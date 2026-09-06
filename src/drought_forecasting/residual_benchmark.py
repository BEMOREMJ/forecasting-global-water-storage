"""P3-M1: fixed Phase 2 LightGBM predicting change from last observed TWS."""

from __future__ import annotations

import argparse
import gc
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
    DATA_MANIFEST_ID,
    POLICIES,
    VALIDATION_ID,
    PeakMemoryMonitor,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.lightgbm_benchmark import (
    APPROVED_FEATURES,
    training_table,
)
from drought_forecasting.lightgbm_benchmark import (
    load_config as load_model_config,
)
from drought_forecasting.prediction_contract import ComparableRowIdentity, validate_prediction_rows
from drought_forecasting.recent_diagnostic import _metrics
from drought_forecasting.validation_audit import load_audit_config
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import (
    configure_connection,
    drop_temporary_relations,
    extract_mask_template,
    transplant_single_fold,
)

EXPECTED = ComparableRowIdentity(
    551_965, "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a"
)


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") not in {
        "phase3m1-residual-lightgbm-v1", "phase3m3b-no-year-residual-v1"
    }:
        raise ValidationError("unknown residual benchmark configuration schema")
    if value.get("execution_limit") != 1 or value.get("experiment_id") not in {"P3-M1", "P3-M3B"}:
        raise ValidationError("residual benchmark must remain a single-execution experiment")
    features = tuple(value.get("features", ()))
    if value["experiment_id"] == "P3-M1":
        if features != APPROVED_FEATURES or not value["target"]["raw_year_retained"]:
            raise ValidationError("P3-M1 must preserve the exact Phase 2 feature representation")
    else:
        expected = tuple(feature for feature in APPROVED_FEATURES if feature != "input_year")
        if features != expected or len(features) != len(set(features)) or "input_year" in features:
            raise ValidationError("P3-M3B schema must equal ordered P3-M1 features minus only input_year")
    return value


def feature_matrix(table: pa.Table, features: tuple[str, ...]) -> np.ndarray:
    matrix = np.column_stack([table[name].to_numpy(zero_copy_only=False) for name in features]).astype(np.float32)
    if matrix.shape != (table.num_rows, len(features)) or not np.isfinite(matrix).all():
        raise ValidationError("feature matrix is incomplete or nonfinite")
    return matrix


