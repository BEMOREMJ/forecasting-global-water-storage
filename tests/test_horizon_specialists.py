from pathlib import Path

import pytest

from drought_forecasting.horizon_specialists import GROUPS, group_for
from drought_forecasting.residual_benchmark import load_config
from drought_forecasting.validation_core import ValidationError


def test_mapping_complete_exclusive():
 assert [group_for(x) for x in range(1,8)]==["G1","G23","G23","G47","G47","G47","G47"]
 assert set().union(*map(set,GROUPS.values()))==set(range(1,8))
@pytest.mark.parametrize("h",[0,8,-1])
def test_bad_horizon(h):
 with pytest.raises(ValidationError):group_for(h)
def test_schema_is_m3b():
 assert "input_year" not in load_config(Path("configs/phase3m3b_no_year_residual.yaml"))["features"]
