"""Leakage-safe Phase 2B deterministic baselines and shared evaluator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Self

import duckdb
import psutil
import pyarrow.parquet as pq

from drought_forecasting.experiment_registry import FIELDS, add_record
from drought_forecasting.prediction_contract import (
    ComparableRowIdentity,
    comparable_row_identity,
    load_fallback_chains,
    validate_prediction_rows,
)
from drought_forecasting.validation_audit import canonical_sha256, load_audit_config
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import (
    configure_connection,
    drop_temporary_relations,
    extract_mask_template,
    transplant_single_fold,
)
from drought_forecasting.validation_metrics import MetricReport, MetricResult, build_metric_report

BASELINES = (
    "global_mean",
    "location_mean",
    "location_calendar_month_climatology",
    "persistence",
    "seasonal_naive",
    "location_trend_seasonal",
)
DATA_MANIFEST_ID = "445ce8f92d21abe7e103ad77f38091a4f55e0466d31515d33fbd40c06fb8e533"
VALIDATION_ID = "dfafe4ae008ac4180f3f92a54ca825c779ab4768b0ba870e22dd1cd4e14088c9"
EXPECTED_ROWS = 551_965
POLICIES = {
    "mask_policy_id": "mask-exact-complete-v1",
    "tws_provenance_policy_id": "tws-observed-only-v1",
    "recursion_policy_id": "recursion-disabled-v1",
    "metric_policy_id": "rmse-row-pooled-v1",
}


class PeakMemoryMonitor:
    """Sample process RSS, including children, during a bounded execution."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self.peak_bytes = 0
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        process = psutil.Process()
        while not self._stop.wait(0.02):
            processes = [process, *process.children(recursive=True)]
            total = sum(item.memory_info().rss for item in processes if item.is_running())
            self.peak_bytes = max(self.peak_bytes, total)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()
        self._sample_once()

    def _sample_once(self) -> None:
        process = psutil.Process()
        total = process.memory_info().rss
        self.peak_bytes = max(self.peak_bytes, total)


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _candidate_sql(baseline: str) -> str:
    candidates = {
        "global_mean": "global_mean",
        "location_mean": "location_mean",
        "location_calendar_month_climatology": "climatology",
        "persistence": "persistence",
        "seasonal_naive": "seasonal_naive",
        "location_trend_seasonal": "trend_seasonal",
    }
    if baseline not in candidates:
        raise ValidationError(f"unknown deterministic baseline: {baseline}")
    return candidates[baseline]


def _fallback_expression(chain: Sequence[str]) -> tuple[str, str, str]:
    columns = {
        "global_mean": "global_mean",
        "location_mean": "location_mean",
        "location_calendar_month_climatology": "climatology",
        "persistence": "persistence",
        "seasonal_naive": "seasonal_naive",
        "location_trend_seasonal": "trend_seasonal",
    }
    expressions = [columns[stage] for stage in chain]
    prediction = f"coalesce({', '.join(expressions)})"
    level = "CASE " + " ".join(
        f"WHEN {expression} IS NOT NULL THEN {index}" for index, expression in enumerate(expressions)
    ) + " ELSE NULL END"
    reason = "CASE " + " ".join(
        f"WHEN {expression} IS NOT NULL THEN '{stage}'" for stage, expression in zip(chain, expressions, strict=True)
    ) + " ELSE 'exhausted' END"
    return prediction, level, reason


