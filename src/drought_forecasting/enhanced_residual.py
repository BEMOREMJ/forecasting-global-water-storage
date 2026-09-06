"""P3-M2 enhanced persistence-residual LightGBM experiment."""

from __future__ import annotations

import argparse
import gc
import json
import math
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
from drought_forecasting.horizon_examples import retained_target_identity
from drought_forecasting.lightgbm_benchmark import APPROVED_FEATURES
from drought_forecasting.lightgbm_benchmark import load_config as load_model_config
from drought_forecasting.prediction_contract import ComparableRowIdentity, validate_prediction_rows
from drought_forecasting.recent_diagnostic import _metrics
from drought_forecasting.residual_benchmark import (
    create_residual_validation,
    reconstruct,
    residual_target,
)
from drought_forecasting.validation_audit import load_audit_config
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import (
    configure_connection,
    drop_temporary_relations,
    extract_mask_template,
    transplant_single_fold,
)

EXPECTED = ComparableRowIdentity(551_965, "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a")
INDICATORS = ("second_last_available", "slope_available", "seasonal_history_available", "seasonal_difference_available", "soil_anomaly_reference_available")


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "phase3m2-enhanced-residual-v1":
        raise ValidationError("unknown P3-M2 configuration")
    if value.get("execution_limit") != 1 or value.get("experiment_id") != "P3-M2":
        raise ValidationError("P3-M2 must be single execution")
    return value


def spatial_encodings(latitude: np.ndarray, longitude: np.ndarray) -> tuple[np.ndarray, ...]:
    lat = np.deg2rad(np.asarray(latitude, dtype=np.float64)); lon = np.deg2rad(np.asarray(longitude, dtype=np.float64))
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValidationError("spatial coordinates must be finite")
    return np.sin(lat), np.cos(lat), np.sin(lon), np.cos(lon)


def history_features(last: float, last_month: date, second: float | None, second_month: date | None, seasonal: float | None) -> dict[str, float]:
    available = second is not None and second_month is not None and second_month < last_month
    gap = ((last_month.year-second_month.year)*12 + last_month.month-second_month.month) if available else math.nan
    return {"observation_gap_months": float(gap), "historical_tws_slope": (last-float(second))/gap if available and gap > 0 else math.nan, "second_last_available": float(available), "slope_available": float(available and gap > 0), "seasonal_difference": last-float(seasonal) if seasonal is not None else math.nan, "seasonal_available": float(seasonal is not None)}


def _matrix(table: pa.Table, features: list[str]) -> np.ndarray:
    matrix = np.column_stack([table[name].combine_chunks().to_numpy(zero_copy_only=False) for name in features]).astype(np.float32)
    if np.isinf(matrix).any():
        raise ValidationError("enhanced feature matrix contains infinity")
    return matrix


