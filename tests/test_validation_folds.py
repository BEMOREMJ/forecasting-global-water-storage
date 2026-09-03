from __future__ import annotations

from datetime import date

import duckdb
import pytest

from drought_forecasting.validation_core import TWSProvenance, ValidationError
from drought_forecasting.validation_folds import (
    TEMPLATE_COLUMNS,
    CompactFoldRelations,
    FoldSpec,
    FoldSummary,
    HistoryGate,
    audit_compact_cross_fold_relations,
    audit_global_origin_coverage,
    configure_connection,
    construct_folds_sequentially,
    drop_temporary_relations,
    extract_mask_template,
    transplant_single_fold,
)

ORIGIN = date(2010, 1, 1)
TEST_ORIGIN = date(2020, 1, 1)


def add_month(month: date, offset: int) -> date:
    absolute = month.year * 12 + month.month - 1 + offset
    year, zero_month = divmod(absolute, 12)
    return date(year, zero_month + 1, 1)


def make_connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    configure_connection(connection)
    connection.execute(
        """
        CREATE TABLE test_data (
            ID VARCHAR, time DATE, lat DOUBLE, lon DOUBLE, TWS_t DOUBLE,
            SPEI_01_t DOUBLE, SPEI_03_t DOUBLE, SPEI_06_t DOUBLE,
            SPEI_12_t DOUBLE, SOIL_MOISTURE_t DOUBLE,
            month_sin DOUBLE, month_cos DOUBLE, TWS_t_masked BOOLEAN
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE train_data (
            sample_id VARCHAR, time DATE, lat DOUBLE, lon DOUBLE,
            TWS_t DOUBLE, target DOUBLE
        )
        """
    )
    return connection


def insert_test_row(
    connection: duckdb.DuckDBPyConnection,
    location: int,
    offset: int,
    masked: bool,
) -> None:
    connection.execute(
        "INSERT INTO test_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            f"test-{location}-{offset}",
            add_month(TEST_ORIGIN, offset),
            float(location),
            float(location),
            900_000.0 + location,
            800_001.0,
            800_003.0,
            800_006.0,
            800_012.0,
            700_000.0,
            0.123,
            0.456,
            masked,
        ],
    )


def insert_train_row(
    connection: duckdb.DuckDBPyConnection,
    location: int,
    offset: int,
    *,
    target: float | None = 1.0,
    tws: float | None = None,
) -> None:
    connection.execute(
        "INSERT INTO train_data VALUES (?, ?, ?, ?, ?, ?)",
        [
            f"train-{location}-{offset}",
            add_month(ORIGIN, offset),
            float(location),
            float(location),
            float(location * 100 + offset) if tws is None else tws,
            target,
        ],
    )


def add_passing_history(connection: duckdb.DuckDBPyConnection, location: int) -> None:
    # Twelve observations whose endpoints span exactly twelve calendar months.
    for offset in [*range(-13, -2), -1]:
        insert_train_row(connection, location, offset)


def populated_connection() -> duckdb.DuckDBPyConnection:
    connection = make_connection()

    # Location 0 has the complete 18-row global path and controls global coverage.
    for offset in range(18):
        insert_test_row(connection, 0, offset, masked=offset not in {0, 7, 14})
        insert_train_row(connection, 0, offset, target=10_000.0 + offset)
    insert_train_row(connection, 0, 18, target=10_018.0)

    # Location 1 has a valid sparse path. Offset 1 is officially omitted even though Train has it.
    for offset, masked in [(0, False), (2, True), (3, True)]:
        insert_test_row(connection, 1, offset, masked)
    for offset in range(4):
        insert_train_row(connection, 1, offset, target=20_000.0 + offset)

    # Location 2 has a sparse three-row template but its expected offset 1 is missing in Train.
    for offset in range(3):
        insert_test_row(connection, 2, offset, masked=offset > 0)
    insert_train_row(connection, 2, 0)
    insert_train_row(connection, 2, 2)

    # Location 3 maps both inputs, but one required target is unavailable.
    for offset in range(2):
        insert_test_row(connection, 3, offset, masked=offset == 1)
        insert_train_row(connection, 3, offset, target=None if offset == 1 else 1.0)

    for location in range(4):
        add_passing_history(connection, location)
    return connection


