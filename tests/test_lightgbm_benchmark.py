"""Focused Phase 2D LightGBM configuration and safety tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from drought_forecasting.lightgbm_benchmark import (
    APPROVED_FEATURES,
    _prediction_table,
    arrow_matrix,
    create_validation_features,
    load_config,
    registry_record,
    train_fixture_model,
    training_table,
    validate_feature_list,
)
from drought_forecasting.prediction_contract import (
    ComparableRowIdentity,
    comparable_row_identity,
    validate_prediction_rows,
)
from drought_forecasting.validation_core import ValidationError


def test_frozen_parameters_and_exact_feature_order() -> None:
    config = load_config(Path("configs/phase2d_lightgbm.yaml"))
    assert tuple(config["features"]) == APPROVED_FEATURES
    assert config["num_boost_round"] == 200
    assert config["parameters"]["num_threads"] == 2
    assert config["parameters"]["deterministic"] is True


def test_unapproved_or_reordered_features_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unapproved"):
        validate_feature_list([*APPROVED_FEATURES, "target_encoding"])
    with pytest.raises(ValidationError, match="ordering"):
        validate_feature_list(list(reversed(APPROVED_FEATURES)))


def test_arrow_matrix_schema_compatibility_and_nonfinite_rejection() -> None:
    table = pa.table({feature: [1.0, 2.0] for feature in APPROVED_FEATURES})
    assert arrow_matrix(table, APPROVED_FEATURES).shape == (2, 13)
    bad = table.set_column(0, APPROVED_FEATURES[0], pa.array([1.0, float("nan")]))
    with pytest.raises(ValidationError, match="nonfinite"):
        arrow_matrix(bad, APPROVED_FEATURES)


def test_repeatable_fixture_predictions_with_fixed_seed() -> None:
    rng = np.random.default_rng(4)
    features = rng.normal(size=(200, len(APPROVED_FEATURES))).astype(np.float32)
    target = (features[:, 0] * 0.5 + features[:, 1]).astype(np.float32)
    config = load_config(Path("configs/phase2d_lightgbm.yaml"))
    first = train_fixture_model(features, target, config["parameters"], 10)
    second = train_fixture_model(features, target, config["parameters"], 10)
    np.testing.assert_array_equal(first, second)


def test_training_table_keeps_folds_separate(tmp_path: Path) -> None:
    values = {feature: [1.0, 2.0] for feature in APPROVED_FEATURES}
    values.update({"target": [1.0, 2.0], "sample_weight": [1.0, 1.0], "fold_id": ["F01", "F02"]})
    path = tmp_path / "examples.parquet"
    pq.write_table(pa.table(values), path)
    assert training_table(path, "F01", APPROVED_FEATURES).num_rows == 1


def test_prediction_coverage_and_nonfinite_output_rejection() -> None:
    validation = pa.table({
        "fold_id": ["F01"], "location_id": ["lat2=0;lon2=0"],
        "input_month": [__import__("datetime").date(2004,9,1)],
        "target_month": [__import__("datetime").date(2004,10,1)],
        "effective_horizon": [1], "mask_state": ["observed"],
        "validation_actual": [1.0], "latitude": [0.0],
        "SPEI_01_t": [0.0], "SPEI_03_t": [0.0], "SPEI_06_t": [0.0], "SPEI_12_t": [0.0],
    })
    assert _prediction_table(validation, np.array([1.0]), run_id="run-20260904T120000Z-test", configuration_id="a"*64).num_rows == 1
    with pytest.raises(ValidationError, match="coverage"):
        _prediction_table(validation, np.array([]), run_id="run-20260904T120000Z-test", configuration_id="a"*64)
    with pytest.raises(ValidationError, match="finiteness"):
        _prediction_table(validation, np.array([np.nan]), run_id="run-20260904T120000Z-test", configuration_id="a"*64)


def test_phase2a_comparable_identity_is_enforced() -> None:
    row = {
        "run_id":"run-20260904T120000Z-test", "fold_id":"F01",
        "location_id":"lat2=0;lon2=0", "input_month":__import__("datetime").date(2004,9,1),
        "target_month":__import__("datetime").date(2004,10,1), "effective_horizon":1,
        "mask_state":"observed", "prediction":1.0, "validation_actual":1.0,
        "model_name":"lightgbm_basic", "configuration_id":"a"*64,
        "data_manifest_id":"b"*64, "validation_id":"c"*64,
    }
    identity = comparable_row_identity([row])
    validate_prediction_rows([row], expected_rows=identity, expected_data_manifest_id="b"*64, expected_validation_id="c"*64)
    with pytest.raises(ValidationError, match="comparable-row identity"):
        validate_prediction_rows([row], expected_rows=ComparableRowIdentity(1,"d"*64), expected_data_manifest_id="b"*64, expected_validation_id="c"*64)


def test_exact_calendar_validation_provenance_and_fold_local_source() -> None:
    con = duckdb.connect()
    con.execute("""CREATE TABLE retained(fold_id VARCHAR,lat2 BIGINT,lon2 BIGINT,input_month DATE,target_month DATE,effective_horizon INTEGER,mask_state BOOLEAN,target_value DOUBLE,last_observed_month DATE);
    INSERT INTO retained VALUES ('F01',0,0,DATE '2004-09-01',DATE '2004-10-01',2,true,3,DATE '2004-08-01');
    CREATE TABLE train_data(time DATE,lat DOUBLE,lon DOUBLE,TWS_t DOUBLE,month_sin DOUBLE,month_cos DOUBLE,SPEI_01_t DOUBLE,SPEI_03_t DOUBLE,SPEI_06_t DOUBLE,SPEI_12_t DOUBLE,SOIL_MOISTURE_t DOUBLE);
    INSERT INTO train_data VALUES (DATE '2004-08-01',0,0,2,0,1,0,0,0,0,0),(DATE '2004-09-01',0,0,999,0,1,0,0,0,0,0);""")
    create_validation_features(con, retained_relation="retained", output_relation="features")
    assert con.execute("SELECT last_observed_tws,effective_horizon,count(*) OVER() FROM features").fetchone() == (2.0,2,1)


def test_registry_record_contains_compact_metrics_and_artifacts() -> None:
    payload = {"run_id":"run-20260904T120000Z-lightgbm_basic","features":list(APPROVED_FEATURES),"configuration":{},"metrics":{"pooled":{"rmse":1.0},"horizon":{},"fold":{},"mask_state":{},"latitude_band":{},"spei":{}},"coverage":{"fraction":1},"runtime_seconds":1,"peak_memory_mb":2,"models":{"F01":{"path":"artifacts/a","size_bytes":1},"F02":{"path":"artifacts/b","size_bytes":1}},"oof":{"path":"artifacts/oof","sha256":"a"*64},"metrics_path":"reports/fixture.json","decision":"reject","decision_reason":"fixture"}
    record = registry_record(payload, datetime(2026,9,4,tzinfo=UTC))
    assert record["model"] == "lightgbm_basic"
    assert "artifacts/oof" in record["artifact_paths"]
