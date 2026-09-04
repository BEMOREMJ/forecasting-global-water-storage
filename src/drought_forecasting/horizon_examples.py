"""Construct deterministic leakage-safe horizon-aware supervised examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Self

import duckdb
import psutil
import yaml

from drought_forecasting.validation_audit import canonical_sha256
from drought_forecasting.validation_core import ValidationError

SCHEMA_VERSION = "phase2c-horizon-examples-v1"
REQUIRED_FINITE = (
    "last_observed_tws",
    "latitude",
    "longitude",
    "SPEI_01_t",
    "SPEI_03_t",
    "SPEI_06_t",
    "SPEI_12_t",
    "SOIL_MOISTURE_t",
    "month_sin",
    "month_cos",
    "target",
    "sample_weight",
)


class _MemoryMonitor:
    def __init__(self) -> None:
        self.peak = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        process = psutil.Process()
        while not self.stop.wait(0.02):
            self.peak = max(self.peak, process.memory_info().rss)

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.thread.join()
        self.peak = max(self.peak, psutil.Process().memory_info().rss)


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"could not load Phase 2C configuration: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("unknown Phase 2C configuration schema")
    if value.get("horizons") != list(range(1, 8)):
        raise ValidationError("Phase 2C horizons must be exactly 1 through 7")
    sampling = value.get("sampling")
    if not isinstance(sampling, dict) or sampling.get("cap") != 2_000_000:
        raise ValidationError("Phase 2C requires the frozen 2,000,000-row sampling cap")
    retained = 0
    for fold_id, fold in value.get("folds", {}).items():
        if fold_id not in {"F01", "F02"} or not isinstance(fold, dict):
            raise ValidationError("Phase 2C contains an unknown fold")
        quotas = fold.get("retained_by_horizon")
        if not isinstance(quotas, dict) or {int(key) for key in quotas} != set(range(1, 8)):
            raise ValidationError("each fold requires quotas for horizons 1 through 7")
        retained += sum(int(count) for count in quotas.values())
    if retained != sampling["cap"]:
        raise ValidationError("stratified quotas do not sum to the configured cap")
    return value


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum() or value[0].isdigit():
        raise ValidationError(f"unsafe relation identifier: {value!r}")
    return value


def create_keyed_train(connection: duckdb.DuckDBPyConnection, source: Path) -> None:
    quoted = str(source.resolve()).replace("'", "''")
    connection.execute(
        f"""
        CREATE TEMP TABLE phase2c_train AS
        SELECT CAST(round(lat*2) AS INTEGER) AS lat2,
               CAST(round(lon*2) AS INTEGER) AS lon2,
               time, lat, lon, TWS_t, SPEI_01_t, SPEI_03_t, SPEI_06_t,
               SPEI_12_t, SOIL_MOISTURE_t, month_sin, month_cos, target
        FROM read_parquet('{quoted}')
        """
    )


def create_fold_candidates(
    connection: duckdb.DuckDBPyConnection,
    *,
    fold_id: str,
    cutoff: date,
    output_relation: str,
    train_relation: str = "phase2c_train",
) -> None:
    """Create exact-calendar candidates using only one fold's permitted target history."""
    output = _identifier(output_relation)
    train = _identifier(train_relation)
    connection.execute(f"DROP TABLE IF EXISTS {output}")
    connection.execute(
        f"""
        CREATE TEMP TABLE {output} AS
        WITH horizons AS (SELECT range::INTEGER AS effective_horizon FROM range(1,8))
        SELECT
            ?::VARCHAR AS fold_id,
            ?::DATE AS fold_cutoff,
            'lat2=' || t.lat2::VARCHAR || ';lon2=' || t.lon2::VARCHAR AS location_id,
            'lat2=' || t.lat2::VARCHAR || ';lon2=' || t.lon2::VARCHAR AS covariate_location_id,
            'lat2=' || s.lat2::VARCHAR || ';lon2=' || s.lon2::VARCHAR AS tws_source_location_id,
            CAST(t.time AS DATE) AS input_month,
            CAST(t.time + INTERVAL 1 MONTH AS DATE) AS target_month,
            CAST(s.time AS DATE) AS tws_source_month,
            h.effective_horizon,
            CAST(s.TWS_t AS DOUBLE) AS last_observed_tws,
            CAST(t.lat AS DOUBLE) AS latitude,
            CAST(t.lon AS DOUBLE) AS longitude,
            CAST(year(t.time) AS INTEGER) AS input_year,
            CAST(month(t.time) AS INTEGER) AS input_calendar_month,
            CAST(t.month_sin AS DOUBLE) AS month_sin,
            CAST(t.month_cos AS DOUBLE) AS month_cos,
            CAST(t.SPEI_01_t AS DOUBLE) AS SPEI_01_t,
            CAST(t.SPEI_03_t AS DOUBLE) AS SPEI_03_t,
            CAST(t.SPEI_06_t AS DOUBLE) AS SPEI_06_t,
            CAST(t.SPEI_12_t AS DOUBLE) AS SPEI_12_t,
            CAST(t.SOIL_MOISTURE_t AS DOUBLE) AS SOIL_MOISTURE_t,
            CAST(t.target AS DOUBLE) AS target,
            ?::INTEGER AS sampling_seed,
            sha256(
                ? || '|' || ? || '|' || CAST(t.time + INTERVAL 1 MONTH AS DATE)::VARCHAR
                || '|' || t.lat2::VARCHAR || '|' || t.lon2::VARCHAR
                || '|' || h.effective_horizon::VARCHAR
            ) AS selection_hash
        FROM {train} t CROSS JOIN horizons h
        JOIN {train} s
          ON s.lat2=t.lat2 AND s.lon2=t.lon2
         AND s.time=t.time + INTERVAL (1-h.effective_horizon) MONTH
         AND s.TWS_t IS NOT NULL
        WHERE t.time + INTERVAL 1 MONTH <= ?
          AND t.target IS NOT NULL
        """,
        [fold_id, cutoff, 20260904, "20260904", fold_id, cutoff],
    )


