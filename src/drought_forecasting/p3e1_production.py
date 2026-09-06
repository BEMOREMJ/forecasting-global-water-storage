"""Owner-authorized P3-E1 production diagnostic; no validation optimization."""
from __future__ import annotations

import gc
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from drought_forecasting.deterministic_baselines import (
 PeakMemoryMonitor,
 _sha256,
 _write_json_atomic,
)
from drought_forecasting.enhanced_residual import (
 _matrix,
 create_soil_statistics,
 materialize_features,
)
from drought_forecasting.lightgbm_benchmark import APPROVED_FEATURES
from drought_forecasting.lightgbm_benchmark import load_config as load_model_config
from drought_forecasting.phase3_production import validate, write_candidate
from drought_forecasting.residual_benchmark import (
 _artifact,
 feature_matrix,
 reconstruct,
 residual_target,
)
from drought_forecasting.validation_core import ValidationError

NOYEAR=tuple(x for x in APPROVED_FEATURES if x!="input_year")
def fit(path,features,tr,te,mc):
 with PeakMemoryMonitor() as mon:
  y=residual_target(tr["target"].to_numpy(),tr["last_observed_tws"].to_numpy()).astype("float32");w=tr["sample_weight"].to_numpy().astype("float32");m=lgb.train(mc["parameters"],lgb.Dataset(feature_matrix(tr,tuple(features)),label=y,weight=w,feature_name=list(features)),num_boost_round=200);m.save_model(str(path));p=reconstruct(te["last_observed_tws"].to_numpy(),m.predict(feature_matrix(te,tuple(features)),num_threads=2))
 return p,mon.peak_bytes/1048576
