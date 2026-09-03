"""Sparse Test-template transplantation and single-fold validation auditing."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

import duckdb

from drought_forecasting.validation_core import TWSProvenance, ValidationError, validate_month

MAX_DUCKDB_MEMORY_BYTES = 2 * 1024**3
TEMPLATE_COLUMNS = (
    "template_row_id",
    "input_month",
    "lat2",
    "lon2",
    "mask_state",
    "relative_month",
    "expected_horizon",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MEMORY_LIMIT = re.compile(r"^(\d+)(MB|GB)$", re.IGNORECASE)


@dataclass(frozen=True)
class HistoryGate:
    """Minimum genuinely observed pre-origin history for a retained location."""

    minimum_observations: int = 12
    minimum_span_months: int = 12

    def __post_init__(self) -> None:
        if isinstance(self.minimum_observations, bool) or self.minimum_observations < 1:
            raise ValidationError("minimum history observations must be a positive integer")
        if isinstance(self.minimum_span_months, bool) or self.minimum_span_months < 0:
            raise ValidationError("minimum history span must be a non-negative integer")


@dataclass(frozen=True)
class FoldSpec:
    """Stable identity and calendar origin for one rolling-origin fold."""

    fold_id: str
    origin: date

    def __post_init__(self) -> None:
        validate_month(self.origin)
        if not self.fold_id or not re.fullmatch(r"[A-Za-z0-9_-]+", self.fold_id):
            raise ValidationError("fold_id must be a non-empty stable identifier")


@dataclass(frozen=True)
class MaskTemplateSummary:
    """Compact facts about the sparse structural Test template."""

    relation: str
    test_origin: date
    rows: int
    locations: int
    distinct_relative_months: int
    omitted_location_month_slots: int


@dataclass(frozen=True)
class GlobalCoverage:
    """Origin-level global calendar coverage, separate from location paths."""

    distinct_relative_months: int
    available_input_months: int
    available_target_months: int
    required_relative_months: int

    @property
    def complete(self) -> bool:
        return (
            self.distinct_relative_months == self.required_relative_months
            and self.available_input_months == self.required_relative_months
            and self.available_target_months == self.required_relative_months
        )


@dataclass(frozen=True)
class FoldRelations:
    """Connection-local temporary relations owned by one fold construction."""

    mapped: str
    cohorts: str
    sources: str
    retained: str

    def cleanup_order(self) -> tuple[str, ...]:
        return self.retained, self.sources, self.cohorts, self.mapped


@dataclass(frozen=True)
class FoldSummary:
    """Compact, row-value-free summary of a single transplanted fold."""

    fold_id: str
    origin: date
    total_locations: int
    retained_locations: int
    excluded_locations: int
    template_rows_for_retained_locations: int
    actual_retained_rows: int
    template_rows_for_excluded_locations: int
    incomplete_transplant_rows_among_retained: int
    path_incomplete_locations: int
    target_incomplete_locations: int
    history_excluded_locations: int
    official_omitted_slots: int
    horizon_counts: tuple[tuple[int, int], ...]
    eligible_fitting_rows: int = 0
    missing_prior_sources: int = 0
    future_source_uses: int = 0
    location_source_mismatches: int = 0
    horizon_mismatches: int = 0
    duplicate_input_keys: int = 0
    duplicate_target_keys: int = 0
    latitude_band_exclusions: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class FoldResult:
    """Temporary relations plus their verified compact fold summary."""

    relations: FoldRelations
    coverage: GlobalCoverage
    summary: FoldSummary


@dataclass(frozen=True)
class CompactFoldRelations:
    """Minimal cross-fold keys retained only while overlap checks run."""

    input_keys: str
    target_keys: str
    excluded_locations: str

    def cleanup_order(self) -> tuple[str, ...]:
        return self.excluded_locations, self.target_keys, self.input_keys


@dataclass(frozen=True)
class PairwiseOverlap:
    """Separate calendar-month and location-month overlap counts for a fold pair."""

    first_fold_id: str
    second_fold_id: str
    input_months: int
    target_months: int
    input_keys: int
    target_keys: int


@dataclass(frozen=True)
class MultiFoldSummary:
    """Compact cross-fold audit result with no row-level assignments."""

    folds: tuple[FoldSummary, ...]
    pairwise_overlaps: tuple[PairwiseOverlap, ...]
    pooled_retained_rows: int
    distinct_pooled_target_keys: int
    excluded_fold_location_instances: int
    unique_excluded_locations: int
    aggregate_horizon_counts: tuple[tuple[int, int], ...]


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValidationError(f"unsafe DuckDB relation identifier: {value!r}")
    return value


def _memory_limit_bytes(value: str) -> int:
    match = _MEMORY_LIMIT.fullmatch(value)
    if match is None:
        raise ValidationError("DuckDB memory limit must use integer MB or GB units")
    amount = int(match.group(1))
    multiplier = 1024**2 if match.group(2).upper() == "MB" else 1024**3
    return amount * multiplier


def configure_connection(
    connection: duckdb.DuckDBPyConnection,
    *,
    threads: int = 2,
    memory_limit: str = "2GB",
) -> None:
    """Apply bounded deterministic DuckDB settings for validation operations."""
    if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 2:
        raise ValidationError("DuckDB validation threads must be one or two")
    if _memory_limit_bytes(memory_limit) > MAX_DUCKDB_MEMORY_BYTES:
        raise ValidationError("DuckDB validation memory limit cannot exceed 2 GB")
    normalized_limit = memory_limit.upper()
    connection.execute(f"SET threads={threads}")
    connection.execute(f"SET memory_limit='{normalized_limit}'")
    connection.execute("SET preserve_insertion_order=false")


def _columns(connection: duckdb.DuckDBPyConnection, relation: str) -> tuple[str, ...]:
    relation = _identifier(relation)
    return tuple(row[0] for row in connection.execute(f"DESCRIBE {relation}").fetchall())


def _require_columns(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    required: set[str],
) -> None:
    columns = set(_columns(connection, relation))
    missing = sorted(required - columns)
    if missing:
        raise ValidationError(f"{relation} is missing required columns: {missing}")


def _relation_exists(connection: duckdb.DuckDBPyConnection, relation: str) -> bool:
    relation = _identifier(relation)
    found = connection.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [relation]
    ).fetchone()
    return bool(found and found[0])


def _require_absent(connection: duckdb.DuckDBPyConnection, relations: tuple[str, ...]) -> None:
    existing = [name for name in relations if _relation_exists(connection, name)]
    if existing:
        raise ValidationError(f"temporary validation relations already exist: {existing}")


def _fold_relations(prefix: str) -> FoldRelations:
    return FoldRelations(
        mapped=f"{prefix}_mapped",
        cohorts=f"{prefix}_cohorts",
        sources=f"{prefix}_sources",
        retained=f"{prefix}_retained",
    )


def extract_mask_template(
    connection: duckdb.DuckDBPyConnection,
    test_relation: str,
    test_origin: date,
    *,
    output_relation: str = "validation_mask_template",
) -> MaskTemplateSummary:
    """Extract only approved structural fields from the actual sparse Test rows."""
    test_relation = _identifier(test_relation)
    output_relation = _identifier(output_relation)
    validate_month(test_origin)
    _require_columns(
        connection,
        test_relation,
        {"ID", "time", "lat", "lon", "TWS_t_masked"},
    )
    _require_absent(connection, (output_relation,))

    invalid = connection.execute(
        f"""
        SELECT count(*)
        FROM {test_relation}
        WHERE ID IS NULL OR time IS NULL OR day(time) <> 1
           OR lat IS NULL OR lon IS NULL OR NOT isfinite(lat) OR NOT isfinite(lon)
           OR lat < -90 OR lat > 90 OR lon < -180 OR lon > 180
           OR lat * 2 <> round(lat * 2) OR lon * 2 <> round(lon * 2)
           OR TWS_t_masked IS NULL
        """
    ).fetchone()[0]
    if invalid:
        raise ValidationError(f"Test structural fields contain {invalid} invalid row(s)")

    duplicate_rows = connection.execute(
        f"""
        SELECT count(*) - count(DISTINCT (time, lat, lon))
        FROM {test_relation}
        """
    ).fetchone()[0]
    if duplicate_rows:
        raise ValidationError("Test contains duplicate location-month template rows")

    connection.execute(
        f"""
        CREATE TEMP TABLE {output_relation} AS
        WITH structural AS (
            SELECT
                CAST(ID AS VARCHAR) AS template_row_id,
                CAST(time AS DATE) AS input_month,
                CAST(round(lat * 2) AS BIGINT) AS lat2,
                CAST(round(lon * 2) AS BIGINT) AS lon2,
                CAST(TWS_t_masked AS BOOLEAN) AS mask_state,
                CAST(date_diff('month', ?, time) AS INTEGER) AS relative_month
            FROM {test_relation}
        ), with_source AS (
            SELECT *,
                max(CASE WHEN NOT mask_state THEN input_month END) OVER (
                    PARTITION BY lat2, lon2
                    ORDER BY input_month
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS last_template_observed_month
            FROM structural
        )
        SELECT
            template_row_id,
            input_month,
            lat2,
            lon2,
            mask_state,
            relative_month,
            CASE
                WHEN last_template_observed_month IS NULL THEN NULL
                ELSE CAST(date_diff(
                    'month', last_template_observed_month, input_month + INTERVAL 1 MONTH
                ) AS INTEGER)
            END AS expected_horizon
        FROM with_source
        ORDER BY input_month, lat2, lon2, template_row_id
        """,
        [test_origin],
    )
    if _columns(connection, output_relation) != TEMPLATE_COLUMNS:
        raise ValidationError("mask template schema contains non-structural fields")

    facts = connection.execute(
        f"""
        SELECT count(*), count(DISTINCT (lat2, lon2)), count(DISTINCT relative_month)
        FROM {output_relation}
        """
    ).fetchone()
    rows, locations, relative_months = map(int, facts)
    return MaskTemplateSummary(
        relation=output_relation,
        test_origin=test_origin,
        rows=rows,
        locations=locations,
        distinct_relative_months=relative_months,
        omitted_location_month_slots=locations * relative_months - rows,
    )


def audit_global_origin_coverage(
    connection: duckdb.DuckDBPyConnection,
    train_relation: str,
    template_relation: str,
    origin: date,
    *,
    required_relative_months: int = 18,
) -> GlobalCoverage:
    """Audit global input/target calendar coverage without expanding location paths."""
    train_relation = _identifier(train_relation)
    template_relation = _identifier(template_relation)
    validate_month(origin)
    _require_columns(connection, train_relation, {"time"})
    _require_columns(connection, template_relation, {"relative_month"})
    if isinstance(required_relative_months, bool) or required_relative_months < 1:
        raise ValidationError("required relative-month count must be positive")

    result = connection.execute(
        f"""
        WITH rels AS (
            SELECT DISTINCT relative_month FROM {template_relation}
        ), months AS (
            SELECT DISTINCT time FROM {train_relation}
        )
        SELECT
            count(*),
            count(*) FILTER (WHERE input_month.time IS NOT NULL),
            count(*) FILTER (WHERE target_month.time IS NOT NULL)
        FROM rels
        LEFT JOIN months input_month
          ON input_month.time = ? + relative_month * INTERVAL 1 MONTH
        LEFT JOIN months target_month
          ON target_month.time = ? + (relative_month + 1) * INTERVAL 1 MONTH
        """,
        [origin, origin],
    ).fetchone()
    return GlobalCoverage(
        distinct_relative_months=int(result[0]),
        available_input_months=int(result[1]),
        available_target_months=int(result[2]),
        required_relative_months=required_relative_months,
    )


def _validate_train_structure(
    connection: duckdb.DuckDBPyConnection,
    train_relation: str,
) -> None:
    _require_columns(
        connection,
        train_relation,
        {"sample_id", "time", "lat", "lon", "TWS_t", "target"},
    )
    invalid = connection.execute(
        f"""
        SELECT count(*) FROM {train_relation}
        WHERE time IS NULL OR day(time) <> 1
           OR lat IS NULL OR lon IS NULL OR NOT isfinite(lat) OR NOT isfinite(lon)
           OR lat < -90 OR lat > 90 OR lon < -180 OR lon > 180
           OR lat * 2 <> round(lat * 2) OR lon * 2 <> round(lon * 2)
        """
    ).fetchone()[0]
    if invalid:
        raise ValidationError(f"Train structural fields contain {invalid} invalid row(s)")


def transplant_single_fold(
    connection: duckdb.DuckDBPyConnection,
    train_relation: str,
    template_relation: str,
    *,
    fold_id: str,
    origin: date,
    history_gate: HistoryGate | None = None,
    relation_prefix: str = "validation_fold",
    required_relative_months: int = 18,
) -> FoldResult:
    """Build and audit one strict sparse-template historical fold."""
    train_relation = _identifier(train_relation)
    template_relation = _identifier(template_relation)
    relation_prefix = _identifier(relation_prefix)
    if not fold_id or not re.fullmatch(r"[A-Za-z0-9_-]+", fold_id):
        raise ValidationError("fold_id must be a non-empty stable identifier")
    validate_month(origin)
    history_gate = history_gate or HistoryGate()
    _validate_train_structure(connection, train_relation)
    if _columns(connection, template_relation) != TEMPLATE_COLUMNS:
        raise ValidationError("template relation does not have the approved structural schema")

    coverage = audit_global_origin_coverage(
        connection,
        train_relation,
        template_relation,
        origin,
        required_relative_months=required_relative_months,
    )
    if not coverage.complete:
        raise ValidationError(
            "historical origin lacks complete global relative input/target month coverage"
        )

    relations = _fold_relations(relation_prefix)
    _require_absent(connection, relations.cleanup_order())

    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.mapped} AS
        SELECT
            ?::VARCHAR AS fold_id,
            t.template_row_id,
            t.relative_month,
            CAST(? + t.relative_month * INTERVAL 1 MONTH AS DATE) AS input_month,
            CAST(? + (t.relative_month + 1) * INTERVAL 1 MONTH AS DATE) AS target_month,
            t.lat2,
            t.lon2,
            t.mask_state,
            t.expected_horizon,
            tr.sample_id IS NOT NULL AS input_matched,
            tr.target IS NOT NULL AS target_present,
            tr.target AS target_value,
            tr.TWS_t AS historical_tws
        FROM {template_relation} t
        LEFT JOIN {train_relation} tr
          ON CAST(round(tr.lat * 2) AS BIGINT) = t.lat2
         AND CAST(round(tr.lon * 2) AS BIGINT) = t.lon2
         AND tr.time = ? + t.relative_month * INTERVAL 1 MONTH
        ORDER BY input_month, lat2, lon2, template_row_id
        """,
        [fold_id, origin, origin, origin],
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.cohorts} AS
        WITH paths AS (
            SELECT
                fold_id,
                lat2,
                lon2,
                count(*) AS expected_template_rows,
                count(*) FILTER (WHERE input_matched) AS matched_template_rows,
                count(*) FILTER (WHERE target_present) AS target_available_rows
            FROM {relations.mapped}
            GROUP BY fold_id, lat2, lon2
        ), histories AS (
            SELECT
                p.fold_id,
                p.lat2,
                p.lon2,
                count(tr.time) FILTER (WHERE tr.TWS_t IS NOT NULL) AS history_observations,
                date_diff(
                    'month',
                    min(tr.time) FILTER (WHERE tr.TWS_t IS NOT NULL),
                    max(tr.time) FILTER (WHERE tr.TWS_t IS NOT NULL)
                ) AS history_span_months
            FROM paths p
            LEFT JOIN {train_relation} tr
              ON CAST(round(tr.lat * 2) AS BIGINT) = p.lat2
             AND CAST(round(tr.lon * 2) AS BIGINT) = p.lon2
             AND tr.time < ?
            GROUP BY p.fold_id, p.lat2, p.lon2
        )
        SELECT
            p.*,
            h.history_observations,
            h.history_span_months,
            p.matched_template_rows = p.expected_template_rows AS path_complete,
            p.target_available_rows = p.expected_template_rows AS targets_complete,
            h.history_observations >= ?
                AND coalesce(h.history_span_months, -1) >= ? AS history_gate_pass,
            p.matched_template_rows = p.expected_template_rows
                AND p.target_available_rows = p.expected_template_rows
                AND h.history_observations >= ?
                AND coalesce(h.history_span_months, -1) >= ? AS retained
        FROM paths p
        JOIN histories h USING (fold_id, lat2, lon2)
        ORDER BY lat2, lon2
        """,
        [
            origin,
            history_gate.minimum_observations,
            history_gate.minimum_span_months,
            history_gate.minimum_observations,
            history_gate.minimum_span_months,
        ],
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.sources} AS
        SELECT
            ?::VARCHAR AS fold_id,
            CAST(round(tr.lat * 2) AS BIGINT) AS lat2,
            CAST(round(tr.lon * 2) AS BIGINT) AS lon2,
            CAST(tr.time AS DATE) AS source_month
        FROM {train_relation} tr
        JOIN {relations.cohorts} c
          ON CAST(round(tr.lat * 2) AS BIGINT) = c.lat2
         AND CAST(round(tr.lon * 2) AS BIGINT) = c.lon2
         AND c.retained
        WHERE tr.time < ? AND tr.TWS_t IS NOT NULL
        UNION ALL
        SELECT fold_id, lat2, lon2, input_month
        FROM {relations.mapped} m
        JOIN {relations.cohorts} c USING (fold_id, lat2, lon2)
        WHERE c.retained AND NOT m.mask_state AND m.historical_tws IS NOT NULL
        """,
        [fold_id, origin],
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.retained} AS
        WITH eligible AS (
            SELECT m.*
            FROM {relations.mapped} m
            JOIN {relations.cohorts} c USING (fold_id, lat2, lon2)
            WHERE c.retained
        )
        SELECT
            e.fold_id,
            e.template_row_id,
            e.relative_month,
            e.input_month,
            e.target_month,
            e.lat2,
            e.lon2,
            e.mask_state,
            e.expected_horizon,
            e.target_value,
            CASE WHEN e.mask_state THEN NULL ELSE e.historical_tws END AS available_tws,
            CASE WHEN e.mask_state THEN ? ELSE ? END AS tws_provenance,
            s.source_month AS last_observed_month,
            CAST(date_diff('month', s.source_month, e.target_month) AS INTEGER)
                AS effective_horizon
        FROM eligible e
        ASOF LEFT JOIN {relations.sources} s
          ON e.fold_id = s.fold_id
         AND e.lat2 = s.lat2
         AND e.lon2 = s.lon2
         AND e.input_month >= s.source_month
        ORDER BY e.input_month, e.lat2, e.lon2, e.template_row_id
        """,
        [TWSProvenance.MASKED.value, TWSProvenance.OBSERVED.value],
    )

    summary = audit_single_fold(
        connection,
        relations,
        fold_id=fold_id,
        origin=origin,
        required_relative_months=required_relative_months,
    )
    fitting_rows = int(
        connection.execute(
            f"""
            SELECT count(*) FROM {train_relation}
            WHERE time + INTERVAL 1 MONTH <= ? AND target IS NOT NULL
            """,
            [origin],
        ).fetchone()[0]
    )
    return FoldResult(
        relations=relations,
        coverage=coverage,
        summary=replace(summary, eligible_fitting_rows=fitting_rows),
    )


def audit_single_fold(
    connection: duckdb.DuckDBPyConnection,
    relations: FoldRelations,
    *,
    fold_id: str,
    origin: date,
    required_relative_months: int = 18,
) -> FoldSummary:
    """Assert single-fold invariants and return a compact summary."""
    for relation in relations.cleanup_order():
        if not _relation_exists(connection, relation):
            raise ValidationError(f"required fold relation is absent: {relation}")

    invalid = connection.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE last_observed_month IS NULL),
            count(*) FILTER (WHERE last_observed_month > input_month),
            count(*) FILTER (WHERE effective_horizon NOT BETWEEN 1 AND 7),
            count(*) FILTER (WHERE expected_horizon IS NULL),
            count(*) FILTER (WHERE effective_horizon <> expected_horizon),
            count(*) FILTER (
                WHERE mask_state AND (
                    available_tws IS NOT NULL OR tws_provenance <> ?
                )
            ),
            count(*) FILTER (
                WHERE NOT mask_state AND (
                    available_tws IS NULL OR tws_provenance <> ?
                )
            ),
            count(*) - count(DISTINCT (lat2, lon2, input_month)),
            count(*) - count(DISTINCT (lat2, lon2, target_month))
        FROM {relations.retained}
        """,
        [TWSProvenance.MASKED.value, TWSProvenance.OBSERVED.value],
    ).fetchone()
    labels = (
        "missing observed source",
        "future observed source",
        "horizon outside 1-7",
        "missing expected horizon",
        "template horizon mismatch",
        "masked provenance violation",
        "observed provenance violation",
        "duplicate input key",
        "duplicate target key",
    )
    failures = {label: int(count) for label, count in zip(labels, invalid, strict=True) if count}
    if failures:
        raise ValidationError(f"single-fold invariant failure: {failures}")

    counts = connection.execute(
        f"""
        SELECT
            count(*),
            count(*) FILTER (WHERE retained),
            count(*) FILTER (WHERE NOT retained),
            coalesce(sum(expected_template_rows) FILTER (WHERE retained), 0),
            coalesce(sum(expected_template_rows) FILTER (WHERE NOT retained), 0),
            coalesce(sum(expected_template_rows - matched_template_rows)
                FILTER (WHERE retained), 0),
            count(*) FILTER (WHERE NOT path_complete),
            count(*) FILTER (WHERE path_complete AND NOT targets_complete),
            count(*) FILTER (
                WHERE path_complete AND targets_complete AND NOT history_gate_pass
            ),
            coalesce(sum(? - expected_template_rows), 0)
        FROM {relations.cohorts}
        """,
        [required_relative_months],
    ).fetchone()
    actual_retained_rows = int(
        connection.execute(f"SELECT count(*) FROM {relations.retained}").fetchone()[0]
    )
    if actual_retained_rows != int(counts[3]):
        raise ValidationError("retained rows do not equal retained locations' template-row sum")
    mapped_rows = int(connection.execute(f"SELECT count(*) FROM {relations.mapped}").fetchone()[0])
    if mapped_rows - actual_retained_rows != int(counts[4]):
        raise ValidationError("excluded rows do not equal excluded locations' template-row sum")

    horizon_counts = tuple(
        (int(horizon), int(row_count))
        for horizon, row_count in connection.execute(
            f"""
            SELECT effective_horizon, count(*)
            FROM {relations.retained}
            GROUP BY effective_horizon
            ORDER BY effective_horizon
            """
        ).fetchall()
    )
    latitude_band_exclusions = tuple(
        (str(band), int(row_count))
        for band, row_count in connection.execute(
            f"""
            SELECT CASE
                WHEN lat2 < -120 THEN '[-90,-60)'
                WHEN lat2 < -60 THEN '[-60,-30)'
                WHEN lat2 < 0 THEN '[-30,0)'
                WHEN lat2 < 60 THEN '[0,30)'
                WHEN lat2 < 120 THEN '[30,60)'
                ELSE '[60,90]'
            END AS latitude_band,
            count(*)
            FROM {relations.cohorts}
            WHERE NOT retained
            GROUP BY latitude_band
            ORDER BY min(lat2)
            """
        ).fetchall()
    )
    return FoldSummary(
        fold_id=fold_id,
        origin=origin,
        total_locations=int(counts[0]),
        retained_locations=int(counts[1]),
        excluded_locations=int(counts[2]),
        template_rows_for_retained_locations=int(counts[3]),
        actual_retained_rows=actual_retained_rows,
        template_rows_for_excluded_locations=int(counts[4]),
        incomplete_transplant_rows_among_retained=int(counts[5]),
        path_incomplete_locations=int(counts[6]),
        target_incomplete_locations=int(counts[7]),
        history_excluded_locations=int(counts[8]),
        official_omitted_slots=int(counts[9]),
        horizon_counts=horizon_counts,
        missing_prior_sources=int(invalid[0]),
        future_source_uses=int(invalid[1]),
        location_source_mismatches=0,
        horizon_mismatches=int(invalid[4]),
        duplicate_input_keys=int(invalid[7]),
        duplicate_target_keys=int(invalid[8]),
        latitude_band_exclusions=latitude_band_exclusions,
    )


