import csv
from pathlib import Path

import duckdb
import numpy as np
import pytest

import drought_forecasting.submission_candidate as candidate
from drought_forecasting.lightgbm_benchmark import APPROVED_FEATURES
from drought_forecasting.validation_core import ValidationError


def _official(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,lineterminator="\n"); writer.writerow(header); writer.writerows(rows)


def test_final_fit_exact_calendar_cutoff_and_deterministic_selection() -> None:
    con=duckdb.connect(":memory:")
    con.execute("""CREATE TABLE source(time DATE,lat DOUBLE,lon DOUBLE,TWS_t DOUBLE,SPEI_01_t DOUBLE,SPEI_03_t DOUBLE,SPEI_06_t DOUBLE,SPEI_12_t DOUBLE,SOIL_MOISTURE_t DOUBLE,month_sin DOUBLE,month_cos DOUBLE,target DOUBLE)""")
    for month,tws,target in (("2000-01-01",1.,2.),("2000-02-01",2.,3.),("2000-03-01",999.,4.)):
        con.execute("INSERT INTO source VALUES (?,1,2,?,1,1,1,1,1,0,1,?)",[month,tws,target])
    con.execute("CREATE TABLE keyed AS SELECT round(lat*2)::INTEGER lat2,round(lon*2)::INTEGER lon2,* FROM source")
    from datetime import date

    from drought_forecasting.horizon_examples import create_fold_candidates
    create_fold_candidates(con,fold_id="FINAL",cutoff=date(2000,2,1),output_relation="c",train_relation="keyed")
    assert con.execute("SELECT max(target_month),max(last_observed_tws) FROM c").fetchone()==(date(2000,2,1),1.)
    candidate.select_final_fit(con,candidates="c",output="a",quotas={1:1,2:0,3:0,4:0,5:0,6:0,7:0})
    candidate.select_final_fit(con,candidates="c",output="b",quotas={1:1,2:0,3:0,4:0,5:0,6:0,7:0})
    assert con.execute("SELECT example_key FROM a").fetchall()==con.execute("SELECT example_key FROM b").fetchall()


def test_duplicate_training_examples_rejected() -> None:
    con=duckdb.connect(":memory:"); con.execute("CREATE TABLE x(example_key VARCHAR)"); con.execute("INSERT INTO x VALUES ('a'),('a')")
    with pytest.raises(ValidationError,match="duplicated"):
        from drought_forecasting.horizon_examples import validate_examples
        validate_examples(con,"x")


def test_config_preserves_phase2d_features() -> None:
    config=candidate.load_config(Path("configs/phase2g_submission.yaml"))
    assert tuple(APPROVED_FEATURES)==("last_observed_tws","effective_horizon","latitude","longitude","input_year","input_calendar_month","month_sin","month_cos","SPEI_01_t","SPEI_03_t","SPEI_06_t","SPEI_12_t","SOIL_MOISTURE_t")
    assert config["sampling"]["cap"]==2_000_000


def test_csv_is_deterministic_and_validator_rejects_structural_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate,"EXPECTED_ROWS",3)
    header=["ID","time","lat","lon","TWS_t","SPEI_01_t","SPEI_03_t","SPEI_06_t","SPEI_12_t","SOIL_MOISTURE_t","month_sin","month_cos","TWS_t_masked"]
    test=tmp_path/"Test.csv"; sample=tmp_path/"Sample.csv"
    _official(test,header,[["a"]+["0"]*12,["b"]+["0"]*12,["c"]+["0"]*12]); _official(sample,["ID","Target"],[["a","0"],["b","0"],["c","0"]])
    one=tmp_path/"one.csv"; two=tmp_path/"two.csv"
    assert candidate.write_submission(one,["a","b","c"],[1.,2.,3.])
    assert candidate.write_submission(two,["a","b","c"],[1.,2.,3.])==candidate._sha256(one)
    assert candidate.independent_validate_submission(one,test,sample)["status"]=="pass"
    cases={"reordered":[["b","1"],["a","2"],["c","3"]],"duplicate":[["a","1"],["a","2"],["c","3"]],"missing":[["a","1"],["b","2"]],"extra":[["a","1"],["b","2"],["c","3"],["d","4"]],"nonfinite":[["a","nan"],["b","2"],["c","3"]]}
    for name,rows in cases.items():
        bad=tmp_path/f"{name}.csv"; _official(bad,["ID","Target"],rows)
        with pytest.raises(ValidationError): candidate.independent_validate_submission(bad,test,sample)
    for header_bad in (["Target","ID"],["","ID","Target"]):
        bad=tmp_path/("bad"+str(len(header_bad))+".csv"); _official(bad,list(header_bad),[["1"]*len(header_bad)]*3)
        with pytest.raises(ValidationError,match="wrong columns"): candidate.independent_validate_submission(bad,test,sample)


def test_writer_rejects_missing_nonfinite_and_wrong_count(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    monkeypatch.setattr(candidate,"EXPECTED_ROWS",2)
    with pytest.raises(ValidationError): candidate.write_submission(tmp_path/"a.csv",["a"],[1.])
    with pytest.raises(ValidationError): candidate.write_submission(tmp_path/"b.csv",["a","b"],[1.,np.inf])