def run(cfgpath=Path("configs/phase3_p3e1_production.yaml")):
 cfg=yaml.safe_load(cfgpath.read_text());root=Path("artifacts/phase3_p3e1");root.mkdir(parents=True,exist_ok=True);manifest=Path("reports/phase3_p3e1_production_manifest.json")
 if manifest.exists():raise ValidationError("refusing repeat construction")
 tr=pq.read_table("artifacts/phase2g/final_fit_examples.parquet");te=pq.read_table("artifacts/phase2g/test_features.parquet");mc=load_model_config(Path("configs/phase2d_lightgbm.yaml"));records={};preds={};start=time.perf_counter()
 # Reused frozen components.
 p2=pq.read_table("artifacts/phase2g/test_predictions.parquet");preds["phase2_raw_lightgbm"]=p2["Target"].to_numpy();preds["persistence"]=te["last_observed_tws"].to_numpy();p3=pq.read_table("artifacts/phase3h/p3m3b-test-predictions.parquet");preds["p3_m3b_no_year_residual"]=p3["prediction"].to_numpy()
 records["phase2_raw_lightgbm"]={"reused":True,"prediction":_artifact(Path("artifacts/phase2g/test_predictions.parquet")),"model":_artifact(Path("artifacts/phase2g/final_lightgbm_model.txt"))};records["persistence"]={"reused":True};records["p3_m3b_no_year_residual"]={"reused":True,"prediction":_artifact(Path("artifacts/phase3h/p3m3b-test-predictions.parquet")),"model":_artifact(Path("artifacts/phase3h/p3m3b-production.txt"))}
 # M1 once.
 mp=root/"p3m1-production.txt";pp=root/"p3m1-test.parquet";t=time.perf_counter();pred,peak=fit(mp,APPROVED_FEATURES,tr,te,mc);pq.write_table(te.select(["ID","effective_horizon","input_month","target_month","tws_source_month","last_observed_tws"]).append_column("prediction",pa.array(pred)),pp,compression="zstd");preds["p3_m1_residual"]=pred;records["p3_m1_residual"]={"reused":False,"runtime_seconds":time.perf_counter()-t,"peak_memory_mb":peak,"model":_artifact(mp),"prediction":_artifact(pp)};gc.collect()
 # M2 production features and fit once, Train-only soil references.
 con=duckdb.connect(":memory:");con.execute("create view train_data as select * from read_parquet('data/processed/Train.parquet')");con.execute("create view base_training as select *,tws_source_month last_observed_month from read_parquet('artifacts/phase2g/final_fit_examples.parquet')");con.execute("create view base_test as select 'PROD' fold_id,'lat2='||lat2::varchar||';lon2='||lon2::varchar location_id,*,tws_source_month last_observed_month from read_parquet('artifacts/phase2g/test_features.parquet')")
 soil=root/"p3m2-soil.parquet";m2tr=root/"p3m2-training-features.parquet";m2te=root/"p3m2-test-features.parquet";create_soil_statistics(con,"base_training",soil);materialize_features(con,"base_training",soil,m2tr);materialize_features(con,"base_test",soil,m2te);con.close();a=yaml.safe_load(Path("configs/phase3m2_enhanced_residual.yaml").read_text());features=[*APPROVED_FEATURES,*[x["name"] for x in a["added_features"]]];et=pq.read_table(m2tr);ev=pq.read_table(m2te);t=time.perf_counter()
 with PeakMemoryMonitor() as mon:
  y=residual_target(et["target"].to_numpy(),et["last_observed_tws"].to_numpy()).astype("float32");w=et["sample_weight"].to_numpy().astype("float32");m=lgb.train(mc["parameters"],lgb.Dataset(_matrix(et,features),label=y,weight=w,feature_name=features),num_boost_round=200);m2model=root/"p3m2-production.txt";m.save_model(str(m2model));pred=reconstruct(ev["last_observed_tws"].to_numpy(),m.predict(_matrix(ev,features),num_threads=2))
 m2pp=root/"p3m2-test.parquet";pq.write_table(ev.append_column("prediction",pa.array(pred)),m2pp,compression="zstd");preds["p3_m2_enhanced_residual"]=pred;records["p3_m2_enhanced_residual"]={"reused":False,"runtime_seconds":time.perf_counter()-t,"peak_memory_mb":mon.peak_bytes/1048576,"model":_artifact(m2model),"prediction":_artifact(m2pp),"soil":_artifact(soil),"feature_state":_artifact(m2te)};del et,ev,m;gc.collect()
 # M4 three specialists once.
 routed=np.empty(te.num_rows);models=[];t=time.perf_counter();peak=0
 for g,hs in cfg["groups"].items():
  tm=np.isin(tr["effective_horizon"].to_numpy(),hs);vm=np.isin(te["effective_horizon"].to_numpy(),hs);gp,gpeak=fit(root/f"p3m4-{g}.txt",NOYEAR,tr.filter(pa.array(tm)),te.filter(pa.array(vm)),mc);routed[vm]=gp;peak=max(peak,gpeak);models.append(_artifact(root/f"p3m4-{g}.txt"))
 m4pp=root/"p3m4-test.parquet";pq.write_table(te.select(["ID","effective_horizon"]).append_column("prediction",pa.array(routed)),m4pp,compression="zstd");preds["p3_m4_horizon_specialists"]=routed;records["p3_m4_horizon_specialists"]={"reused":False,"runtime_seconds":time.perf_counter()-t,"peak_memory_mb":peak,"models":models,"prediction":_artifact(m4pp)}
 # Frozen weighted construction.
 order=cfg["component_order"];X=np.column_stack([preds[x] for x in order]);h=te["effective_horizon"].to_numpy();final=np.empty(te.num_rows);groups={}
 for g,hs in cfg["groups"].items():mask=np.isin(h,hs);weights=np.array(cfg["weights"][g]);final[mask]=X[mask]@weights;groups[g]=int(mask.sum())
 audit=te.select(["ID","input_month","target_month","effective_horizon","last_observed_tws","tws_source_month"]).append_column("final_prediction",pa.array(final));
 for i,n in enumerate(order):audit=audit.append_column(n,pa.array(X[:,i]))
 auditpath=root/"component-audit.parquet";predpath=root/"p3e1-test-predictions.parquet";pq.write_table(audit,auditpath,compression="zstd");pq.write_table(audit.select(["ID","effective_horizon","final_prediction"]),predpath,compression="zstd");csvpath=Path("submissions/phase3_p3e1_guarded_ensemble_diagnostic.csv");write_candidate(csvpath,te["ID"].to_pylist(),final);validation=validate(csvpath,Path("data/raw/SampleSubmission.csv"))
 payload={"status":"generated_diagnostic_owner_requested_not_uploaded","configuration_id":_sha256(cfgpath),"weights":cfg["weights"],"component_order":order,"routing_counts":groups,"supporting_oof_rmse":.5716858841308573,"failed_h6":{"rmse":.655841115446713,"limit":.6483390618674238},"components":records,"artifacts":{"audit":_artifact(auditpath),"predictions":_artifact(predpath),"submission":validation},"runtime_seconds":time.perf_counter()-start,"generated_utc":datetime.now(UTC).isoformat(),"validation_experiment_rerun":False,"optimizer_rerun":False,"h6_repair":False};_write_json_atomic(manifest,payload);return payload
if __name__=="__main__":print(json.dumps(run()["artifacts"]["submission"]))