def append_stratified_sample(
    connection: duckdb.DuckDBPyConnection,
    *,
    candidates: str,
    output: str,
    quotas: Mapping[int, int],
) -> None:
    candidates = _identifier(candidates)
    output = _identifier(output)
    values = ",".join(f"({int(horizon)},{int(count)})" for horizon, count in sorted(quotas.items()))
    connection.execute(
        f"""
        INSERT INTO {output}
        WITH quotas(effective_horizon, quota) AS (VALUES {values}), ranked AS (
            SELECT c.*, q.quota,
                   row_number() OVER (
                       PARTITION BY c.effective_horizon
                       ORDER BY c.selection_hash, c.target_month, c.location_id
                   ) AS selection_rank
            FROM {candidates} c JOIN quotas q USING (effective_horizon)
        ), populations AS (
            SELECT effective_horizon, count(*) AS population_count
            FROM {candidates} GROUP BY effective_horizon
        )
        SELECT
            r.* EXCLUDE (quota, selection_rank),
            CAST(p.population_count AS BIGINT) AS population_count,
            CAST(r.quota AS BIGINT) AS retained_count,
            CAST(p.population_count::DOUBLE / r.quota AS DOUBLE) AS sample_weight,
            r.fold_id || '|' || r.target_month::VARCHAR || '|' || r.location_id
                || '|h=' || r.effective_horizon::VARCHAR AS example_key
        FROM ranked r JOIN populations p USING (effective_horizon)
        WHERE r.selection_rank <= r.quota
        """
    )


def validate_examples(connection: duckdb.DuckDBPyConnection, relation: str) -> int:
    relation = _identifier(relation)
    row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
    if row_count < 1:
        raise ValidationError("horizon example output is empty")
    duplicate_count = int(
        connection.execute(
            f"SELECT count(*)-count(DISTINCT example_key) FROM {relation}"
        ).fetchone()[0]
    )
    if duplicate_count:
        raise ValidationError("duplicated horizon example keys")
    invariant_count = int(
        connection.execute(
            f"""
            SELECT count(*) FROM {relation}
            WHERE date_diff('month', input_month, target_month) <> 1
               OR date_diff('month', tws_source_month, target_month) <> effective_horizon
               OR effective_horizon NOT BETWEEN 1 AND 7
               OR tws_source_month >= target_month
               OR tws_source_month > input_month
               OR target_month > fold_cutoff
               OR location_id <> covariate_location_id
               OR location_id <> tws_source_location_id
            """
        ).fetchone()[0]
    )
    if invariant_count:
        raise ValidationError("calendar, provenance, location, or cutoff invariant failed")
    finite_clause = " OR ".join(f"{column} IS NULL OR NOT isfinite({column})" for column in REQUIRED_FINITE)
    invalid_values = int(
        connection.execute(f"SELECT count(*) FROM {relation} WHERE {finite_clause}").fetchone()[0]
    )
    if invalid_values:
        raise ValidationError("required example values must be finite and nonmissing")
    return row_count


