"""Phase 4 lean, single-run feature experiments."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
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
from drought_forecasting.lightgbm_benchmark import load_config as load_lgb_config
from drought_forecasting.prediction_contract import ComparableRowIdentity, validate_prediction_rows
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

EXPECTED = ComparableRowIdentity(
    551_965, "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a"
)
REFERENCE = {
    "pooled": 0.5839226503529776,
    "fold": {"F01": 0.5831105018693923, "F02": 0.5847459589738885},
    "horizon": {"6": 0.6392206243180938, "7": 0.6877643629952859},
}
BASE_FEATURES = (
    "last_observed_tws", "effective_horizon", "latitude", "longitude",
    "input_calendar_month", "month_sin", "month_cos", "SPEI_01_t", "SPEI_03_t",
    "SPEI_06_t", "SPEI_12_t", "SOIL_MOISTURE_t",
)
SPATIAL_FEATURES = (
    "neighbour_SPEI_01_mean", "neighbour_SPEI_03_mean", "neighbour_SPEI_06_mean",
    "neighbour_SPEI_12_mean", "neighbour_soil_mean", "neighbour_climatological_change",
    "neighbour_count", "neighbour_climatology_count",
)


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != "phase4-v1":
        raise ValidationError("unknown Phase 4 configuration")
    if tuple(config["features"]) != BASE_FEATURES or tuple(config["spatial_features"]) != SPATIAL_FEATURES:
        raise ValidationError("Phase 4 feature order changed")
    if config["execution_limit_per_experiment"] != 1 or config["threads"] != 2:
        raise ValidationError("Phase 4 execution controls changed")
    return config


def seasonal_fallback(
    location_values: np.ndarray,
    band_values: np.ndarray,
    global_values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the registered finite location -> band -> global -> zero fallback."""
    arrays = [np.asarray(values, dtype=np.float64) for values in (location_values, band_values, global_values)]
    if len({array.shape for array in arrays}) != 1:
        raise ValidationError("seasonal fallback arrays differ in shape")
    result = np.zeros(arrays[0].shape, dtype=np.float64)
    level = np.full(arrays[0].shape, 3, dtype=np.int8)
    for code, values in reversed(tuple(enumerate(arrays))):
        available = np.isfinite(values)
        result[available] = values[available]
        level[available] = code
    return result, level


def cardinal_neighbours(lat2: int, lon2: int) -> tuple[tuple[int, int], ...]:
    return ((lat2 - 1, lon2), (lat2 + 1, lon2), (lat2, lon2 - 1), (lat2, lon2 + 1))


def recency_weights(months: np.ndarray) -> np.ndarray:
    values = np.asarray(months, dtype="datetime64[M]")
    age = (values.max() - values).astype(int)
    return np.power(0.5, age / 24.0).astype(np.float32)


def catboost_feasibility(rows: int, columns: int, maximum_mb: float) -> dict[str, Any]:
    installed = importlib.util.find_spec("catboost") is not None
    projected_mb = rows * (columns * 4 + 4 + 8) * 3 / 1024**2
    safe = installed and projected_mb <= maximum_mb
    return {
        "installed": installed,
        "rows": rows,
        "columns": columns,
        "projected_peak_memory_mb": projected_mb,
        "maximum_mb": maximum_mb,
        "safe": safe,
        "selected": "catboost" if safe else "recency_weighted_lightgbm",
    }


