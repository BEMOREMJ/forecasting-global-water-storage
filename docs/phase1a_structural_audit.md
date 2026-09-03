# Phase 1A structural data audit

**Status:** approved structural evidence
**Scope:** data structure and target semantics only; no model or baseline was trained or scored.

## Dataset shape and alignment

| Dataset | Rows | Columns | Input-date range | Distinct input months |
|---|---:|---:|---|---:|
| Train | 2,154,021 | 13 | 2002-05-01 to 2015-08-01 | 138 |
| Test | 280,961 | 13 | 2015-09-01 to 2018-12-01 | 18 |
| SampleSubmission | 280,961 | 2 | Encoded in `ID` | 18 |

Test and SampleSubmission contain the same 280,961 unique IDs in exactly the same order.
There are no missing or extra IDs and no positional mismatch. Test's 186,913 null `TWS_t`
values exactly equal its 186,913 true `TWS_t_masked` flags: no masked row retains TWS and no
unmasked row lacks it. The masked share is 66.5263%.

## Spatial grid

Train and Test each contain 15,715 distinct `(lat, lon)` locations, all shared: there are zero
Train-only and zero Test-only locations. Coordinates are half-degree-centred on a nominal
one-degree grid. Latitudes comprise 140 values from -55.5 to 83.5 at one-degree spacing;
longitudes comprise 358 values from -179.5 to 179.5. Longitude centres -169.5 and -168.5 are
absent, producing the sole three-degree step. Only 15,715 of the 50,120 possible combinations
occur, so this is a spatially masked grid rather than a complete rectangle.

Train observations per location range from 11 to 138 (median 138); 14,558 locations contain
all 138 supplied Train dates. Test observations range from 1 to 18 (median 18); 15,226
locations contain all 18 supplied Test dates. Five locations have only 11 Train rows and five
locations have only one Test row.

## Calendar coverage

All timestamps are first-of-month dates, but the panel is discontinuous. The Train calendar
span contains 22 globally absent months: 2002-06 to 2002-08, 2003-06 to 2003-07, 2011-01 to
2011-02, 2011-06 to 2011-07, 2012-05 to 2012-06, 2012-10 to 2012-11, 2013-03 to 2013-04,
2013-08 to 2013-10, 2014-02 to 2014-03, and 2014-07 to 2014-08.

The 18 Test input months are 2015-09; 2016-01, 2016-02, 2016-03, 2016-06, 2016-07,
2016-08, 2016-09, 2016-12; 2017-01 through 2017-06; 2018-07, 2018-11, and 2018-12.
Within-location sequences contain 160,908 Train adjacent-record pairs and 78,333 Test pairs
whose calendar separation exceeds one month. Maximum separations are 36 and 24 months,
respectively. Some location rows are also absent within otherwise represented months.

Rows per supplied month range from 15,510 to 15,681 in Train and 15,520 to 15,677 in Test.
There are no duplicate `(time, lat, lon)` records and no non-increasing within-location
transitions. Calendar-month joins are mandatory: the next available observation is not `t+1`.

## Identifier construction

Every Train `sample_id` and Test `ID` reconstructs exactly as `YYYYMMDD_lat_lon`. The date
component equals `time`, and the coordinate components equal `lat` and `lon`, for every row.
Thus IDs encode both input month and location.

## Target semantics

The audit joined each Train row to TWS at the same exact location and exact next calendar
month. It did not use row shifts or the next available observation.

| Evidence category | Rows | Result |
|---|---:|---|
| Exact `t+1` TWS found within Train | 1,977,398 | All target/TWS pairs match exactly |
| August 2015 Train target joined to September 2015 Test TWS | 15,503 | All pairs match exactly |
| Calendar gap followed by later nonconsecutive Train data | 160,908 | Exact `t+1` TWS unavailable |
| Location's Train history ends before August 2015 | 180 | Exact `t+1` TWS unavailable; 180 rows at 180 locations, one terminal row each |
| August 2015 row without a September 2015 Test row | 32 | Exact `t+1` TWS unavailable |

Wherever a same-location TWS observation exists at exactly the next calendar month, the
training target equals that TWS value exactly. This is verified for 1,992,901 rows, with zero
mismatches and zero absolute difference at all tested tolerances. The remaining 161,120 rows
are unverifiable because their exact next-month TWS observation is unavailable, not because a
mismatch was found.

The 176,623 rows without a Train-only `t+1` successor partition without overlap into 160,908
calendar-gap rows, 180 early-terminal rows, and 15,535 global-final-month rows. The last group
further divides into 15,503 boundary-verified rows and 32 rows without a September successor.

This equality is an outcome definition. It must not be used to construct features from future
observed TWS or otherwise bypass prediction-time availability.

## Starter-notebook claims

The official notebook's flat, one-row-per-sample structure, ID format, nominal one-degree
grid, next-month target, approximately two-thirds test masking, mask-flag behavior, lack of
future `_tp1` columns, and direct Test/SampleSubmission alignment were independently verified.
Its description of monthly data requires the discontinuity qualification above. Statements
about masking intent, TWS persistence, feature suitability, and imputation are organizer or
modelling claims and are not approved by this structural audit.

## Boundaries of the evidence

The supplied files do not establish operational publication time, whether recursively
generated TWS may be reused, or whether organizer intent permits any uncertain feature use.
No modelling advice is inferred from target equality or spatial overlap. These matters remain
for later Phase 1 availability, masking, leakage, and validation work.
