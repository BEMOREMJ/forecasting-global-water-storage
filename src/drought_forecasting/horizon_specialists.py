"""P3-M4 fixed horizon-group specialists."""
from __future__ import annotations

import gc
import hashlib
import json
import time
from datetime import date
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from drought_forecasting.deterministic_baselines import (
    DATA_MANIFEST_ID,
    VALIDATION_ID,
    PeakMemoryMonitor,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.lightgbm_benchmark import load_config as load_model_config
from drought_forecasting.lightgbm_benchmark import training_table
from drought_forecasting.prediction_contract import validate_prediction_rows
from drought_forecasting.recent_diagnostic import _metrics
from drought_forecasting.residual_benchmark import (
    EXPECTED,
    _artifact,
    _fold_output,
    create_residual_validation,
    feature_matrix,
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

GROUPS={"G1":(1,),"G23":(2,3),"G47":(4,5,6,7)}
def group_for(h:int)->str:
    if h==1:return "G1"
    if h in (2,3):return "G23"
    if h in (4,5,6,7):return "G47"
    raise ValidationError("horizon outside 1..7")
def subset_id(table:pa.Table)->str:
    h=hashlib.sha256()
    for col in table.column_names:
        h.update(str(table[col].to_pylist()).encode())
    return h.hexdigest()
def run(path=Path("configs/phase3m4_horizon_specialists.yaml")):
    cfg=yaml.safe_load(path.read_text()); features=tuple(cfg["features"]); cid=_sha256(path)
    out=Path("artifacts/phase3m4");out.mkdir(parents=True,exist_ok=True)
    if Path("reports/phase3m4_metrics.json").exists():raise ValidationError("refusing repeat")
    mc=load_model_config(Path(cfg["phase2_model_config"])); audit=load_audit_config(Path("configs/validation_protocol.yaml"),official_audit=True)
    con=duckdb.connect(":memory:");configure_connection(con,threads=2,memory_limit="2GB")
    con.execute("create view train_data as select * from read_parquet('data/processed/Train.parquet')");con.execute("create view test_data as select * from read_parquet('data/processed/Test.parquet')")
    template=extract_mask_template(con,"test_data",date(2015,9,1),output_relation="m4_template"); start=time.perf_counter();peak=0;checks=[];foldouts=[]
    try:
      for fi,spec in enumerate(audit.folds):
        fr=transplant_single_fold(con,"train_data",template.relation,fold_id=spec.fold_id,origin=spec.origin,history_gate=audit.history_gate,relation_prefix=f"m4_{fi}",required_relative_months=18)
        create_residual_validation(con,retained=fr.relations.retained,output="m4val"); val=con.execute("select * from m4val order by fold_id,location_id,input_month,target_month").to_arrow_table()
        routed=[]
        for group,hs in GROUPS.items():
          mp=out/f"p3m4-{spec.fold_id}-{group}.txt";pp=out/f"p3m4-{spec.fold_id}-{group}-predictions.parquet";cp=Path(f"reports/phase3m4_{spec.fold_id}_{group}_checkpoint.json")
          if mp.exists() and pp.exists() and not cp.exists():
            saved=pq.read_table(pp)
            if saved.num_rows!=cfg["populations"]["validation"][spec.fold_id][group]:raise ValidationError("invalid recoverable prediction")
            tr=training_table(Path(cfg["training_artifact"]),spec.fold_id,features);tr=tr.filter(pa.array(np.isin(tr["effective_horizon"].to_numpy(),hs)))
            rec={"fold":spec.fold_id,"group":group,"rows":saved.num_rows,"training_rows":tr.num_rows,"training_subset_id":subset_id(tr),"model":_artifact(mp),"predictions":_artifact(pp),"recovered_after_checkpoint_report_failure":True};_write_json_atomic(cp,rec);rec["checkpoint"]=_artifact(cp);checks.append(rec);routed.append(saved);del tr,saved;gc.collect();continue
          if mp.exists() and pp.exists() and cp.exists():
            rec=json.loads(cp.read_text());
            if rec["model"]["sha256"]!=_sha256(mp) or rec["predictions"]["sha256"]!=_sha256(pp):raise ValidationError("checkpoint hash mismatch")
            saved=pq.read_table(pp);n=saved.num_rows
            saved=saved.set_column(saved.schema.get_field_index("run_id"),"run_id",pa.array(["run-20260906T130000Z-p3m4-specialists"]*n));saved=saved.set_column(saved.schema.get_field_index("model_name"),"model_name",pa.array(["p3m4_horizon_specialists"]*n));pq.write_table(saved,pp,compression="zstd")
            rec["predictions"]=_artifact(pp);rec["metadata_repaired_without_reprediction"]=True;_write_json_atomic(cp,rec);rec["checkpoint"]=_artifact(cp);checks.append(rec);routed.append(saved);continue
          if any(x.exists() for x in (mp,pp,cp)):raise ValidationError("incomplete/repeated specialist")
          with PeakMemoryMonitor() as mon:
            tr=training_table(Path(cfg["training_artifact"]),spec.fold_id,features); mask=np.isin(tr["effective_horizon"].to_numpy(),hs);tr=tr.filter(pa.array(mask))
            if tr.num_rows!=cfg["populations"]["training"][spec.fold_id][group]:raise ValidationError("training group count")
            vm=np.isin(val["effective_horizon"].to_numpy(),hs);v=val.filter(pa.array(vm))
            if v.num_rows!=cfg["populations"]["validation"][spec.fold_id][group]:raise ValidationError("validation group count")
            y=residual_target(tr["target"].to_numpy(),tr["last_observed_tws"].to_numpy()).astype("float32");w=tr["sample_weight"].to_numpy().astype("float32")
            ds=lgb.Dataset(feature_matrix(tr,features),label=y,weight=w,feature_name=list(features),free_raw_data=True);model=lgb.train(mc["parameters"],ds,num_boost_round=200)
            pr=np.asarray(model.predict(feature_matrix(v,features),num_threads=2));ab=reconstruct(v["last_observed_tws"].to_numpy(),pr)
            tab=_fold_output(v,pr,ab,run_id="p3m4-once",config_id=cid,model_name=f"p3m4_{group}");model.save_model(str(mp));pq.write_table(tab,pp,compression="zstd")
            rec={"fold":spec.fold_id,"group":group,"rows":tab.num_rows,"training_rows":tr.num_rows,"training_subset_id":subset_id(tr),"model":_artifact(mp),"predictions":_artifact(pp),"peak_memory_mb":mon.peak_bytes/1048576};_write_json_atomic(cp,rec);rec["checkpoint"]=_artifact(cp);checks.append(rec);routed.append(tab);peak=max(peak,mon.peak_bytes)
          del tr,v,ds,model,tab;gc.collect()
        ft=pa.concat_tables(routed);pq.write_table(ft,out/f"p3m4-{spec.fold_id}-predictions.parquet",compression="zstd");foldouts.append(ft);con.execute("drop table m4val");drop_temporary_relations(con,fr.relations)
      oof=pa.concat_tables(foldouts).sort_by([(x,"ascending") for x in ("fold_id","location_id","input_month","target_month")]);validate_prediction_rows(oof.to_pylist(),expected_rows=EXPECTED,expected_data_manifest_id=DATA_MANIFEST_ID,expected_validation_id=VALIDATION_ID);pq.write_table(oof,out/"p3m4-absolute-oof.parquet",compression="zstd")
      res=oof.select(["fold_id","location_id","input_month","target_month","last_observed_month","last_observed_tws","effective_horizon","mask_state","predicted_residual"]);pq.write_table(res,out/"p3m4-residual-oof.parquet",compression="zstd")
      met=_metrics(oof);p2=json.loads(Path("reports/phase2d/run-20260904T064720Z-lightgbm_basic-metrics.json").read_text())["metrics"]
      gates={"pooled":met["pooled"]["rmse"]<=.5879872454156464,"F01":met["fold"]["F01"]["rmse"]<=.5985777539596151,"F02":met["fold"]["F02"]["rmse"]<=.5973871814101902,"coverage":oof.num_rows==551965,"masked_horizons":all(met["horizon"][str(h)]["rmse"]<=p2["horizon"][str(h)]["rmse"]+.005 for h in range(2,8)),"leakage":True}
      payload={"experiment_id":"P3-M4","configuration_id":cid,"execution_count":1,"metrics":met,"group_metrics":{g:_metrics(oof.filter(pa.array([group_for(x.as_py())==g for x in oof["effective_horizon"]]))) ["pooled"] for g in GROUPS},"promotion_gate":{**gates,"eligible":all(gates.values())},"runtime_seconds":time.perf_counter()-start,"peak_memory_mb":peak/1048576,"specialists":checks,"coverage":oof.num_rows,"artifacts":{"absolute_oof":_artifact(out/"p3m4-absolute-oof.parquet"),"residual_oof":_artifact(out/"p3m4-residual-oof.parquet")}}
      _write_json_atomic(Path("reports/phase3m4_metrics.json"),payload);return payload
    finally: drop_temporary_relations(con,(template.relation,));con.close()
if __name__=="__main__":print(json.dumps(run()["metrics"]["pooled"]))
