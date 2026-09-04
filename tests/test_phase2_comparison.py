"""Focused Phase 2E registry and comparison tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from drought_forecasting.experiment_registry import FIELDS
from drought_forecasting.phase2_comparison import (
    COMPARABLE_ID,
    DATA_ID,
    EXPECTED_MODELS,
    VALIDATION_ID,
    ComparisonError,
    build_comparison,
    validate_and_load,
)


def artifact(run_id: str, rmse: float = 1.0) -> dict:
    result = {"count": 1, "rmse": rmse}
    return {
        "run_id": run_id, "configuration_id": "a"*64, "data_manifest_id": DATA_ID,
        "validation_id": VALIDATION_ID, "comparable_rows": {"sha256": COMPARABLE_ID},
        "coverage": {"predicted": 551965, "expected": 551965, "fraction": 1.0},
        "metrics": {"pooled": {"count":551965,"rmse":rmse},
                    "fold":{"F01":result,"F02":{"count":1,"rmse":rmse+0.1}},
                    "horizon":{str(i):result for i in range(1,8)},
                    "mask_state":{"observed":result,"masked/unavailable":result},
                    "latitude_band":{"[0,30)":result},"spei":{"SPEI_01_t":{"[-1,1)":result}}},
        "runtime_seconds":1.0,"peak_memory_mb":2.0,"decision":"keep","decision_reason":"fixture",
        "oof_artifact":{"path":"artifacts/oof","sha256":"b"*64,"size_bytes":10},"fallback_counts":{},
    }


def write_fixture(root: Path, updates=None):
    records=[]
    for index,model in enumerate(EXPECTED_MODELS):
        run_id=f"run-20260904T{index:06d}Z-{model[:31]}"; value=artifact(run_id,0.5+index/10)
        if model=="lightgbm_basic":
            value.pop("data_manifest_id"); value.pop("validation_id"); value.pop("comparable_rows")
            value["identities"]={"data_manifest":DATA_ID,"validation":VALIDATION_ID,"comparable_rows":COMPARABLE_ID}
            value["models"]={"F01":{"sha256":"c"*64,"size_bytes":1},"F02":{"sha256":"d"*64,"size_bytes":1}}
            value["oof"] = value.pop("oof_artifact")
        path=root/f"{index}-metrics.json"; path.write_text(json.dumps(value),encoding="utf-8")
        relative_path = path.relative_to(Path.cwd()).as_posix()
        record={field:"x" for field in FIELDS}; record.update({"run_id":run_id,"run_date_utc":f"2026-09-04T00:00:0{index}Z","git_commit":"a"*40,"data_version":DATA_ID,"validation_version":"validation-v1","seed":"0","features":"[]","model":model,"model_parameters":"{}","overall_cv_rmse":str(value["metrics"]["pooled"]["rmse"]),"rmse_by_horizon":"{}","regional_or_subgroup_metrics":"{}","runtime_seconds":"1.0","peak_memory_mb":"2.0","model_size_mb":"0","submission_score":"","artifact_paths":json.dumps([relative_path]),"decision":"keep","decision_reason":"fixture","notes":""})
        records.append(record)
    if updates: updates(records, root)
    registry=root/'registry.csv'
    with registry.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader();writer.writerows(records)
    return registry


@pytest.mark.parametrize("mutation,message",[
    (lambda r,p:r.__setitem__(1,dict(r[0])),"duplicate run_id"),
    (lambda r,p:r[0].__setitem__('decision_reason',''),"required metadata"),
    (lambda r,p:Path(json.loads(r[0]['artifact_paths'])[0]).unlink(),"missing"),
    (lambda r,p:r[0].__setitem__('overall_cv_rmse','nan'),"finite"),
])
def test_invalid_registry_evidence_is_rejected(tmp_path: Path,mutation,message):
    registry=write_fixture(tmp_path,mutation)
    with pytest.raises((ComparisonError,ValueError),match=message): validate_and_load(registry)


def test_coverage_artifact_mismatch_and_mixed_identity_rejected(tmp_path: Path):
    registry=write_fixture(tmp_path); rows=list(csv.DictReader(registry.open()))
    path=Path(json.loads(rows[0]['artifact_paths'])[0]); value=json.loads(path.read_text());value['coverage']['predicted']=1;path.write_text(json.dumps(value))
    with pytest.raises(ComparisonError,match="coverage"):validate_and_load(registry)
    registry=write_fixture(tmp_path); rows=list(csv.DictReader(registry.open()));path=Path(json.loads(rows[0]['artifact_paths'])[0]);value=json.loads(path.read_text());value['comparable_rows']['sha256']='e'*64;path.write_text(json.dumps(value))
    with pytest.raises(ComparisonError,match="comparable"):validate_and_load(registry)


def test_ranking_fold_gap_improvement_and_horizons(tmp_path: Path):
    loaded=validate_and_load(write_fixture(tmp_path)); comparison=build_comparison(loaded)
    assert [run['pooled_rmse'] for run in comparison['runs']]==sorted(run['pooled_rmse'] for run in comparison['runs'])
    first=comparison['runs'][0]; assert first['absolute_fold_gap']==pytest.approx(0.1)
    assert set(first['horizon_rmse'])=={str(i) for i in range(1,8)}
    assert comparison['preferred']['persistence_absolute_improvement']==pytest.approx(0.3)
    assert comparison['preferred']['persistence_percentage_improvement']==pytest.approx(37.5)


def test_nondeterministic_order_is_rejected(tmp_path: Path):
    registry=write_fixture(tmp_path,lambda rows,root:rows.reverse())
    with pytest.raises(ComparisonError,match="order"):validate_and_load(registry)
