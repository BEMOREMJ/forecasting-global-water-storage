"""Build and independently validate the single frozen Phase 2G submission candidate."""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
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
    PeakMemoryMonitor,
    _sha256,
    _write_json_atomic,
)
from drought_forecasting.horizon_examples import (
    create_fold_candidates,
    create_keyed_train,
    retained_target_identity,
    validate_examples,
)
from drought_forecasting.lightgbm_benchmark import APPROVED_FEATURES, arrow_matrix
from drought_forecasting.lightgbm_benchmark import load_config as load_model_config
from drought_forecasting.validation_audit import canonical_sha256
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import extract_mask_template

SCHEMA_VERSION = "phase2g-submission-v1"
EXPECTED_ROWS = 280_961


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("unknown Phase 2G configuration schema")
    if value.get("horizons") != list(range(1, 8)) or value.get("seed") != 20260904:
        raise ValidationError("Phase 2G horizons or seed differ from the frozen policy")
    quotas = value.get("sampling", {}).get("retained_by_horizon", {})
    if {int(key) for key in quotas} != set(range(1, 8)) or sum(map(int, quotas.values())) != 2_000_000:
        raise ValidationError("Phase 2G horizon quotas must cover 1--7 and sum to 2,000,000")
    model_config = load_model_config(Path(value["sources"]["phase2d_config"]))
    if canonical_sha256(model_config) != value["sources"]["phase2d_configuration_id"]:
        raise ValidationError("Phase 2D configuration identity mismatch")
    return value


def select_final_fit(
    connection: duckdb.DuckDBPyConnection, *, candidates: str, output: str, quotas: Mapping[int, int]
) -> None:
    values = ",".join(f"({int(h)},{int(n)})" for h, n in sorted(quotas.items()))
    connection.execute(
        f"""
        CREATE TEMP TABLE {output} AS
        WITH quotas(effective_horizon,quota) AS (VALUES {values}), ranked AS (
          SELECT c.*,q.quota,row_number() OVER (
            PARTITION BY c.effective_horizon ORDER BY c.selection_hash,c.target_month,c.location_id
          ) selection_rank
          FROM {candidates} c JOIN quotas q USING(effective_horizon)
        ), populations AS (
          SELECT effective_horizon,count(*) population_count FROM {candidates} GROUP BY 1
        )
        SELECT r.* EXCLUDE(quota,selection_rank),p.population_count::BIGINT population_count,
          r.quota::BIGINT retained_count,p.population_count::DOUBLE/r.quota sample_weight,
          r.fold_id || '|' || r.target_month::VARCHAR || '|' || r.location_id
            || '|h=' || r.effective_horizon::VARCHAR example_key
        FROM ranked r JOIN populations p USING(effective_horizon)
        WHERE selection_rank<=quota
        """
    )


def create_test_features(connection: duckdb.DuckDBPyConnection, *, output: str = "test_features") -> int:
    extract_mask_template(connection, "test_data", date(2015, 9, 1), output_relation="phase2g_template")
    connection.execute(
        f"""
        CREATE TEMP TABLE {output} AS
        WITH ordered AS (SELECT row_number() OVER ()::BIGINT row_id,* FROM test_data)
        SELECT o.row_id,CAST(o.ID AS VARCHAR) ID,t.input_month,
          CAST(t.input_month+INTERVAL 1 MONTH AS DATE) target_month,
          t.expected_horizon::INTEGER effective_horizon,s.TWS_t::DOUBLE last_observed_tws,
          o.lat::DOUBLE latitude,o.lon::DOUBLE longitude,year(t.input_month)::INTEGER input_year,
          month(t.input_month)::INTEGER input_calendar_month,o.month_sin::DOUBLE month_sin,
          o.month_cos::DOUBLE month_cos,o.SPEI_01_t::DOUBLE SPEI_01_t,
          o.SPEI_03_t::DOUBLE SPEI_03_t,o.SPEI_06_t::DOUBLE SPEI_06_t,
          o.SPEI_12_t::DOUBLE SPEI_12_t,o.SOIL_MOISTURE_t::DOUBLE SOIL_MOISTURE_t,
          CAST(s.time AS DATE) tws_source_month,t.lat2,t.lon2
        FROM ordered o JOIN phase2g_template t ON CAST(o.ID AS VARCHAR)=t.template_row_id
        JOIN test_data s ON CAST(round(s.lat*2) AS BIGINT)=t.lat2
          AND CAST(round(s.lon*2) AS BIGINT)=t.lon2
          AND s.time=t.input_month+INTERVAL (1-t.expected_horizon) MONTH AND s.TWS_t IS NOT NULL
        ORDER BY o.row_id
        """
    )
    facts = connection.execute(
        f"""SELECT count(*),count(DISTINCT ID),count(*) FILTER(WHERE effective_horizon NOT BETWEEN 1 AND 7
          OR date_diff('month',input_month,target_month)<>1
          OR date_diff('month',tws_source_month,target_month)<>effective_horizon
          OR tws_source_month>input_month) FROM {output}"""
    ).fetchone()
    if tuple(map(int, facts)) != (EXPECTED_ROWS, EXPECTED_ROWS, 0):
        raise ValidationError("Test feature coverage, uniqueness, or temporal provenance failed")
    table = connection.execute(f"SELECT * FROM {output} ORDER BY row_id").to_arrow_table()
    arrow_matrix(table, APPROVED_FEATURES)
    return EXPECTED_ROWS


