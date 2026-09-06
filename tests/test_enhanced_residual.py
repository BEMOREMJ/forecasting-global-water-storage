from datetime import date
from pathlib import Path

import numpy as np

from drought_forecasting.enhanced_residual import history_features, load_config, spatial_encodings


def test_feature_order_and_raw_year_are_frozen() -> None:
    cfg=load_config(Path("configs/phase3m2_enhanced_residual.yaml")); names=[x["name"] for x in cfg["added_features"]]
    assert cfg["base_features"][4]=="input_year"; assert names[0]=="second_last_observed_tws"; assert names[-1]=="soil_anomaly_reference_available"; assert len(cfg["base_features"])+len(names)==32


def test_second_last_gap_slope_and_availability() -> None:
    x=history_features(2.0,date(2010,4,1),1.0,date(2010,2,1),0.5)
    assert x["observation_gap_months"]==2; assert x["historical_tws_slope"]==0.5; assert x["second_last_available"]==1; assert x["seasonal_difference"]==1.5


def test_missing_history_stays_missing_with_zero_indicator() -> None:
    x=history_features(2.0,date(2010,4,1),None,None,None)
    assert np.isnan(x["historical_tws_slope"]); assert np.isnan(x["seasonal_difference"]); assert x["second_last_available"]==0; assert x["seasonal_available"]==0


def test_spatial_encodings_use_degrees_and_are_bounded() -> None:
    a=spatial_encodings(np.array([0.0,90.0]),np.array([0.0,180.0])); assert np.allclose(a[0],[0,1]); assert np.allclose(a[3],[1,-1]); assert all(np.max(np.abs(x))<=1 for x in a)


def test_soil_reference_is_fold_local_and_predictor_only() -> None:
    cfg=load_config(Path("configs/phase3m2_enhanced_residual.yaml")); assert cfg["soil_reference"]["validation_or_target_fitting"]=="forbidden"; assert cfg["soil_reference"]["fitting_population"].startswith("distinct_location")


def test_provenance_forbids_unsafe_sources() -> None:
    p=load_config(Path("configs/phase3m2_enhanced_residual.yaml"))["provenance"]; assert p["canonical_location_required"] and p["source_timestamp_at_or_before_input"]; assert p["validation_target_source_forbidden"] and p["future_source_forbidden"] and p["adjacent_row_assumption_forbidden"]