def build_main_fold(
    connection: duckdb.DuckDBPyConnection,
    *,
    prefix: str = "fold",
):
    template = extract_mask_template(
        connection, "test_data", TEST_ORIGIN, output_relation="template"
    )
    result = transplant_single_fold(
        connection,
        "train_data",
        template.relation,
        fold_id="F01",
        origin=ORIGIN,
        history_gate=HistoryGate(),
        relation_prefix=prefix,
    )
    return template, result


def test_t010_template_contains_only_approved_structural_test_fields() -> None:
    """T010: actual Test values and covariates cannot cross the template boundary."""
    connection = populated_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)

    assert tuple(row[0] for row in connection.execute(
        f"DESCRIBE {template.relation}"
    ).fetchall()) == TEMPLATE_COLUMNS
    forbidden = {
        "TWS_t",
        "SPEI_01_t",
        "SPEI_03_t",
        "SPEI_06_t",
        "SPEI_12_t",
        "SOIL_MOISTURE_t",
        "month_sin",
        "month_cos",
    }
    assert forbidden.isdisjoint(TEMPLATE_COLUMNS)


def test_t011_t012_sparse_own_template_paths_are_all_or_nothing() -> None:
    """T011/T012: shorter paths are valid; incomplete reproduction rejects the location."""
    connection = populated_connection()
    template, result = build_main_fold(connection)
    summary = result.summary

    assert template.rows == 26
    assert template.locations == 4
    assert template.distinct_relative_months == 18
    assert template.omitted_location_month_slots == 46
    assert summary.total_locations == 4
    assert summary.retained_locations == 2
    assert summary.excluded_locations == 2
    assert summary.template_rows_for_retained_locations == 21
    assert summary.actual_retained_rows == 21
    assert summary.template_rows_for_excluded_locations == 5
    assert summary.incomplete_transplant_rows_among_retained == 0
    assert summary.path_incomplete_locations == 1
    assert summary.target_incomplete_locations == 1

    cohorts = connection.execute(
        f"""
        SELECT lat2, expected_template_rows, matched_template_rows, retained
        FROM {result.relations.cohorts} ORDER BY lat2
        """
    ).fetchall()
    assert cohorts == [
        (0, 18, 18, True),
        (2, 3, 3, True),
        (4, 3, 2, False),
        (6, 2, 2, False),
    ]


def test_t012_official_omission_is_not_inserted_or_masked() -> None:
    """T012: a historical row at an omitted Test slot remains outside the fold."""
    connection = populated_connection()
    _, result = build_main_fold(connection)

    assert connection.execute(
        "SELECT count(*) FROM train_data WHERE lat=1 AND time=?", [add_month(ORIGIN, 1)]
    ).fetchone()[0] == 1
    assert connection.execute(
        f"""
        SELECT count(*) FROM {result.relations.retained}
        WHERE lat2=2 AND relative_month=1
        """
    ).fetchone()[0] == 0
    assert connection.execute(
        f"""
        SELECT count(*) FROM {result.relations.mapped}
        WHERE lat2=2 AND relative_month=1
        """
    ).fetchone()[0] == 0