def retained_target_identity(connection: duckdb.DuckDBPyConnection, relation: str) -> str:
    relation = _identifier(relation)
    cursor = connection.execute(f"SELECT example_key FROM {relation} ORDER BY example_key")
    digest = hashlib.sha256()
    while rows := cursor.fetchmany(20_000):
        for (key,) in rows:
            encoded = key.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def materialize(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    configuration_id = canonical_sha256(config)
    artifact = Path(config["output"]["artifact"])
    manifest_path = Path(config["output"]["manifest"])
    if artifact.exists() or manifest_path.exists():
        raise ValidationError("refusing to overwrite a Phase 2C production artifact")
    spill = Path(config["resources"]["spill_directory"])
    artifact.parent.mkdir(parents=True, exist_ok=True)
    spill.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(":memory:")
    connection.execute("SET threads=2")
    connection.execute("SET memory_limit='2GB'")
    connection.execute("SET temp_directory=?", [str(spill.resolve())])
    start = time.perf_counter()
    try:
        with _MemoryMonitor() as memory:
            create_keyed_train(connection, Path(config["sources"]["train_cache"]["path"]))
            connection.execute(
                """
                CREATE TEMP TABLE phase2c_output AS
                SELECT *, 0::BIGINT AS population_count, 0::BIGINT AS retained_count,
                       0.0::DOUBLE AS sample_weight, ''::VARCHAR AS example_key
                FROM (
                    SELECT ''::VARCHAR fold_id, DATE '2000-01-01' fold_cutoff,
                           ''::VARCHAR location_id, ''::VARCHAR covariate_location_id,
                           ''::VARCHAR tws_source_location_id, DATE '2000-01-01' input_month,
                           DATE '2000-01-01' target_month, DATE '2000-01-01' tws_source_month,
                           1::INTEGER effective_horizon, 0.0::DOUBLE last_observed_tws,
                           0.0::DOUBLE latitude, 0.0::DOUBLE longitude, 2000::INTEGER input_year,
                           1::INTEGER input_calendar_month, 0.0::DOUBLE month_sin,
                           0.0::DOUBLE month_cos, 0.0::DOUBLE SPEI_01_t, 0.0::DOUBLE SPEI_03_t,
                           0.0::DOUBLE SPEI_06_t, 0.0::DOUBLE SPEI_12_t,
                           0.0::DOUBLE SOIL_MOISTURE_t, 0.0::DOUBLE AS "target",
                           0::INTEGER sampling_seed, ''::VARCHAR selection_hash
                ) WHERE false
                """
            )
            population: dict[str, dict[str, int]] = {}
            for fold_id, fold in config["folds"].items():
                cutoff = fold["cutoff"]
                create_fold_candidates(
                    connection,
                    fold_id=fold_id,
                    cutoff=cutoff,
                    output_relation="phase2c_candidates",
                )
                population[fold_id] = {
                    str(horizon): count
                    for horizon, count in connection.execute(
                        """
                        SELECT effective_horizon, count(*) FROM phase2c_candidates
                        GROUP BY effective_horizon ORDER BY effective_horizon
                        """
                    ).fetchall()
                }
                append_stratified_sample(
                    connection,
                    candidates="phase2c_candidates",
                    output="phase2c_output",
                    quotas={int(key): int(value) for key, value in fold["retained_by_horizon"].items()},
                )
                connection.execute("DROP TABLE phase2c_candidates")
            row_count = validate_examples(connection, "phase2c_output")
            if row_count != config["sampling"]["cap"]:
                raise ValidationError("materialized row count differs from configured cap")
            target_hash = retained_target_identity(connection, "phase2c_output")
            quoted_artifact = str(artifact.resolve()).replace("'", "''")
            connection.execute(
                f"""
                COPY (
                    SELECT * FROM phase2c_output
                    ORDER BY fold_id, effective_horizon, selection_hash, target_month, location_id
                ) TO '{quoted_artifact}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """
            )
            distributions: dict[str, dict[str, int]] = {}
            for fold, horizon, count in connection.execute(
                """
                SELECT fold_id, effective_horizon, count(*)
                FROM phase2c_output
                GROUP BY fold_id, effective_horizon
                ORDER BY fold_id, effective_horizon
                """
            ).fetchall():
                distributions.setdefault(fold, {})[str(horizon)] = count
        runtime = time.perf_counter() - start
        schema = [
            {"name": name, "type": str(type_value)}
            for name, type_value, *_ in connection.execute("DESCRIBE phase2c_output").fetchall()
        ]
        date_range = connection.execute(
            "SELECT min(input_month),max(input_month),min(target_month),max(target_month),min(tws_source_month),max(tws_source_month) FROM phase2c_output"
        ).fetchone()
        manifest = {
            "schema_version": "phase2c-materialization-manifest-v1",
            "configuration_id": configuration_id,
            "source_identities": config["sources"],
            "sampling": config["sampling"],
            "population_by_fold_horizon": population,
            "retained_by_fold_horizon": distributions,
            "row_count": row_count,
            "date_ranges": {
                "input": [date_range[0].isoformat(), date_range[1].isoformat()],
                "target": [date_range[2].isoformat(), date_range[3].isoformat()],
                "tws_source": [date_range[4].isoformat(), date_range[5].isoformat()],
            },
            "schema": schema,
            "retained_target_sha256": target_hash,
            "artifact": {
                "path": artifact.as_posix(),
                "sha256": _file_hash(artifact),
                "size_bytes": artifact.stat().st_size,
            },
            "runtime_seconds": runtime,
            "peak_memory_mb": memory.peak / 1024**2,
            "provenance_checks": {
                "calendar_relationships": "pass",
                "horizons_1_through_7": "pass",
                "exact_tws_source": "pass",
                "no_intermediate_or_future_tws": "pass",
                "location_identity": "pass",
                "fold_cutoffs": "pass",
                "validation_targets_excluded": "pass",
                "unique_finite_examples": "pass",
            },
        }
        _write_json(manifest_path, manifest)
        return manifest
    except BaseException:
        artifact.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/phase2c_horizon_examples.yaml"))
    args = parser.parse_args(argv)
    manifest = materialize(args.config)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
