"""Pure calendar, location, provenance, and horizon validation semantics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ValidationError(ValueError):
    """Raised when a validation semantic or invariant is violated."""


class TWSProvenance(StrEnum):
    """Immutable provenance labels for Total Water Storage values."""

    OBSERVED = "observed"
    MASKED = "masked/unavailable"
    MODEL_GENERATED = "model-generated"


@dataclass(frozen=True, order=True)
class LocationKey:
    """Lossless half-degree coordinate key represented without floating-point strings."""

    lat2: int
    lon2: int

    def __post_init__(self) -> None:
        if isinstance(self.lat2, bool) or not isinstance(self.lat2, int):
            raise ValidationError("lat2 must be an integer")
        if isinstance(self.lon2, bool) or not isinstance(self.lon2, int):
            raise ValidationError("lon2 must be an integer")
        if not -180 <= self.lat2 <= 180:
            raise ValidationError("lat2 must represent a latitude between -90 and 90")
        if not -360 <= self.lon2 <= 360:
            raise ValidationError("lon2 must represent a longitude between -180 and 180")

    def as_tuple(self) -> tuple[int, int]:
        """Return the canonical sortable integer pair."""
        return self.lat2, self.lon2

    def serialize(self) -> str:
        """Return a stable, unambiguous serialization containing integers only."""
        return f"lat2={self.lat2};lon2={self.lon2}"


def validate_month(month: date) -> date:
    """Return a month-start date or reject a non-date or non-month-start value."""
    if isinstance(month, bool) or not isinstance(month, date):
        raise ValidationError("month must be a date")
    if month.day != 1:
        raise ValidationError("month must be the first day of a calendar month")
    return month


def add_calendar_months(month: date, offset: int) -> date:
    """Add a signed number of calendar months without day-based approximation."""
    validate_month(month)
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise ValidationError("calendar-month offset must be an integer")
    absolute_month = month.year * 12 + month.month - 1 + offset
    if absolute_month < 12:
        raise ValidationError("calendar-month result is outside the supported date range")
    year, zero_based_month = divmod(absolute_month, 12)
    try:
        return date(year, zero_based_month + 1, 1)
    except ValueError as exc:
        raise ValidationError("calendar-month result is outside the supported date range") from exc


def target_month(input_month: date) -> date:
    """Return the exact next calendar month for an input event."""
    return add_calendar_months(input_month, 1)


def calendar_month_distance(start: date, end: date) -> int:
    """Return signed whole-calendar-month distance from ``start`` to ``end``."""
    validate_month(start)
    validate_month(end)
    return (end.year - start.year) * 12 + end.month - start.month


def location_key(lat: float, lon: float) -> LocationKey:
    """Convert finite, bounded half-degree coordinates to a lossless integer key."""
    if isinstance(lat, bool) or isinstance(lon, bool):
        raise ValidationError("coordinates must be finite real numbers")
    try:
        finite = math.isfinite(lat) and math.isfinite(lon)
    except TypeError as exc:
        raise ValidationError("coordinates must be finite real numbers") from exc
    if not finite:
        raise ValidationError("coordinates must be finite real numbers")
    if not -90 <= lat <= 90:
        raise ValidationError("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise ValidationError("longitude must be between -180 and 180")

    lat_doubled = float(lat) * 2
    lon_doubled = float(lon) * 2
    if not lat_doubled.is_integer() or not lon_doubled.is_integer():
        raise ValidationError("coordinates must be losslessly representable at half-degree precision")
    return LocationKey(int(lat_doubled), int(lon_doubled))


def require_same_location(source: LocationKey, event: LocationKey) -> None:
    """Reject a source whose stable location key differs from the prediction event."""
    if source != event:
        raise ValidationError("TWS source and prediction event must have the same location")


def effective_horizon(last_observed_month: date, input_month: date) -> int:
    """Measure months from last genuinely observed TWS to the input row's target month."""
    validate_month(last_observed_month)
    validate_month(input_month)
    if last_observed_month > input_month:
        raise ValidationError("last observed TWS month cannot be after the input event")
    return calendar_month_distance(last_observed_month, target_month(input_month))


def require_observed_only_history(provenance: TWSProvenance) -> None:
    """Enforce that a TWS value may enter the principal observed-only history."""
    if not isinstance(provenance, TWSProvenance):
        raise ValidationError("TWS provenance must be a TWSProvenance value")
    if provenance is not TWSProvenance.OBSERVED:
        raise ValidationError(
            f"{provenance.value} TWS cannot enter principal observed-only history"
        )
