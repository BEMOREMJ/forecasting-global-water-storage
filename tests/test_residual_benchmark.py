from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pytest

from drought_forecasting.residual_benchmark import load_config, reconstruct, residual_target
from drought_forecasting.validation_core import ValidationError


def test_p3m1_changes_only_target_and_retains_raw_year() -> None:
    config = load_config(Path("configs/phase3m1_residual_lightgbm.yaml"))
    assert config["target"]["training"] == "target_minus_last_observed_tws"
    assert config["target"]["raw_year_retained"] is True
    assert config["features"][4] == "input_year"


def test_residual_target_and_reconstruction_round_trip() -> None:
    target = np.array([1.5, -2.0, 0.25])
    anchor = np.array([1.0, -1.25, 0.5])
    residual = residual_target(target, anchor)
    np.testing.assert_allclose(residual, [0.5, -0.75, -0.25])
    np.testing.assert_allclose(reconstruct(anchor, residual), target)


@pytest.mark.parametrize("bad", [np.array([np.nan]), np.array([np.inf])])
def test_rejects_unsafe_nonfinite_anchor(bad: np.ndarray) -> None:
    with pytest.raises(ValidationError):
        residual_target(np.array([1.0]), bad)
    with pytest.raises(ValidationError):
        reconstruct(bad, np.array([0.0]))


def test_timestamp_and_same_location_provenance_predicate() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE anchors(location VARCHAR,input DATE,target DATE,source DATE,source_location VARCHAR)")
    connection.executemany(
        "INSERT INTO anchors VALUES (?,?,?,?,?)",
        [
            ("A", date(2004, 1, 1), date(2004, 2, 1), date(2004, 1, 1), "A"),
            ("A", date(2004, 1, 1), date(2004, 2, 1), date(2004, 2, 1), "A"),
            ("A", date(2004, 1, 1), date(2004, 2, 1), date(2004, 1, 1), "B"),
        ],
    )
    unsafe = connection.execute(
        "SELECT count(*) FROM anchors WHERE source>input OR source_location<>location OR target<>input+INTERVAL 1 MONTH"
    ).fetchone()[0]
    assert unsafe == 2