def drop_temporary_relations(
    connection: duckdb.DuckDBPyConnection,
    relations: FoldRelations | CompactFoldRelations | tuple[str, ...],
) -> None:
    """Drop owned temporary relations in a deterministic dependency-safe order."""
    names = (
        relations.cleanup_order()
        if isinstance(relations, (FoldRelations, CompactFoldRelations))
        else relations
    )
    for relation in names:
        relation = _identifier(relation)
        connection.execute(f"DROP TABLE IF EXISTS {relation}")


def _create_compact_relations(
    connection: duckdb.DuckDBPyConnection,
    relation_prefix: str,
) -> CompactFoldRelations:
    relation_prefix = _identifier(relation_prefix)
    relations = CompactFoldRelations(
        input_keys=f"{relation_prefix}_input_keys",
        target_keys=f"{relation_prefix}_target_keys",
        excluded_locations=f"{relation_prefix}_excluded_locations",
    )
    _require_absent(connection, relations.cleanup_order())
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.input_keys} (
            fold_id VARCHAR, input_month DATE, lat2 BIGINT, lon2 BIGINT
        )
        """
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.target_keys} (
            fold_id VARCHAR, target_month DATE, lat2 BIGINT, lon2 BIGINT
        )
        """
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE {relations.excluded_locations} (
            fold_id VARCHAR, lat2 BIGINT, lon2 BIGINT
        )
        """
    )
    return relations


def _copy_compact_fold_rows(
    connection: duckdb.DuckDBPyConnection,
    fold_relations: FoldRelations,
    compact_relations: CompactFoldRelations,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {compact_relations.input_keys}
        SELECT fold_id, input_month, lat2, lon2 FROM {fold_relations.retained}
        """
    )
    connection.execute(
        f"""
        INSERT INTO {compact_relations.target_keys}
        SELECT fold_id, target_month, lat2, lon2 FROM {fold_relations.retained}
        """
    )
    connection.execute(
        f"""
        INSERT INTO {compact_relations.excluded_locations}
        SELECT fold_id, lat2, lon2 FROM {fold_relations.cohorts} WHERE NOT retained
        """
    )


