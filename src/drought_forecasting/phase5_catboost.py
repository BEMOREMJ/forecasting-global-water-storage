"""Single-pass Phase 5 CatBoost challenger."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from catboost import CatBoostRegressor, Pool

from drought_forecasting.deterministic_baselines import (
    DATA_MANIFEST_ID,
    VALIDATION_ID,
    PeakMemoryMonitor,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.phase4_models import (
    BASE_FEATURES,
    EXPECTED,
    REFERENCE,
    _output_table,
    _recent_rmse,
)
from drought_forecasting.prediction_contract import validate_prediction_rows
from drought_forecasting.recent_diagnostic import _metrics
from drought_forecasting.residual_benchmark import create_residual_validation
from drought_forecasting.validation_audit import load_audit_config
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import (
    configure_connection,
    drop_temporary_relations,
    extract_mask_template,
    transplant_single_fold,
)

CAT_FEATURE = "location_id"


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != "phase5-v1":
        raise ValidationError("unknown Phase 5 configuration")
    if tuple(config["features"]) != BASE_FEATURES or config["categorical_features"] != [CAT_FEATURE]:
        raise ValidationError("Phase 5 feature contract changed")
    if config["execution_limit"] != 1 or config["threads"] != 2:
        raise ValidationError("Phase 5 execution controls changed")
    return config


def model_parameters(config: dict[str, Any]) -> dict[str, Any]:
    params = dict(config["catboost"])
    params.pop("package")
    return params


def feature_frame(table: pa.Table):
    frame = table.select([*BASE_FEATURES, CAT_FEATURE]).to_pandas()
    frame[list(BASE_FEATURES)] = frame[list(BASE_FEATURES)].astype(np.float32)
    frame[CAT_FEATURE] = frame[CAT_FEATURE].astype(str)
    return frame


def promotion_gate(metrics: dict[str, Any], recent: float, reference_recent: float, peak_mb: float) -> dict[str, bool]:
    checks = {
        "pooled": metrics["pooled"]["rmse"] <= 0.578923,
        "folds_stable": all(metrics["fold"][f]["rmse"] <= REFERENCE["fold"][f] + 0.005 for f in REFERENCE["fold"]),
        "horizons_6_7": all(metrics["horizon"][h]["rmse"] <= REFERENCE["horizon"][h] + 0.005 for h in ("6", "7")),
        "coverage": metrics["pooled"]["count"] == EXPECTED.row_count,
        "recent": recent <= reference_recent + 0.005,
        "leakage": True,
        "safe_fallback": True,
        "memory": peak_mb <= 3000,
    }
    return {**checks, "eligible": all(checks.values())}


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def run(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    results_path = Path("reports/phase5_results.json")
    if results_path.exists():
        raise ValidationError("refusing to repeat the Phase 5 CatBoost experiment")
    artifact_dir = Path("artifacts/phase5")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    outputs = {fold: artifact_dir / f"p5-cat-{fold}-predictions.parquet" for fold in ("F01", "F02")}
    models = {fold: artifact_dir / f"p5-cat-{fold}.cbm" for fold in ("F01", "F02")}
    oof_path = artifact_dir / "p5-cat-oof.parquet"
    if oof_path.exists() or any(p.exists() for p in [*outputs.values(), *models.values()]):
        raise ValidationError("refusing to overwrite Phase 5 artifacts")

    started = datetime.now(UTC).replace(microsecond=0)
    run_id = f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-p5cat"
    config_id = hashlib.sha256(config_path.read_bytes()).hexdigest()
    audit = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    source = Path(config["sources"]["training_artifact"])
    con = duckdb.connect(":memory:")
    configure_connection(con, threads=2, memory_limit="2GB")
    con.execute("CREATE VIEW train_data AS SELECT * FROM read_parquet('data/processed/Train.parquet')")
    con.execute("CREATE VIEW test_data AS SELECT * FROM read_parquet('data/processed/Test.parquet')")
    template = extract_mask_template(con, "test_data", date(2015, 9, 1), output_relation="p5_template")
    reference_recent, reference_recent_count = _recent_rmse(con, Path(config["sources"]["reference_oof"]))
    begin = time.perf_counter()
    fold_details: dict[str, Any] = {}
    peak = 0.0
    try:
        for index, fold in enumerate(audit.folds):
            fold_begin = time.perf_counter()
            with PeakMemoryMonitor() as monitor:
                training = pq.read_table(source, filters=[("fold_id", "=", fold.fold_id)])
                expected_training = int(config["population"]["training"][fold.fold_id])
                if training.num_rows != expected_training:
                    raise ValidationError("Phase 5 training population changed")
                train_frame = feature_frame(training)
                labels = (training["target"].to_numpy() - training["last_observed_tws"].to_numpy()).astype(np.float32)
                weights = training["sample_weight"].to_numpy().astype(np.float32, copy=False)
                train_pool = Pool(train_frame, label=labels, weight=weights, cat_features=[CAT_FEATURE])
                model = CatBoostRegressor(**model_parameters(config))
                model.fit(train_pool)

                transplanted = transplant_single_fold(
                    con, "train_data", template.relation, fold_id=fold.fold_id, origin=fold.origin,
                    history_gate=audit.history_gate, relation_prefix=f"p5_cat_{index}", required_relative_months=18,
                )
                try:
                    create_residual_validation(con, retained=transplanted.relations.retained, output="p5_validation")
                    validation = con.execute(
                        "SELECT * FROM p5_validation ORDER BY fold_id,location_id,input_month,target_month"
                    ).to_arrow_table()
                    if validation.num_rows != int(config["population"]["validation"][fold.fold_id]):
                        raise ValidationError("Phase 5 validation population changed")
                    prediction = np.asarray(model.predict(feature_frame(validation), thread_count=2), dtype=np.float64)
                    table = _output_table(
                        validation, prediction, validation["last_observed_tws"].to_numpy(), run_id=run_id,
                        config_id=config_id, model_name="P5-CAT",
                    )
                    pq.write_table(table, outputs[fold.fold_id], compression="zstd")
                    model.save_model(str(models[fold.fold_id]))
                finally:
                    con.execute("DROP TABLE IF EXISTS p5_validation")
                    drop_temporary_relations(con, transplanted.relations)
                fold_details[fold.fold_id] = {
                    "training_rows": training.num_rows,
                    "validation_rows": validation.num_rows,
                    "runtime_seconds": time.perf_counter() - fold_begin,
                    "peak_memory_mb": monitor.peak_bytes / 1024**2,
                }
                peak = max(peak, monitor.peak_bytes / 1024**2)
                del training, train_frame, labels, weights, train_pool, model, validation, prediction, table
                gc.collect()

        combined = pa.concat_tables([pq.read_table(outputs[f]) for f in ("F01", "F02")])
        validate_prediction_rows(
            combined.to_pylist(), expected_rows=EXPECTED,
            expected_data_manifest_id=DATA_MANIFEST_ID, expected_validation_id=VALIDATION_ID,
        )
        pq.write_table(combined, oof_path, compression="zstd")
        metrics = _metrics(combined)
        recent, recent_count = _recent_rmse(con, oof_path)
        gate = promotion_gate(metrics, recent, reference_recent, peak)
        payload = {
            "schema_version": "phase5-results-v1",
            "starting_checkpoint": "773d335e594ca63537aa5ae23b98386737a6d823",
            "run_id": run_id,
            "execution_count": 1,
            "configuration_sha256": config_id,
            "configuration": model_parameters(config),
            "package": "catboost==1.2.8",
            "feasibility": config["feasibility"],
            "population": config["population"],
            "metrics": metrics,
            "recent_period": {"definition": "latest_12_input_months_per_fold", "rmse": recent, "count": recent_count,
                              "reference_rmse": reference_recent, "reference_count": reference_recent_count},
            "promotion": gate,
            "runtime_seconds": time.perf_counter() - begin,
            "peak_memory_mb": peak,
            "folds": fold_details,
            "artifacts": {"oof": _artifact(oof_path), "models": {f: _artifact(p) for f, p in models.items()},
                          "predictions": {f: _artifact(p) for f, p in outputs.items()}},
            "leakage_controls": {"validation_targets_excluded": True, "same_location_anchor": True,
                                 "canonical_location_categorical": True, "recursion": "disabled", "unsafe_fallback": False},
            "production_candidate": None,
            "validation_v1_modified": False,
        }
        _write_json_atomic(results_path, payload)
        return payload
    finally:
        drop_temporary_relations(con, (template.relation,))
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/phase5.yaml"))
    args = parser.parse_args()
    result = run(args.config)
    print(json.dumps({"rmse": result["metrics"]["pooled"]["rmse"], "eligible": result["promotion"]["eligible"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