def _create_fold_output(
    connection: duckdb.DuckDBPyConnection,
    *,
    baseline: str,
    chain: Sequence[str],
    fold_id: str,
    origin: date,
    retained_relation: str,
    train_relation: str,
    run_id: str,
    configuration_id: str,
) -> None:
    """Fit fold-local statistics and create all predictions by exact calendar joins."""
    prediction, fallback_level, selected_stage = _fallback_expression(chain)
    connection.execute("DROP TABLE IF EXISTS phase2b_output")
    connection.execute(
        f"""
        CREATE TEMP TABLE phase2b_output AS
        WITH fitting AS (
            SELECT
                CAST(round(lat * 2) AS BIGINT) AS lat2,
                CAST(round(lon * 2) AS BIGINT) AS lon2,
                CAST(time + INTERVAL 1 MONTH AS DATE) AS fitting_target_month,
                target
            FROM {train_relation}
            WHERE time + INTERVAL 1 MONTH <= ? AND target IS NOT NULL
        ), global_stats AS (
            SELECT avg(target) AS global_mean FROM fitting
        ), location_stats AS (
            SELECT lat2, lon2, avg(target) AS location_mean
            FROM fitting GROUP BY lat2, lon2
        ), climatology AS (
            SELECT lat2, lon2, month(fitting_target_month) AS calendar_month,
                   avg(target) AS climatology
            FROM fitting GROUP BY lat2, lon2, calendar_month
        ), trend AS (
            SELECT lat2, lon2,
                   regr_slope(target, date_diff('month', DATE '1970-01-01', fitting_target_month)) AS slope,
                   regr_intercept(target, date_diff('month', DATE '1970-01-01', fitting_target_month)) AS intercept
            FROM fitting GROUP BY lat2, lon2
        ), trend_seasonality AS (
            SELECT f.lat2, f.lon2, month(f.fitting_target_month) AS calendar_month,
                   avg(f.target - (t.intercept + t.slope * date_diff('month', DATE '1970-01-01', f.fitting_target_month))) AS seasonal_residual
            FROM fitting f JOIN trend t USING (lat2, lon2)
            WHERE t.slope IS NOT NULL AND t.intercept IS NOT NULL
            GROUP BY f.lat2, f.lon2, calendar_month
        ), events AS (
            SELECT r.*, tr.lat AS latitude,
                   tr.SPEI_01_t, tr.SPEI_03_t, tr.SPEI_06_t, tr.SPEI_12_t
            FROM {retained_relation} r
            JOIN {train_relation} tr
              ON CAST(round(tr.lat * 2) AS BIGINT) = r.lat2
             AND CAST(round(tr.lon * 2) AS BIGINT) = r.lon2
             AND tr.time = r.input_month
        ), candidates AS (
            SELECT e.*,
                   g.global_mean,
                   lm.location_mean,
                   cm.climatology,
                   p.TWS_t AS persistence,
                   s.TWS_t AS seasonal_naive,
                   CASE WHEN t.slope IS NOT NULL AND tse.seasonal_residual IS NOT NULL
                        THEN t.intercept + t.slope * date_diff('month', DATE '1970-01-01', e.target_month)
                             + tse.seasonal_residual END AS trend_seasonal
            FROM events e CROSS JOIN global_stats g
            LEFT JOIN location_stats lm USING (lat2, lon2)
            LEFT JOIN climatology cm
              ON cm.lat2=e.lat2 AND cm.lon2=e.lon2
             AND cm.calendar_month=month(e.target_month)
            LEFT JOIN {train_relation} p
              ON CAST(round(p.lat * 2) AS BIGINT)=e.lat2
             AND CAST(round(p.lon * 2) AS BIGINT)=e.lon2
             AND p.time=e.last_observed_month AND p.time <= e.input_month
            LEFT JOIN {train_relation} s
              ON CAST(round(s.lat * 2) AS BIGINT)=e.lat2
             AND CAST(round(s.lon * 2) AS BIGINT)=e.lon2
             AND s.time=e.target_month - INTERVAL 12 MONTH AND s.time <= e.input_month
            LEFT JOIN trend t USING (lat2, lon2)
            LEFT JOIN trend_seasonality tse
              ON tse.lat2=e.lat2 AND tse.lon2=e.lon2
             AND tse.calendar_month=month(e.target_month)
        )
        SELECT
            ?::VARCHAR AS run_id,
            fold_id,
            'lat2=' || lat2::VARCHAR || ';lon2=' || lon2::VARCHAR AS location_id,
            input_month,
            target_month,
            effective_horizon,
            CASE WHEN mask_state THEN 'masked/unavailable' ELSE 'observed' END AS mask_state,
            CAST({prediction} AS DOUBLE) AS prediction,
            CAST(target_value AS DOUBLE) AS validation_actual,
            ?::VARCHAR AS model_name,
            ?::VARCHAR AS configuration_id,
            ?::VARCHAR AS data_manifest_id,
            ?::VARCHAR AS validation_id,
            CAST({fallback_level} AS INTEGER) AS fallback_level,
            CAST({selected_stage} AS VARCHAR) AS fallback_stage,
            CASE WHEN {fallback_level}=0 THEN 'primary_available'
                 ELSE 'missing:' || array_to_string([{', '.join(repr(stage) for stage in chain)}][1:{fallback_level}], ',')
            END AS fallback_reason,
            latitude,
            SPEI_01_t, SPEI_03_t, SPEI_06_t, SPEI_12_t,
            ?::VARCHAR AS mask_policy_id,
            ?::VARCHAR AS tws_provenance_policy_id,
            ?::VARCHAR AS recursion_policy_id,
            ?::VARCHAR AS metric_policy_id
        FROM candidates
        ORDER BY fold_id, location_id, input_month, target_month
        """,
        [
            origin,
            run_id,
            baseline,
            configuration_id,
            DATA_MANIFEST_ID,
            VALIDATION_ID,
            POLICIES["mask_policy_id"],
            POLICIES["tws_provenance_policy_id"],
            POLICIES["recursion_policy_id"],
            POLICIES["metric_policy_id"],
        ],
    )
    invalid = connection.execute(
        """
        SELECT count(*) FROM phase2b_output
        WHERE prediction IS NULL OR NOT isfinite(prediction)
           OR fallback_level IS NULL OR fallback_stage='exhausted'
        """
    ).fetchone()[0]
    if invalid:
        raise ValidationError(f"{invalid} prediction rows exhausted or produced invalid output")