def audit_compact_cross_fold_relations(
    connection: duckdb.DuckDBPyConnection,
    relations: CompactFoldRelations,
    fold_summaries: Sequence[FoldSummary],
    *,
    require_zero_input_keys: bool = True,
) -> MultiFoldSummary:
    """Audit compact keys and exclusions after sequential full-fold construction."""
    for relation in relations.cleanup_order():
        if not _relation_exists(connection, relation):
            raise ValidationError(f"required compact relation is absent: {relation}")
    fold_ids = tuple(summary.fold_id for summary in fold_summaries)
    if len(fold_ids) != len(set(fold_ids)):
        raise ValidationError("compact fold summaries contain duplicate fold IDs")

    within_input_duplicates = int(
        connection.execute(
            f"""
            SELECT count(*) FROM (
                SELECT fold_id, input_month, lat2, lon2
                FROM {relations.input_keys}
                GROUP BY ALL HAVING count(*) > 1
            )
            """
        ).fetchone()[0]
    )
    within_target_duplicates = int(
        connection.execute(
            f"""
            SELECT count(*) FROM (
                SELECT fold_id, target_month, lat2, lon2
                FROM {relations.target_keys}
                GROUP BY ALL HAVING count(*) > 1
            )
            """
        ).fetchone()[0]
    )
    if within_input_duplicates:
        raise ValidationError("duplicate input keys exist within a fold")
    if within_target_duplicates:
        raise ValidationError("duplicate target keys exist within a fold")

    pairwise: list[PairwiseOverlap] = []
    for first_index, first in enumerate(fold_ids):
        for second in fold_ids[first_index + 1 :]:
            input_months = int(
                connection.execute(
                    f"""
                    SELECT count(*) FROM (
                        SELECT DISTINCT input_month FROM {relations.input_keys}
                        WHERE fold_id = ?
                        INTERSECT
                        SELECT DISTINCT input_month FROM {relations.input_keys}
                        WHERE fold_id = ?
                    )
                    """,
                    [first, second],
                ).fetchone()[0]
            )
            target_months = int(
                connection.execute(
                    f"""
                    SELECT count(*) FROM (
                        SELECT DISTINCT target_month FROM {relations.target_keys}
                        WHERE fold_id = ?
                        INTERSECT
                        SELECT DISTINCT target_month FROM {relations.target_keys}
                        WHERE fold_id = ?
                    )
                    """,
                    [first, second],
                ).fetchone()[0]
            )
            input_keys = int(
                connection.execute(
                    f"""
                    SELECT count(*)
                    FROM {relations.input_keys} a
                    JOIN {relations.input_keys} b USING (input_month, lat2, lon2)
                    WHERE a.fold_id = ? AND b.fold_id = ?
                    """,
                    [first, second],
                ).fetchone()[0]
            )
            target_keys = int(
                connection.execute(
                    f"""
                    SELECT count(*)
                    FROM {relations.target_keys} a
                    JOIN {relations.target_keys} b USING (target_month, lat2, lon2)
                    WHERE a.fold_id = ? AND b.fold_id = ?
                    """,
                    [first, second],
                ).fetchone()[0]
            )
            pairwise.append(
                PairwiseOverlap(
                    first_fold_id=first,
                    second_fold_id=second,
                    input_months=input_months,
                    target_months=target_months,
                    input_keys=input_keys,
                    target_keys=target_keys,
                )
            )

    target_key_overlaps = sum(item.target_keys for item in pairwise)
    if target_key_overlaps:
        raise ValidationError("principal pooled OOF target keys overlap across folds")
    input_key_overlaps = sum(item.input_keys for item in pairwise)
    if require_zero_input_keys and input_key_overlaps:
        raise ValidationError("validation-v1 input keys overlap across folds")

    pooled_rows = sum(summary.actual_retained_rows for summary in fold_summaries)
    compact_input_rows = int(
        connection.execute(f"SELECT count(*) FROM {relations.input_keys}").fetchone()[0]
    )
    compact_target_rows, distinct_target_keys = map(
        int,
        connection.execute(
            f"""
            SELECT count(*), count(DISTINCT (target_month, lat2, lon2))
            FROM {relations.target_keys}
            """
        ).fetchone(),
    )
    if compact_input_rows != pooled_rows or compact_target_rows != pooled_rows:
        raise ValidationError("sum of fold rows does not equal compact pooled row count")
    if pooled_rows != distinct_target_keys:
        raise ValidationError("pooled row count does not equal distinct pooled target keys")

    horizon_totals: dict[int, int] = {}
    for summary in fold_summaries:
        for horizon, row_count in summary.horizon_counts:
            horizon_totals[horizon] = horizon_totals.get(horizon, 0) + row_count
    if sum(horizon_totals.values()) != pooled_rows:
        raise ValidationError("pooled horizon counts do not sum to pooled rows")

    excluded_instances, unique_excluded = map(
        int,
        connection.execute(
            f"""
            SELECT count(*), count(DISTINCT (lat2, lon2))
            FROM {relations.excluded_locations}
            """
        ).fetchone(),
    )
    expected_excluded_instances = sum(
        summary.excluded_locations for summary in fold_summaries
    )
    if excluded_instances != expected_excluded_instances:
        raise ValidationError("excluded fold-location instance count disagrees with fold summaries")

    return MultiFoldSummary(
        folds=tuple(fold_summaries),
        pairwise_overlaps=tuple(pairwise),
        pooled_retained_rows=pooled_rows,
        distinct_pooled_target_keys=distinct_target_keys,
        excluded_fold_location_instances=excluded_instances,
        unique_excluded_locations=unique_excluded,
        aggregate_horizon_counts=tuple(sorted(horizon_totals.items())),
    )