def write_submission(path: Path, ids: Sequence[str], predictions: Sequence[float]) -> str:
    if len(ids) != EXPECTED_ROWS or len(predictions) != EXPECTED_ROWS:
        raise ValidationError("submission row count is invalid")
    if len(set(ids)) != len(ids) or not np.isfinite(np.asarray(predictions, dtype=float)).all():
        raise ValidationError("submission IDs must be unique and predictions finite")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValidationError("refusing to overwrite submission candidate")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("ID", "Target"))
            writer.writerows((identifier, format(float(prediction), ".17g")) for identifier, prediction in zip(ids, predictions, strict=True))
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return _sha256(path)


def independent_validate_submission(submission: Path, test: Path, sample: Path) -> dict[str, Any]:
    def read(path: Path, expected: list[str]) -> list[list[str]]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream); header = next(reader, None)
            if header != expected:
                raise ValidationError(f"wrong columns in {path}: {header}")
            return list(reader)
    test_rows = read(test, ["ID","time","lat","lon","TWS_t","SPEI_01_t","SPEI_03_t","SPEI_06_t","SPEI_12_t","SOIL_MOISTURE_t","month_sin","month_cos","TWS_t_masked"])
    sample_rows = read(sample, ["ID","Target"])
    submitted = read(submission, ["ID","Target"])
    ids = [row[0] for row in submitted]
    test_ids = [row[0] for row in test_rows]; sample_ids = [row[0] for row in sample_rows]
    if len(submitted) != EXPECTED_ROWS or len(ids) != len(set(ids)):
        raise ValidationError("wrong submission row count or duplicate ID")
    if ids != test_ids or ids != sample_ids:
        raise ValidationError("submission IDs/order differ from official files")
    try:
        targets = np.asarray([float(row[1]) for row in submitted], dtype=np.float64)
    except (ValueError, IndexError) as exc:
        raise ValidationError("missing or invalid submission target") from exc
    if not np.isfinite(targets).all() or any(len(row) != 2 for row in submitted):
        raise ValidationError("submission contains nonfinite targets or extra columns")
    return {"status":"pass","rows":len(ids),"columns":2,"test_id_order":True,"sample_id_order":True,
            "duplicate_ids":0,"missing_targets":0,"nonfinite_targets":0,"index_column":False}


def _artifact(path: Path) -> dict[str, Any]:
    return {"path":path.as_posix(),"sha256":_sha256(path),"size_bytes":path.stat().st_size}