def test_t019_global_coverage_is_separate_and_failure_is_rejected() -> None:
    """T019: origin-level 18/18 coverage does not expand sparse paths."""
    connection = populated_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    coverage = audit_global_origin_coverage(
        connection, "train_data", template.relation, ORIGIN
    )
    assert coverage.complete
    assert (coverage.available_input_months, coverage.available_target_months) == (18, 18)

    connection.execute("DELETE FROM train_data WHERE time=?", [add_month(ORIGIN, 18)])
    failed = audit_global_origin_coverage(connection, "train_data", template.relation, ORIGIN)
    assert failed.available_input_months == 18
    assert failed.available_target_months == 17
    assert not failed.complete
    with pytest.raises(ValidationError, match="global"):
        transplant_single_fold(
            connection,
            "train_data",
            template.relation,
            fold_id="F01",
            origin=ORIGIN,
        )


def test_t005_t019_history_gate_uses_only_pre_origin_observations() -> None:
    """T005/T019: count and span boundaries are computed strictly before the origin."""
    connection = make_connection()
    for location in range(3):
        insert_test_row(connection, location, 0, masked=False)
        insert_train_row(connection, location, 0)
        insert_train_row(connection, location, 1)

    # Pass: 12 observations with exactly a 12-month endpoint span.
    for offset in [*range(-13, -2), -1]:
        insert_train_row(connection, 0, offset)
    # Fail count: 11 observations despite a 12-month span.
    for offset in [*range(-13, -3), -1]:
        insert_train_row(connection, 1, offset)
    # Fail span: 12 observations but only an 11-month span. Origin rows must not help.
    for offset in range(-12, 0):
        insert_train_row(connection, 2, offset)

    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    result = transplant_single_fold(
        connection,
        "train_data",
        template.relation,
        fold_id="F01",
        origin=ORIGIN,
        required_relative_months=1,
    )
    rows = connection.execute(
        f"""
        SELECT lat2, history_observations, history_span_months, history_gate_pass
        FROM {result.relations.cohorts} ORDER BY lat2
        """
    ).fetchall()
    assert rows == [(0, 12, 12, True), (2, 11, 12, False), (4, 12, 11, False)]
    assert result.summary.retained_locations == 1
    assert result.summary.history_excluded_locations == 2


def test_t008_t019_observed_resets_and_masked_horizons_are_location_safe() -> None:
    """T008/T019: only earlier same-location observed resets anchor masked horizons."""
    connection = populated_connection()
    _, result = build_main_fold(connection)
    rows = connection.execute(
        f"""
        SELECT relative_month, mask_state, available_tws, tws_provenance,
               last_observed_month, effective_horizon
        FROM {result.relations.retained}
        WHERE lat2=0 AND relative_month IN (0, 1, 6, 7)
        ORDER BY relative_month
        """
    ).fetchall()
    assert rows == [
        (0, False, 0.0, TWSProvenance.OBSERVED.value, add_month(ORIGIN, 0), 1),
        (1, True, None, TWSProvenance.MASKED.value, add_month(ORIGIN, 0), 2),
        (6, True, None, TWSProvenance.MASKED.value, add_month(ORIGIN, 0), 7),
        (7, False, 7.0, TWSProvenance.OBSERVED.value, add_month(ORIGIN, 7), 1),
    ]
    assert connection.execute(
        f"""
        SELECT last_observed_month, effective_horizon
        FROM {result.relations.retained}
        WHERE lat2=2 AND relative_month=2
        """
    ).fetchone() == (add_month(ORIGIN, 0), 3)


def test_t019_year_boundary_uses_exact_calendar_offsets() -> None:
    connection = populated_connection()
    _, result = build_main_fold(connection)
    assert connection.execute(
        f"""
        SELECT input_month, target_month
        FROM {result.relations.retained}
        WHERE lat2=0 AND relative_month=11
        """
    ).fetchone() == (date(2010, 12, 1), date(2011, 1, 1))


def structural_result(
    connection: duckdb.DuckDBPyConnection, relation: str
) -> list[tuple[object, ...]]:
    return connection.execute(
        f"""
        SELECT template_row_id, relative_month, input_month, target_month, lat2, lon2,
               mask_state, expected_horizon, tws_provenance,
               last_observed_month, effective_horizon
        FROM {relation}
        ORDER BY input_month, lat2, lon2, template_row_id
        """
    ).fetchall()