def construct_folds_sequentially(
    connection: duckdb.DuckDBPyConnection,
    train_relation: str,
    template_relation: str,
    fold_specs: Sequence[FoldSpec],
    *,
    history_gate: HistoryGate | None = None,
    relation_prefix: str = "validation_multifold",
    required_relative_months: int = 18,
    require_zero_input_keys: bool = True,
) -> MultiFoldSummary:
    """Construct full folds one at a time and retain only compact cross-fold keys."""
    specs = tuple(fold_specs)
    if not specs:
        raise ValidationError("at least one fold specification is required")
    fold_ids = [spec.fold_id for spec in specs]
    origins = [spec.origin for spec in specs]
    if len(fold_ids) != len(set(fold_ids)):
        raise ValidationError("fold IDs must be unique")
    if len(origins) != len(set(origins)):
        raise ValidationError("fold origins must be unique")
    if origins != sorted(origins):
        raise ValidationError("fold specifications must be in ascending origin order")

    relation_prefix = _identifier(relation_prefix)
    compact = _create_compact_relations(connection, f"{relation_prefix}_compact")
    summaries: list[FoldSummary] = []
    try:
        for index, spec in enumerate(specs):
            work_prefix = f"{relation_prefix}_work_{index:03d}"
            work_relations = _fold_relations(work_prefix)
            try:
                result = transplant_single_fold(
                    connection,
                    train_relation,
                    template_relation,
                    fold_id=spec.fold_id,
                    origin=spec.origin,
                    history_gate=history_gate,
                    relation_prefix=work_prefix,
                    required_relative_months=required_relative_months,
                )
                _copy_compact_fold_rows(connection, result.relations, compact)
                summaries.append(result.summary)
            finally:
                drop_temporary_relations(connection, work_relations)

        return audit_compact_cross_fold_relations(
            connection,
            compact,
            summaries,
            require_zero_input_keys=require_zero_input_keys,
        )
    finally:
        drop_temporary_relations(connection, compact)
