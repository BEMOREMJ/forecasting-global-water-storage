"""Single-execution Phase 3 recent-period stress diagnostic and drift audit."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from drought_forecasting.deterministic_baselines import (
    POLICIES,
    PeakMemoryMonitor,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.lightgbm_benchmark import (
    APPROVED_FEATURES,
    arrow_matrix,
)
from drought_forecasting.lightgbm_benchmark import (
    load_config as load_model_config,
)
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import configure_connection
from drought_forecasting.validation_metrics import LATITUDE_BANDS, SPEI_BINS

QUANTILES = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "phase3d1-recent-diagnostic-v1":
        raise ValidationError("unknown P3-D1 configuration schema")
    if value.get("execution_limit") != 1 or value.get("experiment_id") != "P3-D1":
        raise ValidationError("P3-D1 must be a single-execution registered experiment")
    quotas = value["sampling"]["retained_by_horizon"]
    if set(map(int, quotas)) != set(range(1, 8)) or sum(map(int, quotas.values())) != 2_000_000:
        raise ValidationError("P3-D1 records the frozen Phase 2 horizon quotas")
    return value


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _numeric_summary(values: np.ndarray, training_range: tuple[float, float] | None = None) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    missing = ~np.isfinite(values)
    finite = values[~missing]
    result: dict[str, Any] = {
        "rows": int(values.size), "missing": int(missing.sum()),
        "missing_fraction": float(missing.mean()) if values.size else None,
    }
    if finite.size:
        result.update({
            "minimum": float(finite.min()), "maximum": float(finite.max()),
            "mean": float(finite.mean()), "standard_deviation": float(finite.std()),
            "quantiles": {str(q): float(v) for q, v in zip(QUANTILES, np.quantile(finite, QUANTILES), strict=True)},
        })
        if training_range is not None:
            outside = (finite < training_range[0]) | (finite > training_range[1])
            result["out_of_training_range"] = int(outside.sum())
            result["out_of_training_range_fraction"] = float(outside.mean())
    return result


def _column(table: pa.Table, name: str) -> np.ndarray | None:
    if name not in table.column_names:
        return None
    return table[name].combine_chunks().to_numpy(zero_copy_only=False)


def _distribution_evidence(training: pa.Table, validation: pa.Table, test: pa.Table) -> dict[str, Any]:
    features = [
        "input_year", "input_calendar_month", "effective_horizon", "latitude", "longitude",
        "last_observed_tws", "SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t",
        "SOIL_MOISTURE_t",
    ]
    result: dict[str, Any] = {"populations": {"train": training.num_rows, "recent_validation": validation.num_rows, "test": test.num_rows}, "features": {}}
    for feature in features:
        train_values = _column(training, feature)
        train_range = None
        if train_values is not None:
            finite = np.asarray(train_values, dtype=np.float64)
            finite = finite[np.isfinite(finite)]
            if finite.size:
                train_range = (float(finite.min()), float(finite.max()))
        result["features"][feature] = {}
        for label, table in (("train", training), ("recent_validation", validation), ("test", test)):
            values = _column(table, feature)
            result["features"][feature][label] = (
                {"available": False} if values is None else {"available": True, **_numeric_summary(values, train_range if label != "train" else None)}
            )
    result["mask_state"] = {
        "train": {"available": False, "reason": "training examples are horizon samples, not transplanted mask rows"},
        "recent_validation": {str(k): int(v) for k, v in zip(*np.unique(_column(validation, "mask_state"), return_counts=True), strict=True)},
        "test": {str(k): int(v) for k, v in zip(*np.unique(_column(test, "mask_state"), return_counts=True), strict=True)} if "mask_state" in test.column_names else {"available": False, "reason": "derive from TWS mask is not present in saved feature artifact"},
    }
    result["optional_history_missingness"] = {
        "status": "not_yet_available",
        "reason": "P3-M2 optional-history features have not been constructed; no P3-M1/M2 results were inspected",
    }
    return result


def _prediction_table(validation: pa.Table, predictions: np.ndarray, model_name: str, config_id: str) -> pa.Table:
    data = validation.to_pydict()
    data.update({
        "prediction": predictions.astype(np.float64), "model_name": [model_name] * validation.num_rows,
        "configuration_id": [config_id] * validation.num_rows, **{key: [value] * validation.num_rows for key, value in POLICIES.items()},
    })
    columns = ["fold_id", "location_id", "input_month", "target_month", "effective_horizon", "mask_state", "prediction", "validation_actual", "model_name", "configuration_id", "latitude", "SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t", *POLICIES]
    return pa.table({column: data[column] for column in columns})


def _metrics(table: pa.Table) -> dict[str, Any]:
    actual = np.asarray(_column(table, "validation_actual"), dtype=np.float64)
    prediction = np.asarray(_column(table, "prediction"), dtype=np.float64)
    if actual.shape != prediction.shape or not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        raise ValidationError("metric inputs must have equal shape and finite complete values")
    squared_error = np.square(prediction - actual)

    def metric(mask: np.ndarray | None = None) -> dict[str, Any]:
        selected = squared_error if mask is None else squared_error[mask]
        return {"count": int(selected.size), "rmse": None if not selected.size else float(np.sqrt(selected.mean()))}

    horizon = np.asarray(_column(table, "effective_horizon"), dtype=np.int8)
    mask_state = np.asarray(_column(table, "mask_state")).astype(str)
    fold_ids = np.asarray(_column(table, "fold_id")).astype(str)
    latitude = np.asarray(_column(table, "latitude"), dtype=np.float64)
    latitude_labels = np.select(
        [latitude < -60, latitude < -30, latitude < 0, latitude < 30, latitude < 60],
        LATITUDE_BANDS[:5], default=LATITUDE_BANDS[5],
    )
    result: dict[str, Any] = {
        "pooled": metric(),
        "fold": {value: metric(fold_ids == value) for value in sorted(set(fold_ids))},
        "horizon": {str(value): metric(horizon == value) for value in range(1, 8)},
        "mask_state": {value: metric(mask_state == value) for value in ("observed", "masked/unavailable")},
        "latitude_band": {value: metric(latitude_labels == value) for value in LATITUDE_BANDS},
        "spei": {},
    }
    for column in ("SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t"):
        values = np.asarray(_column(table, column), dtype=np.float64)
        labels = np.select(
            [values < -2, values < -1.5, values < -1, values < 1, values < 1.5, values < 2],
            SPEI_BINS[:6], default=SPEI_BINS[6],
        )
        result["spei"][column] = {value: metric(labels == value) for value in SPEI_BINS}
    return result


def run(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    outputs = {key: Path(value) for key, value in config["output"].items()}
    if any(path.exists() for path in outputs.values()):
        raise ValidationError("refusing to overwrite or repeat P3-D1")
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    Path(config["resources"]["spill_directory"]).mkdir(parents=True, exist_ok=True)
    load_model_config(Path(config["sources"]["phase2d_config"]))
    origin = date.fromisoformat(str(config["historical_origin"]))
    started = datetime.now(UTC).replace(microsecond=0)
    start = time.perf_counter()
    stage: dict[str, Any] = {}
    peak = 0
    connection = duckdb.connect(":memory:")
    configure_connection(connection, threads=2, memory_limit="2GB")
    connection.execute("SET temp_directory=?", [str(Path(config["resources"]["spill_directory"]).resolve())])
    quoted_train = str(Path(config["sources"]["train_cache"]).resolve()).replace("'", "''")
    quoted_test = str(Path(config["sources"]["test_cache"]).resolve()).replace("'", "''")
    connection.execute(f"CREATE VIEW train_data AS SELECT * FROM read_parquet('{quoted_train}')")
    connection.execute(f"CREATE VIEW test_data AS SELECT * FROM read_parquet('{quoted_test}')")
    try:
        begin = time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            latest = connection.execute("SELECT max(time) FROM train_data").fetchone()[0]
            if latest != date.fromisoformat(str(config["latest_train_month"])) or origin != date(2014, 10, 1):
                raise ValidationError("registered recent block no longer matches source calendar")
            training = pq.read_table(Path(config["sources"]["phase2c_training"]), filters=[("fold_id", "=", "F02")])
            phase2c_manifest = json.loads(Path(config["sources"]["phase2c_manifest"]).read_text(encoding="utf-8"))
            expected_training_rows = sum(map(int, phase2c_manifest["retained_by_fold_horizon"]["F02"].values()))
            if training.num_rows != expected_training_rows or training.num_rows != int(config["sampling"]["cap"]):
                raise ValidationError("stored Phase 2 F02 training sample is incomplete")
            model = lgb.Booster(model_file=str(Path(config["sources"]["phase2d_f02_model"])))
        peak = max(peak, monitor.peak_bytes); stage["stored_artifact_load"] = {"runtime_seconds": time.perf_counter()-begin, "peak_memory_mb": monitor.peak_bytes/1024**2}

        begin = time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            connection.execute("""
                CREATE TEMP TABLE p3d1_validation AS
                WITH keyed AS (
                  SELECT round(lat*2)::BIGINT lat2,round(lon*2)::BIGINT lon2,* FROM train_data
                ), history AS (
                  SELECT lat2,lon2,count(*) FILTER(WHERE TWS_t IS NOT NULL) observations,
                    date_diff('month',min(time) FILTER(WHERE TWS_t IS NOT NULL),
                      max(time) FILTER(WHERE TWS_t IS NOT NULL)) span_months
                  FROM keyed WHERE time<DATE '2014-10-01' GROUP BY 1,2
                )
                SELECT 'P3-D1'::VARCHAR fold_id,
                  'lat2='||k.lat2::VARCHAR||';lon2='||k.lon2::VARCHAR location_id,
                  k.time::DATE input_month,(k.time+INTERVAL 1 MONTH)::DATE target_month,
                  1::INTEGER effective_horizon,'observed'::VARCHAR mask_state,
                  k.target::DOUBLE validation_actual,k.TWS_t::DOUBLE last_observed_tws,
                  k.lat::DOUBLE latitude,k.lon::DOUBLE longitude,
                  year(k.time)::INTEGER input_year,month(k.time)::INTEGER input_calendar_month,
                  k.month_sin::DOUBLE month_sin,k.month_cos::DOUBLE month_cos,
                  k.SPEI_01_t::DOUBLE SPEI_01_t,k.SPEI_03_t::DOUBLE SPEI_03_t,
                  k.SPEI_06_t::DOUBLE SPEI_06_t,k.SPEI_12_t::DOUBLE SPEI_12_t,
                  k.SOIL_MOISTURE_t::DOUBLE SOIL_MOISTURE_t
                FROM keyed k JOIN history h USING(lat2,lon2)
                WHERE k.time BETWEEN DATE '2014-10-01' AND DATE '2015-07-01'
                  AND k.target IS NOT NULL AND k.TWS_t IS NOT NULL
                  AND h.observations>=12 AND h.span_months>=12
                ORDER BY fold_id,location_id,input_month,target_month
            """)
            validation = connection.execute("SELECT * FROM p3d1_validation ORDER BY fold_id,location_id,input_month,target_month").to_arrow_table()
            if validation.num_rows != int(config["expected_recent_rows"]):
                raise ValidationError("recent population differs from preregistration")
            lightgbm_predictions = np.asarray(model.predict(arrow_matrix(validation, APPROVED_FEATURES), num_threads=2), dtype=np.float64)
            persistence_predictions = np.asarray(_column(validation, "last_observed_tws"), dtype=np.float64)
            config_id = _sha256(config_path)
            lightgbm_table = _prediction_table(validation, lightgbm_predictions, "phase2_fixed_lightgbm", config_id)
            persistence_table = _prediction_table(validation, persistence_predictions, "persistence", config_id)
            pq.write_table(lightgbm_table, outputs["lightgbm_predictions"], compression="zstd")
            pq.write_table(persistence_table, outputs["persistence_predictions"], compression="zstd")
        peak = max(peak, monitor.peak_bytes); stage["evaluation"] = {"runtime_seconds": time.perf_counter()-begin, "peak_memory_mb": monitor.peak_bytes/1024**2}

        begin = time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            test_features = pq.read_table(Path(config["sources"]["phase2g_test_features"]))
            drift = _distribution_evidence(training, validation, test_features)
            phase2_oof = pq.read_table(Path(config["sources"]["phase2d_oof"]), columns=["prediction"])
            test_predictions = pq.read_table(Path(config["sources"]["phase2g_test_predictions"]))
            test_prediction_column = "Target" if "Target" in test_predictions.column_names else "prediction"
            drift["prediction_distributions"] = {
                "validation_v1_phase2_lightgbm": _numeric_summary(_column(phase2_oof, "prediction")),
                "recent_period_phase2_lightgbm": _numeric_summary(lightgbm_predictions),
                "test_phase2_lightgbm": _numeric_summary(_column(test_predictions, test_prediction_column)),
            }
            drift["scope_notes"] = {
                "validation_v1": "Stored OOF artifact supplies prediction, horizon, mask, latitude and SPEI evidence; absent feature columns are not reconstructed.",
                "test_targets": "not accessed and unavailable",
                "hidden_target_inference": "prohibited",
            }
            _write_json_atomic(outputs["drift"], drift)
        peak = max(peak, monitor.peak_bytes); stage["drift_audit"] = {"runtime_seconds": time.perf_counter()-begin, "peak_memory_mb": monitor.peak_bytes/1024**2}

        payload = {
            "schema_version": "phase3d1-metrics-v1", "experiment_id": "P3-D1", "execution_count": 1,
            "started_utc": started.isoformat().replace("+00:00", "Z"), "configuration_id": _sha256(config_path),
            "design": {"historical_origin": origin.isoformat(), "input_range": [origin.isoformat(), "2015-07-01"], "target_range": ["2014-11-01", "2015-08-01"], "latest_feasible": True, "structure": "observed-only horizon-1 consecutive Train panel", "diagnostic_role": "secondary_only", "cannot_replace_validation_v1": True},
            "population": {"retained_rows": validation.num_rows, "retained_locations": int(config["expected_recent_locations"]), "horizon_counts": {"1": validation.num_rows, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0}, "mask_counts": {"observed": validation.num_rows, "masked/unavailable": 0}, "training_rows": training.num_rows, "training_source_fold": "F02"},
            "metrics": {"lightgbm": _metrics(lightgbm_table), "persistence": _metrics(persistence_table)},
            "coverage": {"lightgbm": validation.num_rows, "persistence": validation.num_rows, "expected_recent_population": validation.num_rows, "complete": True},
            "runtime_seconds": time.perf_counter()-start, "peak_memory_mb": peak/1024**2, "stages": stage,
            "identities": {**config["identities"], "phase2d_f02_model": _sha256(Path(config["sources"]["phase2d_f02_model"])), "phase2c_training": _sha256(Path(config["sources"]["phase2c_training"]))},
            "artifacts": {key: _artifact(path) for key, path in outputs.items() if key != "metrics"},
            "validation_v1_modified": False, "other_experiments_run": [], "submission_generated": False,
        }
        _write_json_atomic(outputs["metrics"], payload)
        return payload
    except BaseException:
        for path in outputs.values():
            path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/phase3d1_recent_diagnostic.yaml"))
    args = parser.parse_args(argv)
    result = run(args.config)
    print(json.dumps({"experiment_id": result["experiment_id"], "metrics": result["metrics"], "coverage": result["coverage"], "runtime_seconds": result["runtime_seconds"], "peak_memory_mb": result["peak_memory_mb"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