def test_t009_t010_target_permutation_cannot_change_mask_retention_or_horizons() -> None:
    """T009/T010: target magnitudes are carried for scoring but cannot define the fold."""
    connection = populated_connection()
    template, first = build_main_fold(connection, prefix="first")
    first_rows = structural_result(connection, first.relations.retained)
    first_summary = first.summary
    drop_temporary_relations(connection, first.relations)

    connection.execute("UPDATE train_data SET target = -target * 17 WHERE target IS NOT NULL")
    second = transplant_single_fold(
        connection,
        "train_data",
        template.relation,
        fold_id="F01",
        origin=ORIGIN,
        relation_prefix="second",
    )
    assert structural_result(connection, second.relations.retained) == first_rows
    assert second.summary == first_summary


def test_t012_t020_repeated_construction_is_deterministic_and_cleanup_is_complete() -> None:
    """T012/T020: construction and compact counts repeat without persistent relations."""
    connection = populated_connection()
    template, first = build_main_fold(connection)
    first_rows = structural_result(connection, first.relations.retained)
    first_summary = first.summary
    drop_temporary_relations(connection, first.relations)

    for relation in first.relations.cleanup_order():
        assert connection.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name=?", [relation]
        ).fetchone()[0] == 0

    second = transplant_single_fold(
        connection,
        "train_data",
        template.relation,
        fold_id="F01",
        origin=ORIGIN,
        relation_prefix="fold",
    )
    assert second.summary == first_summary
    assert structural_result(connection, second.relations.retained) == first_rows


@pytest.mark.parametrize(
    ("threads", "memory_limit"),
    [(0, "2GB"), (3, "2GB"), (2, "3GB"), (2, "2048")],
)
def test_connection_configuration_rejects_unsafe_limits(
    threads: int, memory_limit: str
) -> None:
    with pytest.raises(ValidationError):
        configure_connection(duckdb.connect(), threads=threads, memory_limit=memory_limit)


def fake_summary(
    fold_id: str,
    *,
    retained_rows: int = 1,
    excluded_locations: int = 0,
    horizons: tuple[tuple[int, int], ...] = ((1, 1),),
) -> FoldSummary:
    return FoldSummary(
        fold_id=fold_id,
        origin=ORIGIN,
        total_locations=retained_rows + excluded_locations,
        retained_locations=retained_rows,
        excluded_locations=excluded_locations,
        template_rows_for_retained_locations=retained_rows,
        actual_retained_rows=retained_rows,
        template_rows_for_excluded_locations=excluded_locations,
        incomplete_transplant_rows_among_retained=0,
        path_incomplete_locations=excluded_locations,
        target_incomplete_locations=0,
        history_excluded_locations=0,
        official_omitted_slots=0,
        horizon_counts=horizons,
    )


def compact_relations(connection: duckdb.DuckDBPyConnection) -> CompactFoldRelations:
    relations = CompactFoldRelations("compact_inputs", "compact_targets", "compact_excluded")
    connection.execute(
        f"CREATE TEMP TABLE {relations.input_keys} "
        "(fold_id VARCHAR, input_month DATE, lat2 BIGINT, lon2 BIGINT)"
    )
    connection.execute(
        f"CREATE TEMP TABLE {relations.target_keys} "
        "(fold_id VARCHAR, target_month DATE, lat2 BIGINT, lon2 BIGINT)"
    )
    connection.execute(
        f"CREATE TEMP TABLE {relations.excluded_locations} "
        "(fold_id VARCHAR, lat2 BIGINT, lon2 BIGINT)"
    )
    return relations