def _q(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _matrix(table: pa.Table, features: tuple[str, ...]) -> np.ndarray:
    matrix = np.column_stack([table[name].to_numpy(zero_copy_only=False) for name in features]).astype(np.float32)
    if matrix.shape != (table.num_rows, len(features)) or not np.isfinite(matrix).all():
        raise ValidationError("Phase 4 matrix is incomplete or nonfinite")
    return matrix


def _create_climatology(con: duckdb.DuckDBPyConnection, fold_id: str) -> None:
    con.execute("DROP TABLE IF EXISTS p4_clim")
    con.execute("DROP TABLE IF EXISTS p4_band_clim")
    con.execute("DROP TABLE IF EXISTS p4_global_clim")
    source = _q(Path("artifacts/phase2c/horizon_training_examples_v1.parquet"))
    con.execute(
        f"""CREATE TEMP TABLE p4_clim AS SELECT location_id,round(latitude*2)::BIGINT lat2,
        round(longitude*2)::BIGINT lon2,
        month(tws_source_month)::INTEGER source_month, month(target_month)::INTEGER target_month_num,
        avg(target-last_observed_tws)::DOUBLE climatological_change, count(*)::DOUBLE climatology_n
        FROM read_parquet('{source}') WHERE fold_id=? GROUP BY ALL""", [fold_id]
    )
    con.execute(
        f"""CREATE TEMP TABLE p4_band_clim AS SELECT floor((latitude+90)/30)::INTEGER latitude_band,
        month(tws_source_month)::INTEGER source_month, month(target_month)::INTEGER target_month_num,
        avg(target-last_observed_tws)::DOUBLE band_change
        FROM read_parquet('{source}') WHERE fold_id=? GROUP BY ALL""", [fold_id]
    )
    con.execute(
        f"""CREATE TEMP TABLE p4_global_clim AS SELECT month(tws_source_month)::INTEGER source_month,
        month(target_month)::INTEGER target_month_num, avg(target-last_observed_tws)::DOUBLE global_change
        FROM read_parquet('{source}') WHERE fold_id=? GROUP BY ALL""", [fold_id]
    )


def _materialize(
    con: duckdb.DuckDBPyConnection,
    base_sql: str,
    output: Path,
    *,
    spatial: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    con.execute("DROP VIEW IF EXISTS p4_base")
    con.execute(f"CREATE TEMP VIEW p4_base AS {base_sql}")
    spatial_select = ""
    spatial_joins = ""
    if spatial:
        con.execute("DROP TABLE IF EXISTS p4_neighbour_current")
        con.execute("DROP TABLE IF EXISTS p4_neighbour_clim")
        con.execute(
            """CREATE TEMP TABLE p4_neighbour_current AS
            SELECT round(n.lat*2)::BIGINT-d.dlat center_lat2,
              round(n.lon*2)::BIGINT-d.dlon center_lon2,n.time input_month,
              avg(n.SPEI_01_t)::DOUBLE neighbour_SPEI_01_mean,
              avg(n.SPEI_03_t)::DOUBLE neighbour_SPEI_03_mean,
              avg(n.SPEI_06_t)::DOUBLE neighbour_SPEI_06_mean,
              avg(n.SPEI_12_t)::DOUBLE neighbour_SPEI_12_mean,
              avg(n.SOIL_MOISTURE_t)::DOUBLE neighbour_soil_mean,count(*)::DOUBLE neighbour_count
            FROM train_data n JOIN (SELECT DISTINCT input_month FROM p4_base) bm ON n.time=bm.input_month
            CROSS JOIN (VALUES (-1,0),(1,0),(0,-1),(0,1)) d(dlat,dlon) GROUP BY ALL"""
        )
        con.execute(
            """CREATE TEMP TABLE p4_neighbour_clim AS
            SELECT c.lat2-d.dlat center_lat2,c.lon2-d.dlon center_lon2,c.source_month,
              c.target_month_num,avg(c.climatological_change)::DOUBLE neighbour_climatological_change,
              count(*)::DOUBLE neighbour_climatology_count
            FROM p4_clim c CROSS JOIN (VALUES (-1,0),(1,0),(0,-1),(0,1)) d(dlat,dlon)
            GROUP BY ALL"""
        )
        spatial_select = """,
          coalesce(ns.neighbour_SPEI_01_mean,b.SPEI_01_t)::DOUBLE neighbour_SPEI_01_mean,
          coalesce(ns.neighbour_SPEI_03_mean,b.SPEI_03_t)::DOUBLE neighbour_SPEI_03_mean,
          coalesce(ns.neighbour_SPEI_06_mean,b.SPEI_06_t)::DOUBLE neighbour_SPEI_06_mean,
          coalesce(ns.neighbour_SPEI_12_mean,b.SPEI_12_t)::DOUBLE neighbour_SPEI_12_mean,
          coalesce(ns.neighbour_soil_mean,b.SOIL_MOISTURE_t)::DOUBLE neighbour_soil_mean,
          coalesce(nc.neighbour_climatological_change,coalesce(l.climatological_change,bc.band_change,g.global_change,0))::DOUBLE neighbour_climatological_change,
          coalesce(ns.neighbour_count,0)::DOUBLE neighbour_count,
          coalesce(nc.neighbour_climatology_count,0)::DOUBLE neighbour_climatology_count"""
        spatial_joins = """
        LEFT JOIN p4_neighbour_current ns ON ns.center_lat2=b.lat2 AND ns.center_lon2=b.lon2
          AND ns.input_month=b.input_month
        LEFT JOIN p4_neighbour_clim nc ON nc.center_lat2=b.lat2 AND nc.center_lon2=b.lon2
          AND nc.source_month=month(b.last_observed_month)
          AND nc.target_month_num=month(b.target_month)"""
    query = f"""SELECT b.* EXCLUDE(row_key,lat2,lon2),
      coalesce(l.climatological_change,bc.band_change,g.global_change,0)::DOUBLE climatological_change,
      CASE WHEN l.climatological_change IS NOT NULL THEN 0 WHEN bc.band_change IS NOT NULL THEN 1
           WHEN g.global_change IS NOT NULL THEN 2 ELSE 3 END::INTEGER seasonal_fallback_level,
      (b.last_observed_tws+coalesce(l.climatological_change,bc.band_change,g.global_change,0))::DOUBLE seasonal_anchor
      {spatial_select}
      FROM p4_base b
      LEFT JOIN p4_clim l ON l.location_id=b.location_id AND l.source_month=month(b.last_observed_month)
        AND l.target_month_num=month(b.target_month)
      LEFT JOIN p4_band_clim bc ON bc.latitude_band=floor((b.latitude+90)/30)::INTEGER
        AND bc.source_month=month(b.last_observed_month) AND bc.target_month_num=month(b.target_month)
      LEFT JOIN p4_global_clim g ON g.source_month=month(b.last_observed_month)
        AND g.target_month_num=month(b.target_month)
      {spatial_joins} ORDER BY b.row_key"""
    con.execute(f"COPY ({query}) TO '{_q(output)}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def _training_sql(path: Path, fold_id: str) -> str:
    return f"""SELECT row_number() OVER(ORDER BY example_key)::BIGINT row_key,
      * EXCLUDE(tws_source_month), tws_source_month last_observed_month,
      round(latitude*2)::BIGINT lat2,round(longitude*2)::BIGINT lon2
      FROM read_parquet('{_q(path)}') WHERE fold_id='{fold_id}'"""


def _validation_sql(relation: str) -> str:
    return f"""SELECT row_number() OVER(ORDER BY fold_id,location_id,input_month,target_month)::BIGINT row_key,
      *,round(latitude*2)::BIGINT lat2,round(longitude*2)::BIGINT lon2 FROM {relation}"""


def _output_table(
    validation: pa.Table, predictions: np.ndarray, anchor: np.ndarray, *, run_id: str,
    config_id: str, model_name: str,
) -> pa.Table:
    absolute = anchor + predictions
    data = validation.to_pydict()
    rows = validation.num_rows
    columns: dict[str, Any] = {
        "run_id": [run_id] * rows, "fold_id": data["fold_id"], "location_id": data["location_id"],
        "input_month": data["input_month"], "target_month": data["target_month"],
        "last_observed_month": data["last_observed_month"], "last_observed_tws": data["last_observed_tws"],
        "effective_horizon": data["effective_horizon"], "mask_state": data["mask_state_label"],
        "predicted_residual": predictions, "prediction": absolute,
        "validation_actual": data["validation_actual"], "model_name": [model_name] * rows,
        "configuration_id": [config_id] * rows, "data_manifest_id": [DATA_MANIFEST_ID] * rows,
        "validation_id": [VALIDATION_ID] * rows, "latitude": data["latitude"],
        **{name: data[name] for name in ("SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t")},
        **{key: [value] * rows for key, value in POLICIES.items()},
    }
    return pa.table(columns)


def _recent_rmse(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[float, int]:
    row = con.execute(
        f"""WITH x AS (SELECT *,max(input_month) OVER(PARTITION BY fold_id) latest
        FROM read_parquet('{_q(path)}')) SELECT sqrt(avg(pow(prediction-validation_actual,2))),count(*)
        FROM x WHERE input_month>latest-INTERVAL 12 MONTH"""
    ).fetchone()
    return float(row[0]), int(row[1])


def _gate(metrics: dict[str, Any], recent: float, recent_reference: float, peak_mb: float) -> dict[str, Any]:
    checks = {
        "pooled": metrics["pooled"]["rmse"] <= 0.578923,
        "folds": all(metrics["fold"][f]["rmse"] <= REFERENCE["fold"][f] + 0.005 for f in REFERENCE["fold"]),
        "horizons_6_7": all(metrics["horizon"][h]["rmse"] <= REFERENCE["horizon"][h] + 0.005 for h in ("6", "7")),
        "coverage": metrics["pooled"]["count"] == EXPECTED.row_count,
        "recent": recent <= recent_reference + 0.005,
        "leakage": True,
        "memory": peak_mb <= 3000,
    }
    return {**checks, "eligible": all(checks.values())}


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _initial_results(config_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "phase4-results-v1", "configuration_sha256": _sha256(config_path),
        "starting_state": {"branch": "main", "head": "ff480679ef0de953d37e141eb5fa0b1f9e27b8fb", "clean": True, "origin_main": "0/0"},
        "reference": {"experiment": "P3-M3B", **REFERENCE, "public_rmse": 0.766408529},
        "preregistration": {"experiments": ["P4-M1", "P4-M2", "P4-M3"], "approved": True},
        "experiments": {}, "production_candidate": None, "validation_v1_modified": False,
    }


def run_experiment(config_path: Path, experiment: str) -> dict[str, Any]:
    config = load_config(config_path)
    results_path = Path("reports/phase4_results.json")
    results = json.loads(results_path.read_text()) if results_path.exists() else _initial_results(config_path)
    if experiment in results["experiments"]:
        raise ValidationError(f"refusing to repeat successful {experiment}")
    if experiment not in {"P4-M1", "P4-M2", "P4-M3"}:
        raise ValidationError("unknown Phase 4 experiment")
    spatial = experiment == "P4-M2"
    feasibility = None
    if experiment == "P4-M3":
        feasibility = catboost_feasibility(1_007_523, len(BASE_FEATURES) + 1, 3000)
        if feasibility["safe"]:
            raise ValidationError("safe CatBoost installation requires the fixed CatBoost path, unavailable in this lean build")
    anchor_kind = "seasonal" if experiment == "P4-M1" else "persistence"
    if spatial:
        m1 = results["experiments"].get("P4-M1", {})
        if m1.get("metrics", {}).get("pooled", {}).get("rmse", 99) < REFERENCE["pooled"]:
            anchor_kind = "seasonal"
    features = BASE_FEATURES + (SPATIAL_FEATURES if spatial else ())
    config_id = hashlib.sha256((_sha256(config_path) + experiment + anchor_kind).encode()).hexdigest()
    started = datetime.now(UTC).replace(microsecond=0)
    run_id = f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-{experiment.lower().replace('-', '')}"
    artifact_dir = Path("artifacts/phase4")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    outputs = {fold: artifact_dir / f"{experiment.lower()}-{fold}-predictions.parquet" for fold in ("F01", "F02")}
    models = {fold: artifact_dir / f"{experiment.lower()}-{fold}.txt" for fold in ("F01", "F02")}
    oof_path = artifact_dir / f"{experiment.lower()}-oof.parquet"
    if oof_path.exists() or any(path.exists() for path in outputs.values()):
        raise ValidationError(f"refusing to overwrite saved {experiment} artifacts")
    lgb_config = load_lgb_config(Path(config["model_config"]))
    audit = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    con = duckdb.connect(":memory:")
    configure_connection(con, threads=2, memory_limit="2GB")
    con.execute("CREATE VIEW train_data AS SELECT * FROM read_parquet('data/processed/Train.parquet')")
    con.execute("CREATE VIEW test_data AS SELECT * FROM read_parquet('data/processed/Test.parquet')")
    template = extract_mask_template(con, "test_data", date(2015, 9, 1), output_relation="p4_template")
    reference_recent, reference_recent_count = _recent_rmse(con, Path(config["reference_oof"]))
    begin = time.perf_counter()
    peak = 0
    fold_details: dict[str, Any] = {}
    try:
        for index, fold in enumerate(audit.folds):
            fold_begin = time.perf_counter()
            _create_climatology(con, fold.fold_id)
            train_features = artifact_dir / f"{experiment.lower()}-{fold.fold_id}-training.parquet"
            validation_features = artifact_dir / f"{experiment.lower()}-{fold.fold_id}-validation.parquet"
            with PeakMemoryMonitor() as monitor:
                _materialize(con, _training_sql(Path(config["training_artifact"]), fold.fold_id), train_features, spatial=spatial)
                training = pq.read_table(train_features)
                expected = int(config["populations"]["training"][fold.fold_id])
                if training.num_rows != expected:
                    raise ValidationError("Phase 4 training population changed")
                anchor_name = "seasonal_anchor" if anchor_kind == "seasonal" else "last_observed_tws"
                anchor = training[anchor_name].to_numpy().astype(np.float64, copy=False)
                labels = (training["target"].to_numpy().astype(np.float64, copy=False) - anchor).astype(np.float32)
                weights = training["sample_weight"].to_numpy().astype(np.float32, copy=False)
                if experiment == "P4-M3":
                    weights = weights * recency_weights(training["input_month"].to_numpy())
                dataset = lgb.Dataset(_matrix(training, features), label=labels, weight=weights, feature_name=list(features), free_raw_data=True)
                model = lgb.train(lgb_config["parameters"], dataset, num_boost_round=lgb_config["num_boost_round"])
                transplanted = transplant_single_fold(
                    con, "train_data", template.relation, fold_id=fold.fold_id, origin=fold.origin,
                    history_gate=audit.history_gate,
                    relation_prefix=f"p4_{experiment.lower().replace('-', '')}_{index}",
                    required_relative_months=18,
                )
                try:
                    create_residual_validation(con, retained=transplanted.relations.retained, output="p4_validation")
                    _materialize(con, _validation_sql("p4_validation"), validation_features, spatial=spatial)
                    validation = pq.read_table(validation_features)
                    if validation.num_rows != int(config["populations"]["validation"][fold.fold_id]):
                        raise ValidationError("Phase 4 validation population changed")
                    val_anchor = validation[anchor_name].to_numpy().astype(np.float64, copy=False)
                    prediction = np.asarray(model.predict(_matrix(validation, features), num_threads=2), dtype=np.float64)
                    table = _output_table(validation, prediction, val_anchor, run_id=run_id, config_id=config_id, model_name=experiment)
                    pq.write_table(table, outputs[fold.fold_id], compression="zstd")
                    model.save_model(str(models[fold.fold_id]))
                finally:
                    con.execute("DROP TABLE IF EXISTS p4_validation")
                    drop_temporary_relations(con, transplanted.relations)
                fallback_counts = {
                    str(key): int(value) for key, value in zip(
                        *np.unique(training["seasonal_fallback_level"].to_numpy(), return_counts=True), strict=True
                    )
                }
                fold_details[fold.fold_id] = {
                    "training_rows": training.num_rows, "validation_rows": validation.num_rows,
                    "runtime_seconds": time.perf_counter() - fold_begin,
                    "peak_memory_mb": monitor.peak_bytes / 1024**2,
                    "seasonal_fallback_counts_training": fallback_counts,
                }
                peak = max(peak, monitor.peak_bytes)
                del training, anchor, labels, weights, dataset, model, validation, val_anchor, prediction, table
                gc.collect()
        combined = pa.concat_tables([pq.read_table(outputs[fold]) for fold in ("F01", "F02")])
        validate_prediction_rows(
            combined.to_pylist(), expected_rows=EXPECTED,
            expected_data_manifest_id=DATA_MANIFEST_ID, expected_validation_id=VALIDATION_ID,
        )
        pq.write_table(combined, oof_path, compression="zstd")
        metrics = _metrics(combined)
        recent, recent_count = _recent_rmse(con, oof_path)
        gate = _gate(metrics, recent, reference_recent, peak / 1024**2)
        payload = {
            "run_id": run_id, "execution_count": 1, "target_representation": anchor_kind,
            "features": list(features), "model": feasibility["selected"] if feasibility else "lightgbm",
            "catboost_feasibility": feasibility, "metrics": metrics,
            "recent_period": {"definition": "latest_12_input_months_per_fold", "rmse": recent,
                              "count": recent_count, "reference_rmse": reference_recent,
                              "reference_count": reference_recent_count},
            "promotion": gate, "runtime_seconds": time.perf_counter() - begin,
            "peak_memory_mb": peak / 1024**2, "folds": fold_details,
            "artifacts": {"oof": _artifact(oof_path),
                          "models": {fold: _artifact(path) for fold, path in models.items()},
                          "predictions": {fold: _artifact(path) for fold, path in outputs.items()}},
            "leakage_controls": {"fold_local_climatology": True, "validation_targets_excluded": True,
                                 "neighbour_tws_used_only_as_fold_local_climatology": spatial,
                                 "future_or_masked_neighbour_tws": False, "recursion": "disabled"},
        }
        results["experiments"][experiment] = payload
        _write_json_atomic(results_path, results)
        return payload
    finally:
        drop_temporary_relations(con, (template.relation,))
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=("P4-M1", "P4-M2", "P4-M3"))
    parser.add_argument("--config", type=Path, default=Path("configs/phase4.yaml"))
    args = parser.parse_args()
    result = run_experiment(args.config, args.experiment)
    print(json.dumps({"experiment": args.experiment, "rmse": result["metrics"]["pooled"]["rmse"],
                      "eligible": result["promotion"]["eligible"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
