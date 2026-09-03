# Structural data dictionary

**Evidence status:** Phase 1A approved
**Source artifacts:** immutable official CSVs represented by `configs/data_manifest.json`;
structural analysis used the verified Parquet caches.

All dataset timestamps are first-of-month calendar dates. In Train and Test, `time` is the
input or feature month `t`; a row's prediction target is TWS at calendar month `t+1`. The
panel is discontinuous, so the next available row is not necessarily the next calendar month.

## Train

Train contains 2,154,021 rows and 13 columns. No Train field is null.

| Field | Parquet type | Null rows | Meaning and timestamp |
|---|---|---:|---|
| `sample_id` | `VARCHAR` | 0 | Unique identifier, exactly `YYYYMMDD_lat_lon`, using input month `t` and the row coordinates. |
| `time` | `DATE` | 0 | Input month `t`, always the first day of a month. |
| `lat` | `DOUBLE` | 0 | Latitude of the one-degree grid-cell centre. |
| `lon` | `DOUBLE` | 0 | Longitude of the one-degree grid-cell centre. |
| `TWS_t` | `DOUBLE` | 0 | Observed Total Water Storage at input month `t`. |
| `SPEI_01_t` | `DOUBLE` | 0 | One-month Standardized Precipitation Evapotranspiration Index at `t`. |
| `SPEI_03_t` | `DOUBLE` | 0 | Three-month SPEI at `t`. |
| `SPEI_06_t` | `DOUBLE` | 0 | Six-month SPEI at `t`. |
| `SPEI_12_t` | `DOUBLE` | 0 | Twelve-month SPEI at `t`. |
| `SOIL_MOISTURE_t` | `DOUBLE` | 0 | Soil moisture covariate at `t`. |
| `month_sin` | `DOUBLE` | 0 | Sine encoding of the calendar month at `t`. |
| `month_cos` | `DOUBLE` | 0 | Cosine encoding of the calendar month at `t`. |
| `target` | `DOUBLE` | 0 | TWS outcome for calendar month `t+1`. |

## Test

Test contains 280,961 rows and 13 columns. It has the same spatial locations and feature
meanings as Train.

| Field | Parquet type | Null rows | Meaning and timestamp |
|---|---|---:|---|
| `ID` | `VARCHAR` | 0 | Unique identifier, exactly `YYYYMMDD_lat_lon`, using input month `t` and the row coordinates. |
| `time` | `DATE` | 0 | Input month `t`, always the first day of a month. |
| `lat` | `DOUBLE` | 0 | Latitude of the grid-cell centre. |
| `lon` | `DOUBLE` | 0 | Longitude of the grid-cell centre. |
| `TWS_t` | `DOUBLE` | 186,913 | TWS at `t`; null exactly where `TWS_t_masked` is true. |
| `SPEI_01_t` | `DOUBLE` | 0 | One-month SPEI at `t`. |
| `SPEI_03_t` | `DOUBLE` | 0 | Three-month SPEI at `t`. |
| `SPEI_06_t` | `DOUBLE` | 0 | Six-month SPEI at `t`. |
| `SPEI_12_t` | `DOUBLE` | 0 | Twelve-month SPEI at `t`. |
| `SOIL_MOISTURE_t` | `DOUBLE` | 0 | Soil moisture covariate at `t`. |
| `month_sin` | `DOUBLE` | 0 | Sine encoding of the calendar month at `t`. |
| `month_cos` | `DOUBLE` | 0 | Cosine encoding of the calendar month at `t`. |
| `TWS_t_masked` | `BOOLEAN` | 0 | True exactly for rows whose `TWS_t` is null. |

## SampleSubmission

SampleSubmission contains 280,961 rows. Its ID sequence is exactly identical to Test.

| Field | Parquet type | Null rows | Meaning |
|---|---|---:|---|
| `ID` | `VARCHAR` | 0 | Test row identifier in official submission order. |
| `Target` | `BIGINT` | 0 | Placeholder prediction; all supplied values are zero. |

## Stable keys and temporal controls

- The natural row key is `(time, lat, lon)`; no duplicate key occurs in Train or Test.
- A stable location key may use exact `(lat, lon)` or the lossless integer pair
  `(2 * lat, 2 * lon)`. The integer representation is preferred for generated IDs.
- Temporal comparisons must join on location and exact calendar month. A row shift or the next
  available observation is unsafe because the panel contains calendar gaps.
- The exact target identity describes the outcome. It does not authorize use of future TWS
  that would be unavailable at prediction time.
- Operational availability, recursive prediction policy, and permitted feature derivation
  remain unresolved until later Phase 1 subphases.