def test_t013_overlapping_months_without_location_key_overlap_are_reported() -> None:
    """T013: month overlap is distinct from location-month key overlap."""
    connection = duckdb.connect()
    relations = compact_relations(connection)
    shared_input = date(2010, 1, 1)
    shared_target = date(2010, 2, 1)
    connection.executemany(
        f"INSERT INTO {relations.input_keys} VALUES (?, ?, ?, ?)",
        [("F01", shared_input, 0, 0), ("F02", shared_input, 2, 2)],
    )
    connection.executemany(
        f"INSERT INTO {relations.target_keys} VALUES (?, ?, ?, ?)",
        [("F01", shared_target, 0, 0), ("F02", shared_target, 2, 2)],
    )

    summary = audit_compact_cross_fold_relations(
        connection, relations, [fake_summary("F01"), fake_summary("F02")]
    )
    assert summary.pairwise_overlaps[0].input_months == 1
    assert summary.pairwise_overlaps[0].target_months == 1
    assert summary.pairwise_overlaps[0].input_keys == 0
    assert summary.pairwise_overlaps[0].target_keys == 0


def test_l003_t013_overlapping_principal_target_key_is_rejected() -> None:
    connection = duckdb.connect()
    relations = compact_relations(connection)
    connection.executemany(
        f"INSERT INTO {relations.input_keys} VALUES (?, DATE '2010-01-01', ?, ?)",
        [("F01", 0, 0), ("F02", 2, 2)],
    )
    connection.executemany(
        f"INSERT INTO {relations.target_keys} VALUES (?, DATE '2010-02-01', 0, 0)",
        [("F01",), ("F02",)],
    )
    with pytest.raises(ValidationError, match="target keys overlap"):
        audit_compact_cross_fold_relations(
            connection, relations, [fake_summary("F01"), fake_summary("F02")]
        )


@pytest.mark.parametrize("duplicate_kind", ["input", "target"])
def test_l018_t013_duplicate_key_within_fold_is_rejected(duplicate_kind: str) -> None:
    connection = duckdb.connect()
    relations = compact_relations(connection)
    connection.executemany(
        f"INSERT INTO {relations.input_keys} VALUES ('F01', ?, 0, 0)",
        [(date(2010, 1, 1),), (date(2010, 1 if duplicate_kind == "input" else 2, 1),)],
    )
    connection.executemany(
        f"INSERT INTO {relations.target_keys} VALUES ('F01', ?, 0, 0)",
        [(date(2010, 2, 1),), (date(2010, 2 if duplicate_kind == "target" else 3, 1),)],
    )
    with pytest.raises(ValidationError, match=f"duplicate {duplicate_kind} keys"):
        audit_compact_cross_fold_relations(
            connection,
            relations,
            [fake_summary("F01", retained_rows=2, horizons=((1, 2),))],
        )


def sequential_connection() -> duckdb.DuckDBPyConnection:
    connection = make_connection()
    for location in range(2):
        insert_test_row(connection, location, 0, masked=False)

    # Location 0 is complete in both folds. The first fold's validation period is legitimate
    # pre-origin history for the independently simulated second fold.
    for month, row_id in [
        (date(2009, 12, 1), "history-first"),
        (date(2010, 1, 1), "first-input"),
        (date(2010, 2, 1), "first-target-month"),
        (date(2011, 12, 1), "history-second"),
        (date(2012, 1, 1), "second-input"),
        (date(2012, 2, 1), "second-target-month"),
    ]:
        connection.execute(
            "INSERT INTO train_data VALUES (?, ?, 0, 0, 10, 11)", [row_id, month]
        )
    # Location 1 has history but no row at either fold origin, so it is excluded twice.
    connection.execute(
        "INSERT INTO train_data VALUES ('loc1-history', DATE '2009-12-01', 1, 1, 20, 21)"
    )
    return connection


def list_validation_temp_tables(connection: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            """
            SELECT table_name FROM duckdb_tables()
            WHERE table_name LIKE 'multi_%'
            ORDER BY table_name
            """
        ).fetchall()
    ]


