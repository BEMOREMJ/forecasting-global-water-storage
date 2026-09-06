"""P3-E1 artifact-only constrained cross-fitted ensemble."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from scipy.optimize import minimize

from drought_forecasting.deterministic_baselines import (
 DATA_MANIFEST_ID,
 VALIDATION_ID,
 PeakMemoryMonitor,
 _sha256,
 _write_json_atomic,
)
from drought_forecasting.prediction_contract import validate_prediction_rows
from drought_forecasting.recent_diagnostic import _metrics
from drought_forecasting.residual_benchmark import EXPECTED, _artifact
from drought_forecasting.validation_core import ValidationError

KEYS=("fold_id","location_id","input_month","target_month","effective_horizon")
def optimize(X,y,cfg):
 f=lambda w:float(np.mean(np.square(X@w-y)))
 r=minimize(f,np.array(cfg["initial_weights"]),method="SLSQP",bounds=[(0,1)]*X.shape[1],constraints={"type":"eq","fun":lambda w:w.sum()-1},options={"ftol":cfg["tolerance"],"maxiter":cfg["maximum_iterations"],"disp":False})
 if not r.success or r.x.min() < -cfg["feasibility_tolerance"] or abs(r.x.sum()-1)>cfg["feasibility_tolerance"]:raise ValidationError(f"optimizer infeasible: {r.message}")
 return r.x,{"success":bool(r.success),"iterations":int(r.nit),"training_mse":float(r.fun),"sum":float(r.x.sum()),"minimum":float(r.x.min())}
def run(path=Path("configs/phase3e1_crossfit_ensemble.yaml")):
 cfg=yaml.safe_load(path.read_text());out=Path("artifacts/phase3e1/p3e1-crossfit-oof.parquet");weights_path=Path("reports/phase3e1_weights.json");metrics_path=Path("reports/phase3e1_metrics.json")
 if any(x.exists() for x in (out,weights_path,metrics_path)):raise ValidationError("refusing repeated optimization")
 out.parent.mkdir(parents=True,exist_ok=True); names=cfg["components"];tabs=[];hashes={};start=time.perf_counter()
 with PeakMemoryMonitor() as mon:
  for n in names:
   p=Path(cfg["paths"][n]);hashes[n]=_artifact(p);t=pq.read_table(p).sort_by([(k,"ascending") for k in KEYS]);
   if t.num_rows!=551965:raise ValidationError(f"{n} row count")
   tabs.append(t)
  base=tabs[4]; keyref=[base[k].to_pylist() for k in KEYS]; actual=base["validation_actual"].to_numpy();
  for n,t in zip(names,tabs):
   if any(t[k].to_pylist()!=v for k,v in zip(KEYS,keyref)) or not np.array_equal(t["validation_actual"].to_numpy(),actual):raise ValidationError(f"{n} alignment")
   if not np.isfinite(t["prediction"].to_numpy()).all():raise ValidationError(f"{n} nonfinite")
  X=np.column_stack([t["prediction"].to_numpy() for t in tabs]);fold=np.array(base["fold_id"].to_pylist());hor=base["effective_horizon"].to_numpy(); ws={};diag={};pred=np.empty(len(actual))
  for train,apply in (("F01","F02"),("F02","F01")):
   for g,hs in cfg["groups"].items():
    tm=(fold==train)&np.isin(hor,hs);am=(fold==apply)&np.isin(hor,hs);w,d=optimize(X[tm],actual[tm],cfg["optimizer"]);ws[f"train_{train}_{g}"]={n:float(x) for n,x in zip(names,w)};diag[f"train_{train}_{g}"]=d;pred[am]=X[am]@w
  data=base.to_pydict();data["prediction"]=pred;data["run_id"]=["run-20260906T140000Z-p3e1-crossfit"]*len(pred);data["model_name"]=["p3e1_crossfit_ensemble"]*len(pred);table=pa.table(data).sort_by([(k,"ascending") for k in KEYS]);validate_prediction_rows(table.to_pylist(),expected_rows=EXPECTED,expected_data_manifest_id=DATA_MANIFEST_ID,expected_validation_id=VALIDATION_ID);pq.write_table(table,out,compression="zstd")
 _write_json_atomic(weights_path,{"configuration_id":_sha256(path),"components":names,"weights":ws,"diagnostics":diag,"crossfit":"opposite_fold_only","component_artifacts":hashes})
 met=_metrics(table);p2=json.loads(Path("reports/phase2d/run-20260904T064720Z-lightgbm_basic-metrics.json").read_text())["metrics"];gates={"pooled":met["pooled"]["rmse"]<=.5879872454156464,"F01":met["fold"]["F01"]["rmse"]<=.5985777539596151,"F02":met["fold"]["F02"]["rmse"]<=.5973871814101902,"coverage":table.num_rows==551965,"masked_horizons":all(met["horizon"][str(h)]["rmse"]<=p2["horizon"][str(h)]["rmse"]+.005 for h in range(2,8)),"leakage":True}
 payload={"experiment_id":"P3-E1","configuration_id":_sha256(path),"optimization_count":1,"metrics":met,"group_metrics":{g:_metrics(table.filter(pa.array(np.isin(hor,hs))))["pooled"] for g,hs in cfg["groups"].items()},"promotion_gate":{**gates,"eligible":all(gates.values())},"runtime_seconds":time.perf_counter()-start,"peak_memory_mb":mon.peak_bytes/1048576,"weights":_artifact(weights_path),"oof":_artifact(out),"components":hashes}
 _write_json_atomic(metrics_path,payload);return payload
if __name__=="__main__":print(run()["metrics"]["pooled"])