def run(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path); model_config = load_model_config(Path(config["sources"]["phase2d_config"]))
    paths = {key:Path(value) for key,value in config["output"].items()}
    if any(path.exists() for path in paths.values()):
        raise ValidationError("refusing to overwrite a Phase 2G output")
    for key in ("training_artifact","model","test_features","predictions","submission"):
        paths[key].parent.mkdir(parents=True,exist_ok=True)
    Path(config["resources"]["spill_directory"]).mkdir(parents=True,exist_ok=True)
    started=datetime.now(UTC).replace(microsecond=0); run_id=f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-phase2g-lightgbm-basic"
    stage: dict[str, Any]={}; total_start=time.perf_counter(); peak=0
    con=duckdb.connect(":memory:"); con.execute("SET threads=2"); con.execute("SET memory_limit='2GB'")
    con.execute("SET temp_directory=?",[str(Path(config["resources"]["spill_directory"]).resolve())])
    try:
        begin=time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            create_keyed_train(con,Path(config["sources"]["train_cache"]))
            create_fold_candidates(con,fold_id="FINAL",cutoff=date.fromisoformat(str(config["training_cutoff"])),output_relation="final_candidates")
            population={str(h):int(n) for h,n in con.execute("SELECT effective_horizon,count(*) FROM final_candidates GROUP BY 1 ORDER BY 1").fetchall()}
            quotas={int(h):int(n) for h,n in config["sampling"]["retained_by_horizon"].items()}
            select_final_fit(con,candidates="final_candidates",output="final_fit",quotas=quotas)
            validate_examples(con,"final_fit")
            retained_id=retained_target_identity(con,"final_fit")
            con.execute(f"COPY (SELECT * FROM final_fit ORDER BY effective_horizon,selection_hash,target_month,location_id) TO '{str(paths['training_artifact'].resolve()).replace(chr(39),chr(39)*2)}' (FORMAT PARQUET,COMPRESSION ZSTD)")
        peak=max(peak,monitor.peak_bytes); stage["materialization"]={"runtime_seconds":time.perf_counter()-begin,"peak_memory_mb":monitor.peak_bytes/1024**2}

        begin=time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            training=pq.read_table(paths["training_artifact"],columns=[*APPROVED_FEATURES,"target","sample_weight"])
            matrix=arrow_matrix(training,APPROVED_FEATURES); labels=training["target"].to_numpy().astype(np.float32,copy=False); weights=training["sample_weight"].to_numpy().astype(np.float32,copy=False)
            target_range=[float(labels.min()),float(labels.max())]
            dataset=lgb.Dataset(matrix,label=labels,weight=weights,feature_name=list(APPROVED_FEATURES),free_raw_data=True)
            model=lgb.train(model_config["parameters"],dataset,num_boost_round=model_config["num_boost_round"])
            model.save_model(str(paths["model"])); del training,matrix,labels,weights,dataset; gc.collect()
        peak=max(peak,monitor.peak_bytes); stage["fitting"]={"runtime_seconds":time.perf_counter()-begin,"peak_memory_mb":monitor.peak_bytes/1024**2}

        begin=time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            quoted_test = str(Path(config["sources"]["test_cache"]).resolve()).replace("'", "''")
            con.execute(f"CREATE VIEW test_data AS SELECT * FROM read_parquet('{quoted_test}')")
            create_test_features(con)
            con.execute(f"COPY (SELECT * FROM test_features ORDER BY row_id) TO '{str(paths['test_features'].resolve()).replace(chr(39),chr(39)*2)}' (FORMAT PARQUET,COMPRESSION ZSTD)")
            test_table=con.execute("SELECT * FROM test_features ORDER BY row_id").to_arrow_table()
            predictions=np.asarray(model.predict(arrow_matrix(test_table,APPROVED_FEATURES),num_threads=2),dtype=np.float64)
            if len(predictions)!=EXPECTED_ROWS or not np.isfinite(predictions).all(): raise ValidationError("invalid Test predictions")
            prediction_table=pa.table({"ID":test_table["ID"],"Target":pa.array(predictions)})
            pq.write_table(prediction_table,paths["predictions"],compression="zstd")
            write_submission(paths["submission"],test_table["ID"].to_pylist(),predictions)
        peak=max(peak,monitor.peak_bytes); stage["prediction_and_write"]={"runtime_seconds":time.perf_counter()-begin,"peak_memory_mb":monitor.peak_bytes/1024**2}

        begin=time.perf_counter(); validation=independent_validate_submission(paths["submission"],Path(config["sources"]["official_test"]),Path(config["sources"]["official_sample_submission"])); stage["independent_validation"]={"runtime_seconds":time.perf_counter()-begin}
        quantiles=np.quantile(predictions,[0,.01,.05,.25,.5,.75,.95,.99,1])
        manifest={"schema_version":"phase2g-submission-manifest-v1","run_id":run_id,"started_utc":started.isoformat().replace("+00:00","Z"),"starting_git_checkpoint":"b3003209ec29c860498a93bf5163784fe720a64c","configuration_id":canonical_sha256(config),"phase2d_configuration_id":config["sources"]["phase2d_configuration_id"],"official_identities":{k:config["sources"][k] for k in ("train_sha256","test_sha256","sample_submission_sha256")},"validation_identity":config["sources"]["validation_identity"],"comparable_row_identity":config["sources"]["comparable_row_identity"],"phase2e_candidate":{"model":"lightgbm_basic","run_id":"run-20260904T064720Z-lightgbm_basic","decision":"preferred"},"final_fit_policy":{"cutoff":str(config["training_cutoff"]),"eligible_by_horizon":population,"retained_by_horizon":{str(k):v for k,v in quotas.items()},"sampling_seed":config["seed"],"algorithm":config["sampling"]["algorithm"],"weights":config["sampling"]["weights"],"retained_identity":retained_id},"features":list(APPROVED_FEATURES),"lightgbm":{"parameters":model_config["parameters"],"num_boost_round":200},"dependencies":{"lightgbm":lgb.__version__,"numpy":np.__version__,"duckdb":duckdb.__version__,"pyarrow":pa.__version__},"artifacts":{k:_artifact(paths[k]) for k in ("training_artifact","model","test_features","predictions","submission")},"submission":{"filename":paths["submission"].as_posix(),"rows":EXPECTED_ROWS,"columns":["ID","Target"],"upload_status":"not_uploaded"},"independent_validation":validation,"prediction_diagnostics":{"minimum":float(predictions.min()),"maximum":float(predictions.max()),"mean":float(predictions.mean()),"standard_deviation":float(predictions.std()),"quantiles":{str(q):float(v) for q,v in zip((0,.01,.05,.25,.5,.75,.95,.99,1),quantiles,strict=True)},"final_fit_target_range":target_range,"below_target_range":int((predictions<target_range[0]).sum()),"above_target_range":int((predictions>target_range[1]).sum())},"stages":stage,"total_runtime_seconds":time.perf_counter()-total_start,"peak_memory_mb":peak/1024**2,"registry_handling":"unchanged; registry contains validation experiments only","production_step_counts":{"materialization":1,"fitting":1,"prediction":1,"candidate_write":1,"independent_validation":1}}
        _write_json_atomic(paths["manifest"],manifest); return manifest
    finally:
        con.close()


