from pathlib import Path

from drought_forecasting.phase5_catboost import load_config, model_parameters, promotion_gate


def _metrics(rmse: float = 0.57, count: int = 551_965) -> dict:
    return {
        "pooled": {"rmse": rmse, "count": count},
        "fold": {"F01": {"rmse": 0.57}, "F02": {"rmse": 0.57}},
        "horizon": {"6": {"rmse": 0.63}, "7": {"rmse": 0.68}},
    }


def test_configuration_is_fixed_cpu_catboost() -> None:
    config = load_config(Path("configs/phase5.yaml"))
    params = model_parameters(config)
    assert config["population"]["training"]["pooled"] == 2_000_000
    assert config["categorical_features"] == ["location_id"]
    assert params["task_type"] == "CPU"
    assert params["thread_count"] == 2
    assert params["iterations"] == 200
    assert config["controls"]["early_stopping"] is False


def test_promotion_gate_requires_every_check() -> None:
    assert promotion_gate(_metrics(), 0.57, 0.57, 2500)["eligible"] is True
    assert promotion_gate(_metrics(rmse=0.58), 0.57, 0.57, 2500)["eligible"] is False
    assert promotion_gate(_metrics(count=1), 0.57, 0.57, 2500)["eligible"] is False