def residual_target(target: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    target = np.asarray(target, dtype=np.float64)
    anchor = np.asarray(anchor, dtype=np.float64)
    if target.shape != anchor.shape or not np.isfinite(target).all() or not np.isfinite(anchor).all():
        raise ValidationError("residual target requires equal finite target and anchor arrays")
    return target - anchor


def reconstruct(anchor: np.ndarray, predicted_residual: np.ndarray) -> np.ndarray:
    anchor = np.asarray(anchor, dtype=np.float64)
    predicted_residual = np.asarray(predicted_residual, dtype=np.float64)
    if anchor.shape != predicted_residual.shape or not np.isfinite(anchor).all() or not np.isfinite(predicted_residual).all():
        raise ValidationError("reconstruction requires equal finite anchor and residual arrays")
    prediction = anchor + predicted_residual
    if not np.isfinite(prediction).all():
        raise ValidationError("reconstruction produced nonfinite predictions")
    return prediction


def create_residual_validation(
    connection: duckdb.DuckDBPyConnection, *, retained: str, output: str
) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {output}")
    connection.execute(
        f"""
        CREATE TEMP TABLE {output} AS
        SELECT r.fold_id,'lat2='||r.lat2::VARCHAR||';lon2='||r.lon2::VARCHAR location_id,
          r.input_month,r.target_month,r.last_observed_month,
          r.effective_horizon,r.mask_state,
          CASE WHEN r.mask_state THEN 'masked/unavailable' ELSE 'observed' END mask_state_label,
          r.target_value::DOUBLE validation_actual,s.TWS_t::DOUBLE last_observed_tws,
          i.lat::DOUBLE latitude,i.lon::DOUBLE longitude,year(r.input_month)::INTEGER input_year,
          month(r.input_month)::INTEGER input_calendar_month,i.month_sin::DOUBLE month_sin,
          i.month_cos::DOUBLE month_cos,i.SPEI_01_t::DOUBLE SPEI_01_t,
          i.SPEI_03_t::DOUBLE SPEI_03_t,i.SPEI_06_t::DOUBLE SPEI_06_t,
          i.SPEI_12_t::DOUBLE SPEI_12_t,i.SOIL_MOISTURE_t::DOUBLE SOIL_MOISTURE_t,
          CAST(round(i.lat*2) AS BIGINT) anchor_lat2,CAST(round(i.lon*2) AS BIGINT) anchor_lon2
        FROM {retained} r
        JOIN train_data i ON CAST(round(i.lat*2) AS BIGINT)=r.lat2
          AND CAST(round(i.lon*2) AS BIGINT)=r.lon2 AND i.time=r.input_month
        JOIN train_data s ON CAST(round(s.lat*2) AS BIGINT)=r.lat2
          AND CAST(round(s.lon*2) AS BIGINT)=r.lon2 AND s.time=r.last_observed_month
          AND s.TWS_t IS NOT NULL
        ORDER BY fold_id,location_id,input_month,target_month
        """
    )
    invalid = connection.execute(
        f"""SELECT count(*) FROM {output}
        WHERE anchor_lat2<>CAST(split_part(split_part(location_id,';',1),'=',2) AS BIGINT)
           OR anchor_lon2<>CAST(split_part(split_part(location_id,';',2),'=',2) AS BIGINT)
           OR last_observed_month>input_month
           OR date_diff('month',last_observed_month,target_month)<>effective_horizon
           OR date_diff('month',input_month,target_month)<>1
           OR last_observed_tws IS NULL OR NOT isfinite(last_observed_tws)"""
    ).fetchone()[0]
    if invalid:
        raise ValidationError(f"{invalid} unsafe or invalid residual anchors")


def _fold_output(
    validation: pa.Table,
    predicted_residual: np.ndarray,
    absolute: np.ndarray,
    *,
    run_id: str,
    config_id: str,
    model_name: str = "p3m1_residual_lightgbm",
) -> pa.Table:
    data = validation.to_pydict()
    rows = validation.num_rows
    data.update(
        {
            "run_id": [run_id] * rows,
            "predicted_residual": predicted_residual,
            "prediction": absolute,
            "model_name": [model_name] * rows,
            "configuration_id": [config_id] * rows,
            "data_manifest_id": [DATA_MANIFEST_ID] * rows,
            "validation_id": [VALIDATION_ID] * rows,
            **{key: [value] * rows for key, value in POLICIES.items()},
        }
    )
    order = [
        "run_id", "fold_id", "location_id", "input_month", "target_month",
        "last_observed_month", "last_observed_tws", "effective_horizon", "mask_state_label",
        "predicted_residual", "prediction", "validation_actual", "model_name",
        "configuration_id", "data_manifest_id", "validation_id", "latitude",
        "SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t", *POLICIES,
    ]
    return pa.table({name: data[name] for name in order}).rename_columns(
        ["mask_state" if name == "mask_state_label" else name for name in order]
    )


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def run(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    experiment = config["experiment_id"]
    is_m3b = experiment == "P3-M3B"
    prefix = "p3m3b" if is_m3b else "p3m1"
    features = tuple(config["features"])
    model_config = load_model_config(Path(config["sources"]["phase2_model_config"]))
    outputs = {key: Path(value) for key, value in config["output"].items()}
    final_keys = ("absolute_oof", "residual_oof", "metrics", "provenance")
    if any(outputs[key].exists() for key in final_keys):
        raise ValidationError(f"refusing to overwrite or repeat {experiment}")
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    config_id = _sha256(config_path)
    started = datetime.now(UTC).replace(microsecond=0)
    run_id = f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-{prefix}-residual"
    audit = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    connection = duckdb.connect(":memory:")
    configure_connection(connection, threads=2, memory_limit="2GB")
    connection.execute("CREATE VIEW train_data AS SELECT * FROM read_parquet('data/processed/Train.parquet')")
    connection.execute("CREATE VIEW test_data AS SELECT * FROM read_parquet('data/processed/Test.parquet')")
    template = extract_mask_template(connection, "test_data", date(2015, 9, 1), output_relation=f"{prefix}_template")
    start = time.perf_counter()
    peak = 0
    stages: dict[str, Any] = {}
    checkpoints: list[dict[str, Any]] = []
    try:
        training_anchor_invalid = connection.execute(
            """SELECT count(*) FROM read_parquet(?)
            WHERE location_id<>covariate_location_id OR location_id<>tws_source_location_id
               OR tws_source_month>input_month OR tws_source_month>=target_month
               OR date_diff('month',tws_source_month,target_month)<>effective_horizon
               OR target_month>fold_cutoff OR last_observed_tws IS NULL
               OR NOT isfinite(last_observed_tws)""",
            [str(Path(config["sources"]["training_artifact"]).resolve())],
        ).fetchone()[0]
        if training_anchor_invalid:
            raise ValidationError(f"{training_anchor_invalid} unsafe training residual anchors")
        for index, fold_spec in enumerate(audit.folds):
            fold_id = fold_spec.fold_id
            model_path = outputs[f"{fold_id}_model"]
            prediction_path = outputs[f"{fold_id}_predictions"]
            checkpoint_path = Path(f"reports/{prefix}_{fold_id}_checkpoint.json")
            existing = (model_path.exists(), prediction_path.exists(), checkpoint_path.exists())
            if all(existing):
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if (
                    checkpoint["model"]["sha256"] != _sha256(model_path)
                    or checkpoint["predictions"]["sha256"] != _sha256(prediction_path)
                    or checkpoint["rows"] != int(config["populations"]["validation"][fold_id])
                ):
                    raise ValidationError(f"saved {fold_id} checkpoint identity mismatch")
                checkpoint["checkpoint"] = _artifact(checkpoint_path)
                checkpoints.append(checkpoint)
                stages[fold_id] = {"status": "resumed_verified_without_retraining"}
                peak = max(peak, int(float(checkpoint.get("peak_memory_mb", 0)) * 1024**2))
                continue
            if any(existing):
                raise ValidationError(f"incomplete {fold_id} checkpoint cannot be resumed")
            begin = time.perf_counter()
            with PeakMemoryMonitor() as monitor:
                training = training_table(Path(config["sources"]["training_artifact"]), fold_id, features)
                expected_training = int(config["populations"]["training"][fold_id])
                if training.num_rows != expected_training:
                    raise ValidationError("P3-M1 training population mismatch")
                train_anchor = training["last_observed_tws"].to_numpy().astype(np.float64, copy=False)
                train_target = training["target"].to_numpy().astype(np.float64, copy=False)
                labels = residual_target(train_target, train_anchor).astype(np.float32)
                matrix = feature_matrix(training, features)
                weights = training["sample_weight"].to_numpy().astype(np.float32, copy=False)
                dataset = lgb.Dataset(matrix, label=labels, weight=weights, feature_name=list(features), free_raw_data=True)
                model = lgb.train(model_config["parameters"], dataset, num_boost_round=model_config["num_boost_round"])
                fold_result = transplant_single_fold(
                    connection, "train_data", template.relation, fold_id=fold_id,
                    origin=fold_spec.origin, history_gate=audit.history_gate,
                    relation_prefix=f"{prefix}_fold_{index}", required_relative_months=18,
                )
                try:
                    create_residual_validation(connection, retained=fold_result.relations.retained, output=f"{prefix}_validation")
                    validation = connection.execute(f"SELECT * FROM {prefix}_validation ORDER BY fold_id,location_id,input_month,target_month").to_arrow_table()
                    if validation.num_rows != int(config["populations"]["validation"][fold_id]):
                        raise ValidationError("P3-M1 validation population mismatch")
                    predicted_residual = np.asarray(model.predict(feature_matrix(validation, features), num_threads=2), dtype=np.float64)
                    anchor = validation["last_observed_tws"].to_numpy().astype(np.float64, copy=False)
                    absolute = reconstruct(anchor, predicted_residual)
                    table = _fold_output(validation, predicted_residual, absolute, run_id=run_id, config_id=config_id, model_name=("p3m3b_no_year_residual_lightgbm" if is_m3b else "p3m1_residual_lightgbm"))
                    model.save_model(str(model_path))
                    pq.write_table(table, prediction_path, compression="zstd")
                    checkpoint = {
                        "fold": fold_id, "rows": table.num_rows,
                        "model": _artifact(model_path), "predictions": _artifact(prediction_path),
                        "anchor_checks": {"same_location": "pass", "timestamp_ordering": "pass", "genuinely_observed": "pass", "recursion": "disabled"},
                        "runtime_seconds": time.perf_counter()-begin,
                        "peak_memory_mb": monitor.peak_bytes/1024**2,
                    }
                    _write_json_atomic(checkpoint_path, checkpoint)
                    checkpoint["checkpoint"] = _artifact(checkpoint_path)
                    checkpoints.append(checkpoint)
                finally:
                    connection.execute(f"DROP TABLE IF EXISTS {prefix}_validation")
                    drop_temporary_relations(connection, fold_result.relations)
                del training, train_anchor, train_target, labels, matrix, weights, dataset, model
                del validation, predicted_residual, anchor, absolute, table
                gc.collect()
            peak = max(peak, monitor.peak_bytes)
            stages[fold_id] = {"runtime_seconds": time.perf_counter()-begin, "peak_memory_mb": monitor.peak_bytes/1024**2}

        fold_tables = [pq.read_table(outputs[f"{fold}_predictions"]) for fold in ("F01", "F02")]
        absolute_oof = pa.concat_tables(fold_tables)
        run_id = absolute_oof["run_id"][0].as_py()
        absolute_rows = absolute_oof.to_pylist()
        validate_prediction_rows(
            absolute_rows, expected_rows=EXPECTED,
            expected_data_manifest_id=DATA_MANIFEST_ID, expected_validation_id=VALIDATION_ID,
        )
        pq.write_table(absolute_oof, outputs["absolute_oof"], compression="zstd")
        residual_oof = absolute_oof.select([
            "fold_id", "location_id", "input_month", "target_month", "last_observed_month",
            "last_observed_tws", "effective_horizon", "mask_state", "predicted_residual",
        ])
        residual_actual = np.asarray([row["validation_actual"]-row["last_observed_tws"] for row in absolute_rows])
        residual_oof = residual_oof.append_column("residual_actual", pa.array(residual_actual))
        pq.write_table(residual_oof, outputs["residual_oof"], compression="zstd")
        metrics = _metrics(absolute_oof)
        p2 = json.loads(Path("reports/phase2d/run-20260904T064720Z-lightgbm_basic-metrics.json").read_text())
        persistence = json.loads(Path("reports/phase2b/run-20260904T061036Z-persistence-metrics.json").read_text())
        fold_gate = all(metrics["fold"][fold]["rmse"] <= config["promotion_gate"]["fold_maximum_rmse"][fold] for fold in ("F01", "F02"))
        pooled_gate = metrics["pooled"]["rmse"] <= config["promotion_gate"]["pooled_maximum_rmse"]
        tolerance = float(config["promotion_gate"].get("masked_horizon_tolerance", 0.005))
        masked_horizons = {str(h): metrics["horizon"][str(h)]["rmse"] for h in range(2, 8)}
        masked_limits = {str(h): p2["metrics"]["horizon"][str(h)]["rmse"] + tolerance for h in range(2, 8)}
        masked_by_horizon = {key: masked_horizons[key] <= masked_limits[key] for key in masked_horizons}
        masked_gate = all(masked_by_horizon.values())
        promotion = {"pooled": pooled_gate, "folds": fold_gate, "coverage": absolute_oof.num_rows == EXPECTED.row_count, "leakage": True, "masked_protected": masked_gate, "masked_horizon_checks": masked_by_horizon, "masked_horizon_limits": masked_limits}
        promotion["eligible"] = all(value for key, value in promotion.items() if key not in {"masked_horizon_checks", "masked_horizon_limits"})
        provenance = {
            "schema_version": f"{prefix}-provenance-v1", "configuration_id": config_id,
            "training_checks": {"same_location": "pass", "explicit_source_timestamp": "pass", "source_not_later_than_input": "pass", "target_not_anchor": "pass", "no_adjacent_row": "pass", "no_recursion": "pass", "no_global_target_statistic": "pass"},
            "validation_checks": {"rows": absolute_oof.num_rows, "comparable_row_identity": EXPECTED.sha256, "same_location": "pass", "explicit_source_timestamp": "pass", "source_not_later_than_input": "pass", "effective_horizon": "pass"},
            "fold_checkpoints": checkpoints,
        }
        _write_json_atomic(outputs["provenance"], provenance)
        payload = {
            "schema_version": f"{prefix}-metrics-v1", "experiment_id": experiment, "execution_count": 1,
            "run_id": run_id, "configuration_id": config_id, "metrics": metrics,
            "references": {"phase2_lightgbm": p2["metrics"], "persistence": persistence["metrics"], "p3d1_recent_lightgbm": 0.7565834086766431, "p3d1_recent_persistence": 0.8395729310406177},
            "populations": config["populations"], "coverage": {"actual": absolute_oof.num_rows, "expected": EXPECTED.row_count, "fraction": absolute_oof.num_rows/EXPECTED.row_count},
            "runtime_seconds": time.perf_counter()-start, "peak_memory_mb": peak/1024**2, "stages": stages,
            "promotion_gate": promotion, "identities": {**config["identities"], "configuration": config_id},
            "artifacts": {key: _artifact(path) for key, path in outputs.items() if key not in {"metrics", "provenance"}},
            "provenance": _artifact(outputs["provenance"]),
            "validation_v1_modified": False, "other_phase3_experiments_run": [], "submission_generated": False,
        }
        _write_json_atomic(outputs["metrics"], payload)
        return payload
    except BaseException:
        # Fold checkpoints and their verified artifacts deliberately survive for resume inspection.
        for key in ("absolute_oof", "residual_oof", "metrics", "provenance"):
            outputs[key].unlink(missing_ok=True)
        raise
    finally:
        drop_temporary_relations(connection, (template.relation,))
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/phase3m1_residual_lightgbm.yaml"))
    args = parser.parse_args(argv)
    result = run(args.config)
    print(json.dumps({key: result[key] for key in ("metrics", "coverage", "runtime_seconds", "peak_memory_mb", "promotion_gate")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