def _metric_value(result: MetricResult) -> dict[str, Any]:
    return {"count": result.row_count, "rmse": result.rmse}


def _metric_report(report: MetricReport) -> dict[str, Any]:
    return {
        "pooled": _metric_value(report.pooled),
        "fold": {str(key): _metric_value(value) for key, value in report.per_fold},
        "horizon": {str(key): _metric_value(value) for key, value in report.per_horizon},
        "mask_state": {str(key): _metric_value(value) for key, value in report.per_mask_state},
        "latitude_band": {
            str(key): _metric_value(value) for key, value in report.per_latitude_band
        },
        "spei": {
            column: {str(key): _metric_value(value) for key, value in values}
            for column, values in report.per_spei
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
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


def _load_or_freeze_identity(
    path: Path, actual: ComparableRowIdentity, *, allow_freeze: bool
) -> ComparableRowIdentity:
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        expected = ComparableRowIdentity(value["row_count"], value["sha256"])
        if actual != expected:
            raise ValidationError("prediction rows differ from authoritative comparable-row identity")
        return expected
    if not allow_freeze:
        raise ValidationError("authoritative comparable-row identity has not been frozen")
    if actual.row_count != EXPECTED_ROWS:
        raise ValidationError("cannot freeze unexpected validation row count")
    _write_json_atomic(
        path,
        {
            "schema_version": "phase2b-comparable-rows-v1",
            "validation_version": "validation-v1",
            "validation_id": VALIDATION_ID,
            **asdict(actual),
        },
    )
    return actual


def run_baseline(baseline: str, *, allow_freeze: bool = False) -> dict[str, Any]:
    """Execute one finalized baseline once, persist metrics, and register it atomically."""
    if baseline not in BASELINES:
        raise ValidationError(f"unknown deterministic baseline: {baseline}")
    chains = load_fallback_chains(Path("configs/phase2a_prediction_contract.yaml"))
    chain = chains[baseline]
    config = {
        "schema_version": "phase2b-baseline-v1",
        "baseline": baseline,
        "fallback_chain": list(chain),
        "fit_policy": "target-month-on-or-before-fold-origin-v1",
        "calendar_lookup": "exact-month-only-v1",
        "threads": 2,
        "duckdb_memory_limit": "2GB",
    }
    configuration_id = canonical_sha256(config)
    started_at = datetime.now(UTC).replace(microsecond=0)
    run_id = f"run-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{baseline[:31]}"
    oof_path = Path("artifacts/phase2b") / f"{run_id}-oof.parquet"
    metrics_path = Path("reports/phase2b") / f"{run_id}-metrics.json"
    comparable_path = Path("reports/phase2b/comparable_rows.json")
    if oof_path.exists() or metrics_path.exists():
        raise ValidationError("refusing to overwrite an existing Phase 2B run")

    audit_config = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    connection = duckdb.connect(":memory:")
    configure_connection(connection, threads=2, memory_limit="2GB")
    connection.execute(
        f"CREATE VIEW train_data AS SELECT * FROM read_parquet('{_quoted_path(Path('data/processed/Train.parquet'))}')"
    )
    connection.execute(
        f"CREATE VIEW test_data AS SELECT * FROM read_parquet('{_quoted_path(Path('data/processed/Test.parquet'))}')"
    )
    template = extract_mask_template(
        connection, "test_data", date(2015, 9, 1), output_relation="phase2b_template"
    )
    oof_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    start = time.perf_counter()
    try:
        with PeakMemoryMonitor() as memory:
            for index, fold in enumerate(audit_config.folds):
                prefix = f"phase2b_fold_{index:03d}"
                result = transplant_single_fold(
                    connection,
                    "train_data",
                    template.relation,
                    fold_id=fold.fold_id,
                    origin=fold.origin,
                    history_gate=audit_config.history_gate,
                    relation_prefix=prefix,
                    required_relative_months=18,
                )
                try:
                    _create_fold_output(
                        connection,
                        baseline=baseline,
                        chain=chain,
                        fold_id=fold.fold_id,
                        origin=fold.origin,
                        retained_relation=result.relations.retained,
                        train_relation="train_data",
                        run_id=run_id,
                        configuration_id=configuration_id,
                    )
                    table = connection.execute(
                        """
                        SELECT * FROM phase2b_output
                        ORDER BY fold_id, location_id, input_month, target_month
                        """
                    ).to_arrow_table()
                    if writer is None:
                        writer = pq.ParquetWriter(oof_path, table.schema, compression="zstd")
                    writer.write_table(table)
                finally:
                    connection.execute("DROP TABLE IF EXISTS phase2b_output")
                    drop_temporary_relations(connection, result.relations)
            if writer is not None:
                writer.close()
                writer = None
            rows = pq.read_table(oof_path).to_pylist()
            actual_identity = comparable_row_identity(rows)
            expected_identity = _load_or_freeze_identity(
                comparable_path, actual_identity, allow_freeze=allow_freeze
            )
            validate_prediction_rows(
                rows,
                expected_rows=expected_identity,
                expected_data_manifest_id=DATA_MANIFEST_ID,
                expected_validation_id=VALIDATION_ID,
            )
            if len({(row["fold_id"], row["target_month"], row["location_id"]) for row in rows}) != EXPECTED_ROWS:
                raise ValidationError("F01/F02 do not contain 551,965 distinct targets")
            metric_rows = [
                {
                    "target": row["validation_actual"],
                    "prediction": row["prediction"],
                    "fold_id": row["fold_id"],
                    "horizon": row["effective_horizon"],
                    "mask_state": row["mask_state"],
                    "latitude": row["latitude"],
                    "SPEI_01_t": row["SPEI_01_t"],
                    "SPEI_03_t": row["SPEI_03_t"],
                    "SPEI_06_t": row["SPEI_06_t"],
                    "SPEI_12_t": row["SPEI_12_t"],
                    **POLICIES,
                }
                for row in rows
            ]
            report = build_metric_report(metric_rows)
            fallback_counts = dict(sorted(Counter(row["fallback_stage"] for row in rows).items()))
        runtime = time.perf_counter() - start
        oof_hash = _sha256(oof_path)
        result_payload: dict[str, Any] = {
            "schema_version": "phase2b-run-metrics-v1",
            "run_id": run_id,
            "baseline": baseline,
            "configuration": config,
            "configuration_id": configuration_id,
            "data_manifest_id": DATA_MANIFEST_ID,
            "validation_id": VALIDATION_ID,
            "comparable_rows": asdict(expected_identity),
            "metrics": _metric_report(report),
            "coverage": {"predicted": len(rows), "expected": EXPECTED_ROWS, "fraction": len(rows) / EXPECTED_ROWS},
            "fallback_counts": fallback_counts,
            "runtime_seconds": runtime,
            "peak_memory_mb": memory.peak_bytes / 1024**2,
            "oof_artifact": {
                "path": oof_path.as_posix(),
                "sha256": oof_hash,
                "size_bytes": oof_path.stat().st_size,
            },
            "decision": "keep",
            "decision_reason": "meaningful deterministic performance-floor evidence",
        }
        _write_json_atomic(metrics_path, result_payload)
        result_payload["compact_artifact_size_bytes"] = metrics_path.stat().st_size
        _write_json_atomic(metrics_path, result_payload)

        registry_record = {field: "" for field in FIELDS}
        registry_record.update(
            {
                "run_id": run_id,
                "run_date_utc": started_at.isoformat().replace("+00:00", "Z"),
                "git_commit": "b3003209ec29c860498a93bf5163784fe720a64c",
                "data_version": DATA_MANIFEST_ID,
                "validation_version": "validation-v1",
                "seed": "0",
                "features": json.dumps(["fold-local-target-history", "exact-month-observed-TWS"]),
                "model": baseline,
                "model_parameters": json.dumps(config, sort_keys=True),
                "overall_cv_rmse": str(report.pooled.rmse),
                "rmse_by_horizon": json.dumps(result_payload["metrics"]["horizon"], sort_keys=True),
                "regional_or_subgroup_metrics": json.dumps(
                    {
                        key: result_payload["metrics"][key]
                        for key in ("fold", "mask_state", "latitude_band", "spei")
                    }
                    | {"fallback_counts": fallback_counts, "coverage": result_payload["coverage"]},
                    sort_keys=True,
                ),
                "runtime_seconds": str(runtime),
                "peak_memory_mb": str(memory.peak_bytes / 1024**2),
                "model_size_mb": "0",
                "artifact_paths": json.dumps([metrics_path.as_posix(), oof_path.as_posix()]),
                "decision": result_payload["decision"],
                "decision_reason": result_payload["decision_reason"],
                "notes": f"OOF sha256={oof_hash}; compact metrics bytes={metrics_path.stat().st_size}",
            }
        )
        add_record(Path("experiments/registry.csv"), registry_record)
        return result_payload
    except BaseException:
        if writer is not None:
            writer.close()
        oof_path.unlink(missing_ok=True)
        raise
    finally:
        drop_temporary_relations(connection, (template.relation,))
        connection.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", choices=BASELINES, required=True)
    parser.add_argument("--freeze-comparable", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_baseline(args.baseline, allow_freeze=args.freeze_comparable)
    print(json.dumps({key: result[key] for key in ("run_id", "baseline", "metrics", "runtime_seconds", "peak_memory_mb", "fallback_counts")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