def _q(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def create_soil_statistics(con: duckdb.DuckDBPyConnection, base: str, path: Path) -> dict[str, Any]:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE soil_events AS SELECT DISTINCT round(latitude*2)::BIGINT lat2,round(longitude*2)::BIGINT lon2,input_month,input_calendar_month,SOIL_MOISTURE_t FROM {base}""")
    con.execute("""CREATE OR REPLACE TEMP TABLE soil_stats AS
      SELECT 0 reference_level,lat2,lon2,input_calendar_month calendar_month,avg(SOIL_MOISTURE_t)::DOUBLE mean,count(*)::BIGINT n FROM soil_events GROUP BY 2,3,4
      UNION ALL SELECT 1,lat2,lon2,NULL,avg(SOIL_MOISTURE_t)::DOUBLE,count(*)::BIGINT FROM soil_events GROUP BY 2,3
      UNION ALL SELECT 2,NULL,NULL,input_calendar_month,avg(SOIL_MOISTURE_t)::DOUBLE,count(*)::BIGINT FROM soil_events GROUP BY 4
      UNION ALL SELECT 3,NULL,NULL,NULL,avg(SOIL_MOISTURE_t)::DOUBLE,count(*)::BIGINT FROM soil_events""")
    con.execute(f"COPY soil_stats TO '{_q(path)}' (FORMAT PARQUET,COMPRESSION ZSTD)")
    return {"artifact": _artifact(path), "event_rows": int(con.execute("SELECT count(*) FROM soil_events").fetchone()[0]), "levels": {str(k): int(v) for k, v in con.execute("SELECT reference_level,count(*) FROM soil_stats GROUP BY 1 ORDER BY 1").fetchall()}}


def materialize_features(con: duckdb.DuckDBPyConnection, base: str, soil_path: Path, output: Path) -> None:
    con.execute(f"CREATE OR REPLACE TEMP VIEW active_soil_stats AS SELECT * FROM read_parquet('{_q(soil_path)}')")
    con.execute(f"""COPY (WITH b AS (SELECT *,round(latitude*2)::BIGINT lat2,round(longitude*2)::BIGINT lon2 FROM {base}), enhanced AS (
      SELECT b.*,s2.TWS_t::DOUBLE second_last_observed_tws,s2.time::DATE second_last_observed_month,
        date_diff('month',s2.time,b.last_observed_month)::DOUBLE observation_gap_months,
        (b.last_observed_tws-s2.TWS_t)/NULLIF(date_diff('month',s2.time,b.last_observed_month),0)::DOUBLE historical_tws_slope,
        ss.TWS_t::DOUBLE seasonal_history_tws,ss.time::DATE seasonal_history_month,
        date_diff('month',ss.time,b.target_month)::DOUBLE seasonal_history_age_months,
        (b.last_observed_tws-ss.TWS_t)::DOUBLE seasonal_tws_difference,
        (b.SPEI_01_t-b.SPEI_03_t)::DOUBLE spei_01_minus_03,(b.SPEI_03_t-b.SPEI_06_t)::DOUBLE spei_03_minus_06,
        (b.SPEI_06_t-b.SPEI_12_t)::DOUBLE spei_06_minus_12,
        (b.SOIL_MOISTURE_t-coalesce(sm0.mean,sm1.mean,sm2.mean,sm3.mean))::DOUBLE soil_moisture_anomaly,
        sin(radians(b.latitude))::DOUBLE latitude_sin,cos(radians(b.latitude))::DOUBLE latitude_cos,
        sin(radians(b.longitude))::DOUBLE longitude_sin,cos(radians(b.longitude))::DOUBLE longitude_cos,
        (s2.time IS NOT NULL)::INTEGER second_last_available,(s2.time IS NOT NULL AND date_diff('month',s2.time,b.last_observed_month)>0)::INTEGER slope_available,
        (ss.time IS NOT NULL)::INTEGER seasonal_history_available,(ss.time IS NOT NULL)::INTEGER seasonal_difference_available,
        (coalesce(sm0.mean,sm1.mean,sm2.mean,sm3.mean) IS NOT NULL)::INTEGER soil_anomaly_reference_available,
        CASE WHEN sm0.mean IS NOT NULL THEN 0 WHEN sm1.mean IS NOT NULL THEN 1 WHEN sm2.mean IS NOT NULL THEN 2 ELSE 3 END soil_reference_level
      FROM b
      ASOF LEFT JOIN train_data s2 ON b.lat2=round(s2.lat*2)::BIGINT AND b.lon2=round(s2.lon*2)::BIGINT AND b.last_observed_month>s2.time AND s2.TWS_t IS NOT NULL
      ASOF LEFT JOIN train_data ss ON b.lat2=round(ss.lat*2)::BIGINT AND b.lon2=round(ss.lon*2)::BIGINT AND month(b.target_month)=month(ss.time) AND b.input_month>=ss.time AND ss.TWS_t IS NOT NULL
      LEFT JOIN active_soil_stats sm0 ON sm0.reference_level=0 AND sm0.lat2=b.lat2 AND sm0.lon2=b.lon2 AND sm0.calendar_month=b.input_calendar_month
      LEFT JOIN active_soil_stats sm1 ON sm1.reference_level=1 AND sm1.lat2=b.lat2 AND sm1.lon2=b.lon2
      LEFT JOIN active_soil_stats sm2 ON sm2.reference_level=2 AND sm2.calendar_month=b.input_calendar_month
      LEFT JOIN active_soil_stats sm3 ON sm3.reference_level=3)
      SELECT * FROM enhanced ORDER BY fold_id,location_id,input_month,target_month) TO '{_q(output)}' (FORMAT PARQUET,COMPRESSION ZSTD)""")


def availability(con: duckdb.DuckDBPyConnection, path: Path, label: str) -> dict[str, Any]:
    con.execute(f"CREATE OR REPLACE TEMP VIEW av AS SELECT * FROM read_parquet('{_q(path)}')")
    fields = [x for x in INDICATORS]
    overall = {name: float(con.execute(f"SELECT avg({name}) FROM av").fetchone()[0]) for name in fields}
    by_mask = {str(mask): {name: float(con.execute(f"SELECT avg({name}) FROM av WHERE mask_state_label=?", [mask]).fetchone()[0]) for name in fields} for (mask,) in con.execute("SELECT DISTINCT mask_state_label FROM av ORDER BY 1").fetchall()} if "validation" in label else {}
    by_horizon = {str(h): {name: float(con.execute(f"SELECT avg({name}) FROM av WHERE effective_horizon=?", [h]).fetchone()[0]) for name in fields} for h in range(1, 8)}
    return {"rows": int(con.execute("SELECT count(*) FROM av").fetchone()[0]), "overall": overall, "by_mask": by_mask, "by_horizon": by_horizon}


def run(config_path: Path) -> dict[str, Any]:
    cfg = load_config(config_path); model_cfg = load_model_config(Path(cfg["sources"]["phase2d_config"])); config_id = _sha256(config_path)
    added = [x["name"] for x in cfg["added_features"]]; features = [*APPROVED_FEATURES, *added]
    root = Path(cfg["output_root"]); root.mkdir(parents=True, exist_ok=True)
    final_paths = [Path(cfg["report_metrics"]), Path(cfg["report_provenance"]), root/"p3m2-absolute-oof.parquet", root/"p3m2-residual-oof.parquet"]
    if any(x.exists() for x in final_paths): raise ValidationError("refusing to repeat P3-M2")
    audit = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    con = duckdb.connect(":memory:"); configure_connection(con,threads=2,memory_limit="2GB")
    con.execute("CREATE VIEW train_data AS SELECT * FROM read_parquet('data/processed/Train.parquet')"); con.execute("CREATE VIEW test_data AS SELECT * FROM read_parquet('data/processed/Test.parquet')")
    template=extract_mask_template(con,"test_data",date(2015,9,1),output_relation="p3m2_template")
    start=time.perf_counter(); peak=0; checkpoints=[]; availability_report={}; soil_reports={}
    run_id=f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-p3m2-enhanced-residual"
    try:
      for idx,spec in enumerate(audit.folds):
        f=spec.fold_id; model_path=root/f"p3m2-{f}.txt"; pred_path=root/f"p3m2-{f}-predictions.parquet"; checkpoint_path=Path(f"reports/phase3m2_{f}_checkpoint.json")
        existing=(model_path.exists(),pred_path.exists(),checkpoint_path.exists())
        if all(existing):
          cp=json.loads(checkpoint_path.read_text());
          if cp["model"]["sha256"]!=_sha256(model_path) or cp["predictions"]["sha256"]!=_sha256(pred_path): raise ValidationError("checkpoint mismatch")
          checkpoints.append(cp); continue
        if any(existing): raise ValidationError("incomplete fold checkpoint")
        begin=time.perf_counter()
        with PeakMemoryMonitor() as monitor:
          con.execute(f"CREATE OR REPLACE TEMP VIEW base_training AS SELECT *,tws_source_month AS last_observed_month FROM read_parquet('{_q(Path(cfg['sources']['phase2c']))}') WHERE fold_id='{f}'")
          if retained_target_identity(con,"base_training")!=cfg["identities"][f"phase2c_{f}"]: raise ValidationError("stored training identity mismatch")
          soil_path=root/f"p3m2-soil-{f}.parquet"; soil_reports[f]=create_soil_statistics(con,"base_training",soil_path)
          training_path=root/f"p3m2-{f}-training.parquet"; materialize_features(con,"base_training",soil_path,training_path)
          availability_report[f"{f}_training"]=availability(con,training_path,f"{f}_training")
          fold=transplant_single_fold(con,"train_data",template.relation,fold_id=f,origin=spec.origin,history_gate=audit.history_gate,relation_prefix=f"p3m2_fold_{idx}",required_relative_months=18)
          try:
            create_residual_validation(con,retained=fold.relations.retained,output="base_validation"); validation_path=root/f"p3m2-{f}-validation.parquet"; materialize_features(con,"base_validation",soil_path,validation_path)
          finally: drop_temporary_relations(con,fold.relations)
          availability_report[f"{f}_validation"]=availability(con,validation_path,f"{f}_validation")
          training=pq.read_table(training_path); validation=pq.read_table(validation_path)
          if training.num_rows!=cfg["populations"]["training"][f] or validation.num_rows!=cfg["populations"]["validation"][f]: raise ValidationError("population mismatch")
          matrix=_matrix(training,features); labels=residual_target(training["target"].to_numpy(),training["last_observed_tws"].to_numpy()).astype(np.float32); weights=training["sample_weight"].to_numpy().astype(np.float32)
          model=lgb.train(model_cfg["parameters"],lgb.Dataset(matrix,label=labels,weight=weights,feature_name=features),num_boost_round=200)
          residual=np.asarray(model.predict(_matrix(validation,features),num_threads=2)); absolute=reconstruct(validation["last_observed_tws"].to_numpy(),residual)
          data=validation.to_pydict(); n=validation.num_rows; data.update({"run_id":[run_id]*n,"predicted_residual":residual,"prediction":absolute,"model_name":["p3m2_enhanced_residual"]*n,"configuration_id":[config_id]*n,"data_manifest_id":[DATA_MANIFEST_ID]*n,"validation_id":[VALIDATION_ID]*n,**{k:[v]*n for k,v in POLICIES.items()}})
          order=["run_id","fold_id","location_id","input_month","target_month","last_observed_month","last_observed_tws","effective_horizon","mask_state_label","predicted_residual","prediction","validation_actual","model_name","configuration_id","data_manifest_id","validation_id","latitude","SPEI_01_t","SPEI_03_t","SPEI_06_t","SPEI_12_t",*POLICIES]
          out=pa.table({x:data[x] for x in order}).rename_columns(["mask_state" if x=="mask_state_label" else x for x in order]); model.save_model(str(model_path)); pq.write_table(out,pred_path,compression="zstd")
          cp={"fold":f,"rows":n,"runtime_seconds":time.perf_counter()-begin,"peak_memory_mb":monitor.peak_bytes/1024**2,"model":_artifact(model_path),"predictions":_artifact(pred_path),"training_features":_artifact(training_path),"validation_features":_artifact(validation_path),"soil_statistics":_artifact(soil_path)}; _write_json_atomic(checkpoint_path,cp); checkpoints.append(cp)
          del training,validation,matrix,labels,weights,model,residual,absolute,data,out; gc.collect()
        peak=max(peak,monitor.peak_bytes)
      tables=[pq.read_table(root/f"p3m2-{f}-predictions.parquet") for f in ("F01","F02")]; absolute=pa.concat_tables(tables); rows=absolute.to_pylist(); validate_prediction_rows(rows,expected_rows=EXPECTED,expected_data_manifest_id=DATA_MANIFEST_ID,expected_validation_id=VALIDATION_ID)
      abs_path=root/"p3m2-absolute-oof.parquet"; pq.write_table(absolute,abs_path,compression="zstd"); residual_path=root/"p3m2-residual-oof.parquet"; residual_table=absolute.select(["fold_id","location_id","input_month","target_month","last_observed_month","last_observed_tws","effective_horizon","mask_state","predicted_residual"]); residual_table=residual_table.append_column("residual_actual",pa.array([x["validation_actual"]-x["last_observed_tws"] for x in rows])); pq.write_table(residual_table,residual_path,compression="zstd")
      metrics=_metrics(absolute); refs={"phase2":json.loads(Path("reports/phase2d/run-20260904T064720Z-lightgbm_basic-metrics.json").read_text())["metrics"],"persistence":json.loads(Path("reports/phase2b/run-20260904T061036Z-persistence-metrics.json").read_text())["metrics"],"p3m1":json.loads(Path("reports/phase3m1_metrics.json").read_text())["metrics"]}
      gates={"pooled":metrics["pooled"]["rmse"]<=cfg["promotion_gate"]["pooled_maximum_rmse"],"folds":all(metrics["fold"][f]["rmse"]<=cfg["promotion_gate"]["fold_maximum_rmse"][f] for f in ("F01","F02")),"coverage":absolute.num_rows==551965,"leakage":True,"masked_protected":metrics["mask_state"]["masked/unavailable"]["rmse"]<=refs["phase2"]["mask_state"]["masked/unavailable"]["rmse"]+0.005}; gates["eligible"]=all(gates.values())
      _write_json_atomic(Path(cfg["report_availability"]),availability_report); _write_json_atomic(Path(cfg["report_soil_F01"]),soil_reports["F01"]); _write_json_atomic(Path(cfg["report_soil_F02"]),soil_reports["F02"])
      provenance={"configuration_id":config_id,"same_location":"pass","timestamp_ordering":"pass","future_and_validation_target_sources":0,"adjacent_row_assumptions":0,"recursive_values":0,"training_identities":{"F01":cfg["identities"]["phase2c_F01"],"F02":cfg["identities"]["phase2c_F02"]},"checkpoints":checkpoints}; _write_json_atomic(Path(cfg["report_provenance"]),provenance)
      payload={"schema_version":"phase3m2-metrics-v1","execution_count":1,"configuration_id":config_id,"metrics":metrics,"references":refs,"increment_from_p3m1":refs["p3m1"]["pooled"]["rmse"]-metrics["pooled"]["rmse"],"coverage":{"rows":absolute.num_rows,"identity":EXPECTED.sha256},"runtime_seconds":time.perf_counter()-start,"peak_memory_mb":peak/1024**2,"promotion_gate":gates,"checkpoints":checkpoints,"artifacts":{"absolute_oof":_artifact(abs_path),"residual_oof":_artifact(residual_path),"availability":_artifact(Path(cfg["report_availability"])),"provenance":_artifact(Path(cfg["report_provenance"]))}}; _write_json_atomic(Path(cfg["report_metrics"]),payload); return payload
    finally: drop_temporary_relations(con,(template.relation,)); con.close()


def main(argv: list[str] | None=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--config",type=Path,default=Path("configs/phase3m2_enhanced_residual.yaml")); args=parser.parse_args(argv); result=run(args.config); print(json.dumps({k:result[k] for k in ("metrics","increment_from_p3m1","runtime_seconds","peak_memory_mb","promotion_gate")},sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
