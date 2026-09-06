"""Fit the frozen P3-M3B production model and write local candidates."""
from __future__ import annotations

import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from drought_forecasting.deterministic_baselines import (
 PeakMemoryMonitor,
 _sha256,
 _write_json_atomic,
)
from drought_forecasting.lightgbm_benchmark import load_config as load_model_config
from drought_forecasting.residual_benchmark import (
 _artifact,
 feature_matrix,
 reconstruct,
 residual_target,
)
from drought_forecasting.validation_core import ValidationError


def write_candidate(path,ids,pred):
 with path.open("w",newline="",encoding="utf-8") as f:
  w=csv.writer(f);w.writerow(["ID","Target"]);w.writerows(zip(ids,pred,strict=True))
def validate(path,sample):
 with sample.open(newline="",encoding="utf-8-sig") as f: expected=[r["ID"] for r in csv.DictReader(f)]
 with path.open(newline="",encoding="utf-8") as f:
  reader=csv.DictReader(f);r=list(reader);fields=reader.fieldnames
 vals=np.array([float(x["Target"]) for x in r]);ids=[x["ID"] for x in r]
 if fields!=["ID","Target"] or len(r)!=280961 or ids!=expected or len(set(ids))!=len(ids) or not np.isfinite(vals).all():raise ValidationError("submission contract")
 return {"rows":len(r),"columns":fields,"unique_ids":len(set(ids)),"finite":True,"official_order":True,"sha256":_sha256(path),"size_bytes":path.stat().st_size,"quantiles":{str(q):float(v) for q,v in zip([0,.01,.05,.5,.95,.99,1],np.quantile(vals,[0,.01,.05,.5,.95,.99,1]),strict=True)},"mean":float(vals.mean()),"std":float(vals.std())}
def run(path=Path("configs/phase3h_production.yaml")):
 cfg=yaml.safe_load(path.read_text());o={k:Path(v) for k,v in cfg["outputs"].items()};
 if all(o[k].exists() for k in ("model","predictions","primary_submission","persistence_submission")) and not o["manifest"].exists():
  primary=validate(o["primary_submission"],Path(cfg["sources"]["sample_submission"]));pers=validate(o["persistence_submission"],Path(cfg["sources"]["sample_submission"]));manifest={"configuration_id":_sha256(path),"fit_count":1,"generated_utc":datetime.now(UTC).isoformat(),"features":cfg["features"],"training_rows":2000000,"test_rows":280961,"training_identity":cfg["sources"]["retained_identity"],"runtime_seconds":None,"peak_memory_mb":None,"execution_discrepancy":"post-fit CSV validator failed; saved model and predictions reused without refit","artifacts":{"model":_artifact(o["model"]),"predictions":_artifact(o["predictions"]),"primary":primary,"persistence_diagnostic":pers},"roles":{"primary":"P3-M3B; OOF 0.583923; not uploaded","persistence":"diagnostic only; OOF 0.673722; not uploaded"},"provenance":{"same_location_observed_anchor":True,"source_lte_input_lt_target":True,"recursion":"disabled","input_year_in_matrix":False}};_write_json_atomic(o["manifest"],manifest);return manifest
 if any(o[k].exists() for k in ("model","predictions","primary_submission","manifest")):raise ValidationError("refusing production refit")
 for p in o.values():p.parent.mkdir(parents=True,exist_ok=True)
 if _sha256(Path(cfg["sources"]["training"]))!=cfg["sources"]["training_sha256"] or _sha256(Path(cfg["sources"]["test_features"]))!=cfg["sources"]["test_features_sha256"]:raise ValidationError("source identity")
 tr=pq.read_table(cfg["sources"]["training"]);te=pq.read_table(cfg["sources"]["test_features"]);features=tuple(cfg["features"])
 if tr.num_rows!=2000000 or te.num_rows!=280961 or "input_year" in features:raise ValidationError("population/schema")
 unsafe=pc.sum(pc.greater(tr["tws_source_month"],tr["input_month"])).as_py()+pc.sum(pc.greater_equal(tr["tws_source_month"],tr["target_month"])).as_py()
 if unsafe:raise ValidationError("unsafe anchor")
 mc=load_model_config(Path(cfg["model"]["config"]));start=time.perf_counter()
 with PeakMemoryMonitor() as mon:
  y=residual_target(tr["target"].to_numpy(),tr["last_observed_tws"].to_numpy()).astype("float32");w=tr["sample_weight"].to_numpy().astype("float32");ds=lgb.Dataset(feature_matrix(tr,features),label=y,weight=w,feature_name=list(features),free_raw_data=True);model=lgb.train(mc["parameters"],ds,num_boost_round=200);model.save_model(str(o["model"]))
  rp=np.asarray(model.predict(feature_matrix(te,features),num_threads=2));pred=reconstruct(te["last_observed_tws"].to_numpy(),rp);ids=te["ID"].to_pylist();pt=te.append_column("predicted_residual",pa.array(rp)).append_column("prediction",pa.array(pred));pq.write_table(pt,o["predictions"],compression="zstd");write_candidate(o["primary_submission"],ids,pred);write_candidate(o["persistence_submission"],ids,te["last_observed_tws"].to_numpy())
 primary=validate(o["primary_submission"],Path(cfg["sources"]["sample_submission"]));pers=validate(o["persistence_submission"],Path(cfg["sources"]["sample_submission"]));manifest={"configuration_id":_sha256(path),"fit_count":1,"generated_utc":datetime.now(UTC).isoformat(),"features":list(features),"training_rows":tr.num_rows,"test_rows":te.num_rows,"training_identity":cfg["sources"]["retained_identity"],"runtime_seconds":time.perf_counter()-start,"peak_memory_mb":mon.peak_bytes/1048576,"artifacts":{"model":_artifact(o["model"]),"predictions":_artifact(o["predictions"]),"primary":primary,"persistence_diagnostic":pers},"roles":{"primary":"P3-M3B; OOF 0.583923; not uploaded","persistence":"diagnostic only; OOF 0.673722; not uploaded"},"provenance":{"same_location_observed_anchor":True,"source_lte_input_lt_target":True,"recursion":"disabled","input_year_in_matrix":False}}
 _write_json_atomic(o["manifest"],manifest);return manifest
if __name__=="__main__":print(json.dumps(run()["artifacts"]["primary"]))
