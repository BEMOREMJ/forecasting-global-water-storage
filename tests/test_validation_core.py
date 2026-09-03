from __future__ import annotations

from datetime import date

import pytest

from drought_forecasting.validation_core import (
    LocationKey,
    TWSProvenance,
    ValidationError,
    add_calendar_months,
    calendar_month_distance,
    effective_horizon,
    location_key,
    require_observed_only_history,
    require_same_location,
    target_month,
    validate_month,
)


@pytest.mark.parametrize(
    ("month", "offset", "expected"),
    [
        (date(2010, 3, 1), 5, date(2010, 8, 1)),
        (date(2010, 12, 1), 1, date(2011, 1, 1)),
        (date(2011, 1, 1), -1, date(2010, 12, 1)),
        (date(2004, 2, 1), 24, date(2006, 2, 1)),
        (date(2004, 2, 1), -25, date(2002, 1, 1)),
    ],
)
def test_t001_calendar_month_addition(
    month: date, offset: int, expected: date
) -> None:
    """T001: calendar arithmetic includes year boundaries and signed offsets."""
    assert add_calendar_months(month, offset) == expected


def test_t001_leap_year_uses_month_arithmetic() -> None:
    """T001: February length cannot alter month-start arithmetic."""
    assert add_calendar_months(date(2020, 1, 1), 1) == date(2020, 2, 1)
    assert add_calendar_months(date(2020, 2, 1), 1) == date(2020, 3, 1)
    assert add_calendar_months(date(2019, 2, 1), 12) == date(2020, 2, 1)


def test_t001_target_month_is_exact_next_month() -> None:
    assert target_month(date(2015, 12, 1)) == date(2016, 1, 1)


@pytest.mark.parametrize("value", [date(2020, 1, 2), date(2020, 2, 29), "2020-01-01"])
def test_t001_non_month_start_or_non_date_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="month"):
        validate_month(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("offset", [True, 1.0, "1"])
def test_t001_non_integer_month_offset_is_rejected(offset: object) -> None:
    with pytest.raises(ValidationError, match="offset"):
        add_calendar_months(date(2020, 1, 1), offset)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2020, 1, 1), date(2020, 4, 1), 3),
        (date(2020, 4, 1), date(2020, 4, 1), 0),
        (date(2021, 2, 1), date(2020, 11, 1), -3),
    ],
)
def test_t001_signed_calendar_month_distance(
    start: date, end: date, expected: int
) -> None:
    assert calendar_month_distance(start, end) == expected


def test_t002_calendar_gap_is_not_compressed_to_one_month() -> None:
    """T002: row adjacency cannot change the exact calendar-month distance."""
    january = date(2020, 1, 1)
    march = date(2020, 3, 1)
    assert calendar_month_distance(january, march) == 2
    assert add_calendar_months(march, -1) == date(2020, 2, 1)


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (-90.0, -180.0, LocationKey(-180, -360)),
        (90.0, 180.0, LocationKey(180, 360)),
        (0, 0, LocationKey(0, 0)),
        (-0.5, 0.0, LocationKey(-1, 0)),
        (12.5, -43.5, LocationKey(25, -87)),
    ],
)
def test_t004_half_degree_locations_are_lossless(
    lat: float, lon: float, expected: LocationKey
) -> None:
    """T004: stable integer keys retain exact location identity."""
    assert location_key(lat, lon) == expected


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (0.25, 10.0),
        (10.0, -20.25),
        (float("nan"), 0.0),
        (0.0, float("inf")),
        (float("-inf"), 0.0),
        (90.5, 0.0),
        (0.0, 180.5),
    ],
)
def test_t004_invalid_coordinates_are_rejected(lat: float, lon: float) -> None:
    with pytest.raises(ValidationError, match="coordinate|latitude|longitude"):
        location_key(lat, lon)


def test_t004_location_keys_have_stable_equality_ordering_and_serialization() -> None:
    first = location_key(-0.5, 10.0)
    same = LocationKey(-1, 20)
    later = location_key(0.0, -180.0)

    assert first == same
    assert first.as_tuple() == (-1, 20)
    assert first.serialize() == "lat2=-1;lon2=20"
    assert sorted([later, first]) == [first, later]


def test_t004_location_isolation_contract_rejects_cross_location_source() -> None:
    event = location_key(1.5, 2.5)
    require_same_location(event, LocationKey(3, 5))
    with pytest.raises(ValidationError, match="same location"):
        require_same_location(location_key(1.5, 3.0), event)


@pytest.mark.parametrize("horizon", range(1, 8))
def test_t001_t003_effective_horizons_one_through_seven(horizon: int) -> None:
    """T001/T003: horizon is last observed month through exact target month."""
    input_month = date(2020, 8, 1)
    last_observed = add_calendar_months(target_month(input_month), -horizon)
    assert effective_horizon(last_observed, input_month) == horizon


def test_t001_effective_horizon_above_protocol_range_is_valid_core_arithmetic() -> None:
    assert effective_horizon(date(2018, 12, 1), date(2020, 1, 1)) == 14


def test_t003_future_last_observed_month_is_rejected() -> None:
    with pytest.raises(ValidationError, match="after the input event"):
        effective_horizon(date(2020, 2, 1), date(2020, 1, 1))


def test_t014_all_provenance_labels_are_exact_and_distinct() -> None:
    assert [state.value for state in TWSProvenance] == [
        "observed",
        "masked/unavailable",
        "model-generated",
    ]


def test_t003_t014_only_observed_tws_may_enter_observed_only_history() -> None:
    """T003/T014: unavailable or generated values never acquire observed status."""
    require_observed_only_history(TWSProvenance.OBSERVED)
    for forbidden in (TWSProvenance.MASKED, TWSProvenance.MODEL_GENERATED):
        with pytest.raises(ValidationError, match="cannot enter"):
            require_observed_only_history(forbidden)


def test_t014_untyped_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="TWSProvenance"):
        require_observed_only_history("observed")  # type: ignore[arg-type]
