"""One fixed, fold-local, deterministic Phase 2D LightGBM benchmark."""

from __future__ import annotations

import argparse
import gc
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from drought_forecasting.deterministic_baselines import (
    DATA_MANIFEST_ID,
    EXPECTED_ROWS,
    POLICIES,
    VALIDATION_ID,
    PeakMemoryMonitor,
    _metric_report,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.experiment_registry import FIELDS, add_record
from drought_forecasting.prediction_contract import (
    ComparableRowIdentity,
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
from drought_forecasting.validation_metrics import build_metric_report

APPROVED_FEATURES = (
    "last_observed_tws",
    "effective_horizon",
    "latitude",
    "longitude",
    "input_year",
    "input_calendar_month",
    "month_sin",
    "month_cos",
    "SPEI_01_t",
    "SPEI_03_t",
    "SPEI_06_t",
    "SPEI_12_t",
    "SOIL_MOISTURE_t",
)
COMPARABLE_ID = "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a"
PHASE2C_ID = "ac6e737441d115475f8062d2e53bff57b16d4d8b3786aa54f8ac9a34866dd05e"
PHASE2C_TARGET_ID = "4e1fc3745b754ae0020e111fa0d4e65afd3daf8b63034b7095340d3dc15fe95d"
PHASE2C_ARTIFACT_ID = "078ad361f03159ddd5b1f1f0a30e311d261ce82e1ab938d4e56cf56e2885e31b"


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "phase2d-lightgbm-v1":
        raise ValidationError("unknown Phase 2D configuration schema")
    validate_feature_list(value.get("features"))
    parameters = value.get("parameters")
    required = {
        "objective": "regression",
        "metric": "rmse",
        "boosting_type": "gbdt",
        "seed": 20260904,
        "deterministic": True,
        "force_col_wise": True,
        "num_threads": 2,
        "use_missing": True,
        "zero_as_missing": False,
        "verbosity": -1,
    }
    if not isinstance(parameters, dict) or any(parameters.get(key) != wanted for key, wanted in required.items()):
        raise ValidationError("LightGBM safety parameters differ from the frozen requirements")
    if value.get("num_boost_round") != 200:
        raise ValidationError("Phase 2D requires exactly 200 fixed boosting rounds")
    return value


def validate_feature_list(features: Any) -> tuple[str, ...]:
    if not isinstance(features, list) or tuple(features) != APPROVED_FEATURES:
        extra = set(features or ()).difference(APPROVED_FEATURES)
        if extra:
            raise ValidationError(f"unapproved LightGBM features: {sorted(extra)}")
        raise ValidationError("LightGBM features must exactly preserve approved ordering")
    return tuple(features)


def arrow_matrix(table: pa.Table, features: Sequence[str]) -> np.ndarray:
    if tuple(features) != APPROVED_FEATURES:
        validate_feature_list(list(features))
    missing = set(features).difference(table.column_names)
    if missing:
        raise ValidationError(f"feature table is missing columns: {sorted(missing)}")
    matrix = np.column_stack(
        [table[column].combine_chunks().to_numpy(zero_copy_only=False) for column in features]
    ).astype(np.float32, copy=False)
    if matrix.shape != (table.num_rows, len(features)):
        raise ValidationError("feature matrix shape is invalid")
    if not np.isfinite(matrix).all():
        raise ValidationError("feature matrix contains nonfinite values")
    return matrix


def training_table(path: Path, fold_id: str, features: Sequence[str]) -> pa.Table:
    if fold_id not in {"F01", "F02"}:
        raise ValidationError("unknown training fold")
    columns = [*features, "target", "sample_weight", "effective_horizon", "fold_id"]
    table = pq.read_table(path, columns=list(dict.fromkeys(columns)), filters=[("fold_id", "=", fold_id)])
    if not table.num_rows or not pc.all(pc.equal(table["fold_id"], fold_id)).as_py():
        raise ValidationError("fold-local training separation failed")
    return table


def create_validation_features(
    connection: duckdb.DuckDBPyConnection,
    *,
    retained_relation: str,
    output_relation: str,
    train_relation: str = "train_data",
) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {output_relation}")
    connection.execute(
        f"""
        CREATE TEMP TABLE {output_relation} AS
        SELECT
            r.fold_id,
            'lat2=' || r.lat2::VARCHAR || ';lon2=' || r.lon2::VARCHAR AS location_id,
            r.input_month, r.target_month, r.effective_horizon,
            CASE WHEN r.mask_state THEN 'masked/unavailable' ELSE 'observed' END AS mask_state,
            r.target_value AS validation_actual,
            s.TWS_t AS last_observed_tws,
            i.lat AS latitude, i.lon AS longitude,
            year(r.input_month)::INTEGER AS input_year,
            month(r.input_month)::INTEGER AS input_calendar_month,
            i.month_sin, i.month_cos, i.SPEI_01_t, i.SPEI_03_t,
            i.SPEI_06_t, i.SPEI_12_t, i.SOIL_MOISTURE_t
        FROM {retained_relation} r
        JOIN {train_relation} i
          ON CAST(round(i.lat*2) AS BIGINT)=r.lat2
         AND CAST(round(i.lon*2) AS BIGINT)=r.lon2
         AND i.time=r.input_month
        JOIN {train_relation} s
          ON CAST(round(s.lat*2) AS BIGINT)=r.lat2
         AND CAST(round(s.lon*2) AS BIGINT)=r.lon2
         AND s.time=r.last_observed_month
         AND s.time <= r.input_month
         AND date_diff('month', s.time, r.target_month)=r.effective_horizon
        ORDER BY fold_id, location_id, input_month, target_month
        """
    )
    invalid = connection.execute(
        f"""
        SELECT count(*) FROM {output_relation}
        WHERE date_diff('month', input_month,target_month)<>1
           OR date_diff('month', input_month + INTERVAL (1-effective_horizon) MONTH,target_month)
              <> effective_horizon
           OR last_observed_tws IS NULL OR NOT isfinite(last_observed_tws)
        """
    ).fetchone()[0]
    if invalid:
        raise ValidationError("validation feature provenance is invalid")


def train_fixture_model(
    features: np.ndarray, target: np.ndarray, parameters: Mapping[str, Any], rounds: int
) -> np.ndarray:
    dataset = lgb.Dataset(features, label=target, free_raw_data=False)
    model = lgb.train(dict(parameters), dataset, num_boost_round=rounds)
    prediction = model.predict(features, num_threads=2)
    if not np.isfinite(prediction).all():
        raise ValidationError("LightGBM produced nonfinite predictions")
    return prediction


def _prediction_table(
    validation: pa.Table,
    predictions: np.ndarray,
    *,
    run_id: str,
    configuration_id: str,
) -> pa.Table:
    if len(predictions) != validation.num_rows or not np.isfinite(predictions).all():
        raise ValidationError("prediction coverage or finiteness failure")
    data = validation.to_pydict()
    rows = validation.num_rows
    data.update(
        {
            "run_id": [run_id] * rows,
            "prediction": predictions.astype(np.float64),
            "model_name": ["lightgbm_basic"] * rows,
            "configuration_id": [configuration_id] * rows,
            "data_manifest_id": [DATA_MANIFEST_ID] * rows,
            "validation_id": [VALIDATION_ID] * rows,
            **{key: [value] * rows for key, value in POLICIES.items()},
        }
    )
    ordered = [
        "run_id", "fold_id", "location_id", "input_month", "target_month",
        "effective_horizon", "mask_state", "prediction", "validation_actual", "model_name",
        "configuration_id", "data_manifest_id", "validation_id", "latitude",
        "SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t", *POLICIES,
    ]
    return pa.table({column: data[column] for column in ordered})


def registry_record(payload: Mapping[str, Any], started_at: datetime) -> dict[str, str]:
    record = {field: "" for field in FIELDS}
    metrics = payload["metrics"]
    record.update(
        {
            "run_id": str(payload["run_id"]),
            "run_date_utc": started_at.isoformat().replace("+00:00", "Z"),
            "git_commit": "b3003209ec29c860498a93bf5163784fe720a64c",
            "data_version": DATA_MANIFEST_ID,
            "validation_version": "validation-v1",
            "seed": "20260904",
            "features": json.dumps(payload["features"]),
            "model": "lightgbm_basic",
            "model_parameters": json.dumps(payload["configuration"], sort_keys=True),
            "overall_cv_rmse": str(metrics["pooled"]["rmse"]),
            "rmse_by_horizon": json.dumps(metrics["horizon"], sort_keys=True),
            "regional_or_subgroup_metrics": json.dumps(
                {key: metrics[key] for key in ("fold", "mask_state", "latitude_band", "spei")}
                | {"coverage": payload["coverage"]}, sort_keys=True
            ),
            "runtime_seconds": str(payload["runtime_seconds"]),
            "peak_memory_mb": str(payload["peak_memory_mb"]),
            "model_size_mb": str(sum(item["size_bytes"] for item in payload["models"].values()) / 1024**2),
            "artifact_paths": json.dumps([payload["metrics_path"], payload["oof"]["path"], *[item["path"] for item in payload["models"].values()]]),
            "decision": str(payload["decision"]),
            "decision_reason": str(payload["decision_reason"]),
            "notes": f"OOF sha256={payload['oof']['sha256']}; Phase2C={PHASE2C_ARTIFACT_ID}",
        }
    )
    return record


def run_benchmark(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    configuration_id = canonical_sha256(config)
    started_at = datetime.now(UTC).replace(microsecond=0)
    run_id = f"run-{started_at.strftime('%Y%m%dT%H%M%SZ')}-lightgbm_basic"
    artifact_root = Path("artifacts/phase2d")
    model_paths = {fold: artifact_root / f"{run_id}-{fold}.txt" for fold in ("F01", "F02")}
    oof_path = artifact_root / f"{run_id}-oof.parquet"
    metrics_path = Path("reports/phase2d") / f"{run_id}-metrics.json"
    if any(path.exists() for path in [*model_paths.values(), oof_path, metrics_path]):
        raise ValidationError("refusing to overwrite Phase 2D artifacts")
    artifact_root.mkdir(parents=True, exist_ok=True)
    train_path = Path("artifacts/phase2c/horizon_training_examples_v1.parquet")
    audit = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    connection = duckdb.connect(":memory:")
    configure_connection(connection, threads=2, memory_limit="2GB")
    connection.execute("CREATE VIEW train_data AS SELECT * FROM read_parquet('data/processed/Train.parquet')")
    connection.execute("CREATE VIEW test_data AS SELECT * FROM read_parquet('data/processed/Test.parquet')")
    template = extract_mask_template(connection, "test_data", date(2015, 9, 1), output_relation="phase2d_template")
    writer: pq.ParquetWriter | None = None
    start = __import__("time").perf_counter()
    training_counts: dict[str, dict[str, int]] = {}
    try:
        with PeakMemoryMonitor() as memory:
            for index, fold in enumerate(audit.folds):
                training = training_table(train_path, fold.fold_id, config["features"])
                training_counts[fold.fold_id] = {
                    str(h): int(n) for h, n in zip(*np.unique(training["effective_horizon"].to_numpy(), return_counts=True), strict=True)
                }
                matrix = arrow_matrix(training, config["features"])
                labels = training["target"].to_numpy().astype(np.float32, copy=False)
                weights = training["sample_weight"].to_numpy().astype(np.float32, copy=False)
                dataset = lgb.Dataset(matrix, label=labels, weight=weights, feature_name=config["features"], free_raw_data=True)
                model = lgb.train(config["parameters"], dataset, num_boost_round=config["num_boost_round"])
                result = transplant_single_fold(
                    connection, "train_data", template.relation, fold_id=fold.fold_id,
                    origin=fold.origin, history_gate=audit.history_gate,
                    relation_prefix=f"phase2d_fold_{index:03d}", required_relative_months=18,
                )
                try:
                    create_validation_features(connection, retained_relation=result.relations.retained, output_relation="phase2d_validation")
                    validation = connection.execute("SELECT * FROM phase2d_validation ORDER BY fold_id,location_id,input_month,target_month").to_arrow_table()
                    predictions = model.predict(arrow_matrix(validation, config["features"]), num_threads=2)
                    output = _prediction_table(validation, predictions, run_id=run_id, configuration_id=configuration_id)
                    if writer is None:
                        writer = pq.ParquetWriter(oof_path, output.schema, compression="zstd")
                    writer.write_table(output)
                    model.save_model(str(model_paths[fold.fold_id]))
                finally:
                    connection.execute("DROP TABLE IF EXISTS phase2d_validation")
                    drop_temporary_relations(connection, result.relations)
                del model, dataset, matrix, labels, weights, training, validation, predictions, output
                gc.collect()
            if writer is not None:
                writer.close(); writer = None
            rows = pq.read_table(oof_path).to_pylist()
            validate_prediction_rows(
                rows,
                expected_rows=ComparableRowIdentity(EXPECTED_ROWS, COMPARABLE_ID),
                expected_data_manifest_id=DATA_MANIFEST_ID,
                expected_validation_id=VALIDATION_ID,
            )
            metric_rows = [
                {"target": row["validation_actual"], "prediction": row["prediction"],
                 "fold_id": row["fold_id"], "horizon": row["effective_horizon"],
                 "mask_state": row["mask_state"], "latitude": row["latitude"],
                 **{column: row[column] for column in ("SPEI_01_t","SPEI_03_t","SPEI_06_t","SPEI_12_t")}, **POLICIES}
                for row in rows
            ]
            report = build_metric_report(metric_rows)
        runtime = __import__("time").perf_counter() - start
        models = {fold: {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)} for fold, path in model_paths.items()}
        payload: dict[str, Any] = {
            "schema_version": "phase2d-run-metrics-v1", "run_id": run_id,
            "configuration_id": configuration_id, "configuration": config,
            "features": list(APPROVED_FEATURES), "feature_types": {feature: "float32" for feature in APPROVED_FEATURES},
            "feature_missing_counts": {feature: 0 for feature in APPROVED_FEATURES},
            "training_rows_by_fold_horizon": training_counts,
            "identities": {"data_manifest": DATA_MANIFEST_ID, "validation": VALIDATION_ID,
                           "phase2c_artifact": PHASE2C_ARTIFACT_ID, "phase2c_configuration": PHASE2C_ID,
                           "phase2c_retained_targets": PHASE2C_TARGET_ID, "comparable_rows": COMPARABLE_ID},
            "metrics": _metric_report(report),
            "coverage": {"predicted": len(rows), "expected": EXPECTED_ROWS, "fraction": len(rows)/EXPECTED_ROWS},
            "runtime_seconds": runtime, "peak_memory_mb": memory.peak_bytes/1024**2,
            "models": models,
            "oof": {"path": oof_path.as_posix(), "size_bytes": oof_path.stat().st_size, "sha256": _sha256(oof_path)},
            "decision": "keep" if report.pooled.rmse < 0.6737224552267717 else "reject",
            "decision_reason": "fixed benchmark compared against persistence without tuning",
            "metrics_path": metrics_path.as_posix(),
        }
        _write_json_atomic(metrics_path, payload)
        add_record(Path("experiments/registry.csv"), registry_record(payload, started_at))
        return payload
    except BaseException:
        if writer is not None: writer.close()
        oof_path.unlink(missing_ok=True)
        for path in model_paths.values(): path.unlink(missing_ok=True)
        raise
    finally:
        drop_temporary_relations(connection, (template.relation,))
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/phase2d_lightgbm.yaml"))
    args = parser.parse_args(argv)
    result = run_benchmark(args.config)
    print(json.dumps({key: result[key] for key in ("run_id","metrics","coverage","runtime_seconds","peak_memory_mb","models","oof","decision")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