def resume_after_fit(config_path: Path) -> dict[str, Any]:
    """Resume only downstream steps after the documented prepared-view failure."""
    config=load_config(config_path); model_config=load_model_config(Path(config["sources"]["phase2d_config"])); paths={key:Path(value) for key,value in config["output"].items()}
    required=(paths["training_artifact"],paths["model"])
    forbidden=(paths["test_features"],paths["predictions"],paths["submission"],paths["manifest"])
    if not all(path.exists() for path in required) or any(path.exists() for path in forbidden):
        raise ValidationError("resume requires valid upstream artifacts and no downstream outputs")
    started=datetime.now(UTC).replace(microsecond=0); run_id="run-20260904T100126Z-phase2g-lightgbm-basic"
    total_start=time.perf_counter(); peak=0; stage: dict[str,Any]={
        "materialization":{"runtime_seconds":None,"peak_memory_mb":None,"status":"completed_once_before_downstream_failure"},
        "fitting":{"runtime_seconds":None,"peak_memory_mb":None,"status":"completed_once_before_downstream_failure"},
    }
    con=duckdb.connect(":memory:"); con.execute("SET threads=2"); con.execute("SET memory_limit='2GB'")
    quoted_training=str(paths["training_artifact"].resolve()).replace("'","''"); con.execute(f"CREATE VIEW saved_fit AS SELECT * FROM read_parquet('{quoted_training}')")
    count,unique=map(int,con.execute("SELECT count(*),count(DISTINCT example_key) FROM saved_fit").fetchone())
    if (count,unique)!=(2_000_000,2_000_000): raise ValidationError("upstream final-fit artifact is incomplete or duplicated")
    retained_id=retained_target_identity(con,"saved_fit")
    population={str(h):int(n) for h,n in con.execute("SELECT effective_horizon,max(population_count) FROM saved_fit GROUP BY 1 ORDER BY 1").fetchall()}
    target_range=list(map(float,con.execute("SELECT min(target),max(target) FROM saved_fit").fetchone()))
    model=lgb.Booster(model_file=str(paths["model"]))
    try:
        begin=time.perf_counter()
        with PeakMemoryMonitor() as monitor:
            quoted_test=str(Path(config["sources"]["test_cache"]).resolve()).replace("'","''"); con.execute(f"CREATE VIEW test_data AS SELECT * FROM read_parquet('{quoted_test}')")
            create_test_features(con); con.execute(f"COPY (SELECT * FROM test_features ORDER BY row_id) TO '{str(paths['test_features'].resolve()).replace(chr(39),chr(39)*2)}' (FORMAT PARQUET,COMPRESSION ZSTD)")
            test_table=con.execute("SELECT * FROM test_features ORDER BY row_id").to_arrow_table(); predictions=np.asarray(model.predict(arrow_matrix(test_table,APPROVED_FEATURES),num_threads=2),dtype=np.float64)
            if len(predictions)!=EXPECTED_ROWS or not np.isfinite(predictions).all(): raise ValidationError("invalid Test predictions")
            pq.write_table(pa.table({"ID":test_table["ID"],"Target":pa.array(predictions)}),paths["predictions"],compression="zstd"); write_submission(paths["submission"],test_table["ID"].to_pylist(),predictions)
        peak=monitor.peak_bytes; stage["prediction_and_write"]={"runtime_seconds":time.perf_counter()-begin,"peak_memory_mb":peak/1024**2}
        begin=time.perf_counter(); validation=independent_validate_submission(paths["submission"],Path(config["sources"]["official_test"]),Path(config["sources"]["official_sample_submission"])); stage["independent_validation"]={"runtime_seconds":time.perf_counter()-begin}
        quantile_points=(0,.01,.05,.25,.5,.75,.95,.99,1); quantiles=np.quantile(predictions,quantile_points); quotas={str(k):int(v) for k,v in config["sampling"]["retained_by_horizon"].items()}
        manifest={"schema_version":"phase2g-submission-manifest-v1","run_id":run_id,"started_utc":started.isoformat().replace("+00:00","Z"),"starting_git_checkpoint":"b3003209ec29c860498a93bf5163784fe720a64c","configuration_id":canonical_sha256(config),"phase2d_configuration_id":config["sources"]["phase2d_configuration_id"],"official_identities":{k:config["sources"][k] for k in ("train_sha256","test_sha256","sample_submission_sha256")},"validation_identity":config["sources"]["validation_identity"],"comparable_row_identity":config["sources"]["comparable_row_identity"],"phase2e_candidate":{"model":"lightgbm_basic","run_id":"run-20260904T064720Z-lightgbm_basic","decision":"preferred"},"final_fit_policy":{"cutoff":str(config["training_cutoff"]),"eligible_by_horizon":population,"retained_by_horizon":quotas,"sampling_seed":config["seed"],"algorithm":config["sampling"]["algorithm"],"weights":config["sampling"]["weights"],"retained_identity":retained_id},"features":list(APPROVED_FEATURES),"lightgbm":{"parameters":model_config["parameters"],"num_boost_round":200},"dependencies":{"lightgbm":lgb.__version__,"numpy":np.__version__,"duckdb":duckdb.__version__,"pyarrow":pa.__version__},"artifacts":{k:_artifact(paths[k]) for k in ("training_artifact","model","test_features","predictions","submission")},"submission":{"filename":paths["submission"].as_posix(),"rows":EXPECTED_ROWS,"columns":["ID","Target"],"upload_status":"not_uploaded"},"independent_validation":validation,"prediction_diagnostics":{"minimum":float(predictions.min()),"maximum":float(predictions.max()),"mean":float(predictions.mean()),"standard_deviation":float(predictions.std()),"quantiles":{str(q):float(v) for q,v in zip(quantile_points,quantiles,strict=True)},"final_fit_target_range":target_range,"below_target_range":int((predictions<target_range[0]).sum()),"above_target_range":int((predictions>target_range[1]).sum())},"stages":stage,"resume_runtime_seconds":time.perf_counter()-total_start,"peak_memory_mb_resume":peak/1024**2,"execution_discrepancy":"upstream timing/peak telemetry was lost when the original process failed after fitting; upstream artifacts were preserved and not rerun","registry_handling":"unchanged; registry contains validation experiments only","production_step_counts":{"materialization":1,"fitting":1,"prediction":1,"candidate_write":1,"independent_validation":1}}
        _write_json_atomic(paths["manifest"],manifest); return manifest
    finally: con.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--config",type=Path,default=Path("configs/phase2g_submission.yaml")); parser.add_argument("--resume-after-fit",action="store_true"); args=parser.parse_args(argv)
    result=resume_after_fit(args.config) if args.resume_after_fit else run(args.config); print(json.dumps({"run_id":result["run_id"],"submission":result["submission"],"independent_validation":result["independent_validation"]},sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