def test_l001_l004_t013_t019_t020_two_folds_are_built_sequentially() -> None:
    """T013/T019/T020: disjoint folds pool correctly and distinguish exclusion counts."""
    connection = sequential_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    specs = [FoldSpec("F01", ORIGIN), FoldSpec("F02", date(2012, 1, 1))]

    summary = construct_folds_sequentially(
        connection,
        "train_data",
        template.relation,
        specs,
        history_gate=HistoryGate(1, 0),
        relation_prefix="multi_success",
        required_relative_months=1,
    )

    assert [fold.fold_id for fold in summary.folds] == ["F01", "F02"]
    assert summary.pooled_retained_rows == 2
    assert summary.distinct_pooled_target_keys == 2
    assert summary.aggregate_horizon_counts == ((1, 2),)
    assert summary.excluded_fold_location_instances == 2
    assert summary.unique_excluded_locations == 1
    assert summary.pairwise_overlaps[0].input_months == 0
    assert summary.pairwise_overlaps[0].target_months == 0
    assert summary.pairwise_overlaps[0].input_keys == 0
    assert summary.pairwise_overlaps[0].target_keys == 0
    assert list_validation_temp_tables(connection) == []


@pytest.mark.parametrize(
    ("specs", "message"),
    [
        ([FoldSpec("F01", ORIGIN), FoldSpec("F01", date(2012, 1, 1))], "IDs"),
        ([FoldSpec("F01", ORIGIN), FoldSpec("F02", ORIGIN)], "origins"),
        (
            [FoldSpec("F02", date(2012, 1, 1)), FoldSpec("F01", ORIGIN)],
            "ascending",
        ),
    ],
)
def test_l001_duplicate_or_reversed_fold_specs_are_rejected(
    specs: list[FoldSpec], message: str
) -> None:
    connection = sequential_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    with pytest.raises(ValidationError, match=message):
        construct_folds_sequentially(
            connection,
            "train_data",
            template.relation,
            specs,
            history_gate=HistoryGate(1, 0),
            relation_prefix="multi_invalid",
            required_relative_months=1,
        )
    assert list_validation_temp_tables(connection) == []


def overlapping_fold_connection() -> duckdb.DuckDBPyConnection:
    connection = make_connection()
    insert_test_row(connection, 0, 0, masked=False)
    insert_test_row(connection, 0, 2, masked=False)
    for offset in range(-1, 7):
        insert_train_row(connection, 0, offset)
    return connection


def test_l003_l019_t013_cleanup_after_cross_fold_overlap_failure() -> None:
    """T013: duplicate pooled targets fail after each full fold has already been dropped."""
    connection = overlapping_fold_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    with pytest.raises(ValidationError, match="target keys overlap"):
        construct_folds_sequentially(
            connection,
            "train_data",
            template.relation,
            [FoldSpec("F01", ORIGIN), FoldSpec("F02", date(2010, 3, 1))],
            history_gate=HistoryGate(1, 0),
            relation_prefix="multi_failure",
            required_relative_months=2,
        )
    assert list_validation_temp_tables(connection) == []


def test_t019_t020_multifold_result_is_deterministic_across_repeated_runs() -> None:
    connection = sequential_connection()
    template = extract_mask_template(connection, "test_data", TEST_ORIGIN)
    specs = [FoldSpec("F01", ORIGIN), FoldSpec("F02", date(2012, 1, 1))]
    first = construct_folds_sequentially(
        connection,
        "train_data",
        template.relation,
        specs,
        history_gate=HistoryGate(1, 0),
        relation_prefix="multi_repeat",
        required_relative_months=1,
    )
    second = construct_folds_sequentially(
        connection,
        "train_data",
        template.relation,
        specs,
        history_gate=HistoryGate(1, 0),
        relation_prefix="multi_repeat",
        required_relative_months=1,
    )
    assert second == first
    assert list_validation_temp_tables(connection) == []
