# Phase 1C test mask and effective horizons

**Status:** approved empirical analysis
**Scope:** Test masking, effective horizons, and historical-mask feasibility. Fold selection
remains deferred to Phase 1E; no validation fold is frozen here.

## Mask structure

Test contains 280,961 rows. TWS is observed in 94,048 rows (33.473685%) and masked in
186,913 rows (66.526315%). `TWS_t_masked` agrees exactly with TWS nullness: zero flagged rows
retain a value and zero unflagged rows are null. The mask indicator identifies availability;
it does not reveal the hidden TWS value.

| Input month | Rows | Observed | Masked | Masked % |
|---|---:|---:|---:|---:|
| 2015-09 | 15,552 | 15,552 | 0 | 0.000000 |
| 2016-01 | 15,647 | 15,647 | 0 | 0.000000 |
| 2016-02 | 15,663 | 38 | 15,625 | 99.757390 |
| 2016-03 | 15,665 | 17 | 15,648 | 99.891478 |
| 2016-06 | 15,584 | 15,584 | 0 | 0.000000 |
| 2016-07 | 15,591 | 65 | 15,526 | 99.583093 |
| 2016-08 | 15,520 | 36 | 15,484 | 99.768041 |
| 2016-09 | 15,529 | 50 | 15,479 | 99.678022 |
| 2016-12 | 15,618 | 15,618 | 0 | 0.000000 |
| 2017-01 | 15,610 | 29 | 15,581 | 99.814222 |
| 2017-02 | 15,642 | 51 | 15,591 | 99.673955 |
| 2017-03 | 15,677 | 41 | 15,636 | 99.738470 |
| 2017-04 | 15,638 | 21 | 15,617 | 99.865712 |
| 2017-05 | 15,572 | 4 | 15,568 | 99.974313 |
| 2017-06 | 15,584 | 34 | 15,550 | 99.781828 |
| 2018-07 | 15,584 | 15,584 | 0 | 0.000000 |
| 2018-11 | 15,646 | 15,646 | 0 | 0.000000 |
| 2018-12 | 15,639 | 31 | 15,608 | 99.801778 |

The mask is dominated by near-global temporal blocks, with 417 observed exceptions inside
otherwise almost entirely masked months.

### Location-level distributions

- Eight locations have all their available Test TWS observed, but together contain only 14
  rows; none has 18 observed rows.
- 15,707 locations are partially masked.
- No location has every available Test TWS masked.
- Masked rows per location are `0:8, 2:18, 3:9, 4:7, 5:13, 6:29, 7:45, 8:22, 9:125,
  10:109, 11:83, 12:15,247`, expressed as `masked rows:locations`.
- Observed rows per location are `1:5, 2:2, 3:18, 4:31, 5:157, 6:15,438, 7:64`.

All 15,715 locations begin their available Test sequence with observed TWS. When eligible
Train history is also searched, every Test row has a valid genuinely observed same-location
source at or before its input event.

## Two streak concepts

A **calendar-consecutive masked streak** contains masked rows at exact successive calendar
months. A **released-row masked run** contains successive available rows for a location that
are masked, even if their dates are separated. Missing released months do not themselves
become masked rows and must not be counted as part of a calendar-consecutive streak.

The two definitions happen to give the same distribution in Test because no masked-to-masked
released-row pair crosses a calendar gap:

| Length | Streaks or runs | Affected rows | Locations represented |
|---:|---:|---:|---:|
| 1 | 15,799 | 15,799 | 15,649 |
| 2 | 15,701 | 31,402 | 15,639 |
| 3 | 15,516 | 46,548 | 15,465 |
| 4 | 81 | 324 | 81 |
| 5 | 34 | 170 | 34 |
| 6 | 15,445 | 92,670 | 15,445 |
| **Total** | **62,576** | **186,913** | **15,707 overall** |

There are 124,337 masked-to-masked released adjacencies, all calendar-consecutive; 62,576
observed-to-masked transitions, all calendar-consecutive; 46,952 masked-to-observed
transitions, all across calendar gaps; and 31,381 observed-to-observed transitions, all across
calendar gaps. Of the released masked runs, 46,952 end at an observed row and 15,624 end
without a later released row. The two definitions must remain separate in infrastructure even
though their observed length distributions coincide.

## Effective-horizon definition

For a Test row:

```text
target_month = input_month + 1 calendar month
effective_horizon = calendar months from the most recent genuinely observed
                    same-location TWS month to target_month
```

The source search includes eligible Train TWS and only observed Test TWS at or before the
current input event. It excludes later observations and model predictions. An observed Test
input therefore has horizon 1. A masked input's horizon is measured in calendar months from
the most recent genuinely observed same-location TWS to its target month. Later observations
may never fill earlier masks.

| Horizon | Rows | Percentage | Observed inputs | Masked inputs |
|---:|---:|---:|---:|---:|
| 1 | 94,048 | 33.473685 | 94,048 | 0 |
| 2 | 62,576 | 22.272130 | 0 | 62,576 |
| 3 | 46,777 | 16.648930 | 0 | 46,777 |
| 4 | 31,076 | 11.060610 | 0 | 31,076 |
| 5 | 15,560 | 5.538135 | 0 | 15,560 |
| 6 | 15,479 | 5.509306 | 0 | 15,479 |
| 7 | 15,445 | 5.497204 | 0 | 15,445 |
| **Total** | **280,961** | **100.000000** | **94,048** | **186,913** |

The maximum is 7, consistent with the rules' approximate 1-7-month description. Per-location
maximum horizons are `1:8, 2:15, 3:24, 4:108, 5:81, 6:34, 7:15,445`, expressed as
`maximum horizon:locations`.

## Boundary and irregular histories

The August 2015 Train and September 2015 Test boundary contains 15,503 locations in both
months, 32 with August Train but no September Test row, 49 with September Test but no August
Train row, and 131 with neither. Every September TWS value is observed. Locations missing
September begin Test later with observed TWS; locations missing August can use their observed
September input. No boundary case lacks a valid horizon source.

Test contains 15,715 locations. Relative to its 18 distinct released months, 15,226 locations
contain all 18 rows and 489 have sparse official paths, for 1,909 omitted location-month slots.
A location's expected template path consists only of rows actually present for that location in
official Test. Missing released months and location-specific omissions remain absent calendar
entries; they are never created or labelled as masked observations.

## Automated consistency checks

| Assertion | Failures |
|---|---:|
| All 280,961 rows and unique IDs classified exactly once | 0 |
| Observed TWS input not assigned horizon 1 | 0 |
| Missing genuinely observed source | 0 |
| Source after input event | 0 |
| Source from another location | 0 |
| Horizon below 1 or above 7 | 0 |
| Year-boundary calendar arithmetic error | 0 |

## Historical-mask candidates

### Exact relative-calendar/location transplantation

The Test input offsets from September 2015 are `0, 4, 5, 6, 9, 10, 11, 12, 15, 16, 17,
18, 19, 20, 21, 34, 38, 39` months. Exact transplantation maps these relative calendar
offsets and each location's mask path onto a historical origin.

Among 121 calendar-valid origins, 62 contain all 18 input months and 55 contain all 18 input
and corresponding target-TWS months. No origin maps every row because historical
location-month omissions differ from Test.

The strongest examined placement is currently `2006-09`, but it is not a frozen validation
fold. Raw row-wise matching retains 280,813 rows and drops 148. It is rejected because missing
observed anchor rows cause 87 horizon mismatches and an artificial maximum horizon of 13.

Strict complete-location filtering keeps only locations that reproduce every row in their own
actual, potentially sparse Test template path. A shorter official path is not itself an
exclusion reason; failure to reproduce any row in that path excludes the whole location. At
`2006-09` this retains 15,593 locations and 278,855 template rows. Every retained row preserves
its Test horizon exactly and the maximum remains 7. Other strong placements include
`2005-09` with 15,582 locations and 278,619 rows and `2003-09` with 15,571 locations and
278,468 rows. Fold selection remains deferred to Phase 1E.

### Deterministic synthetic masking

A seeded, versioned constrained generator could match totals, per-month masking, calendar
streaks, horizons, and observed-anchor requirements. It would not inherently preserve the
exact spatial association, rare observed exceptions, or relationship between masking and row
omissions. It remains a named sensitivity option.

### Simple month-block mask

A deterministic mask based only on the dominant observed and masked month blocks is cheap but
loses 417 observed exceptions, location omissions, and exact location-specific paths. It is
diagnostic only.

## Provisional recommendation

> Use exact Test-mask transplantation by relative calendar offset and location, restricted to
> locations that reproduce 100% of their own actual Test template path. “Complete-location”
> means complete relative to that path, not necessarily all 18 global Test months. Preserve
> official omissions as absent rows and never label them as masked. This policy preserves each
> retained row's empirical horizon within 1-7. Reject partial row-wise transplantation,
> retain deterministic synthetic masking as a named sensitivity option, and use the simple
> month-block approach only diagnostically. Keep recursion disabled in the principal policy.
> Treat `2006-09` as the strongest examined placement, not a frozen fold; fold selection
> remains a Phase 1E decision.

## Residual risks for Phase 1E

- Complete-location filtering excludes a small, non-random subset and may introduce mild
  spatial-selection bias. Report excluded rows and spatial diagnostics per fold.
- Select fold origins using predefined structural criteria, not future model scores.
- Keep transplantation sequential or optimize it to avoid repeatedly approaching the 2 GB
  analysis cap.
- Recursive predictions remain disabled in the principal observed-only policy. Any later
  permitted recursive policy must remain separately named and scored.

## Runtime and memory

The mask/streak/horizon scan took 2.32 seconds and peaked at 232,513,536 bytes process RSS.
The all-origin transplantation analysis took 52.83 seconds and peaked at 2,078,949,376 bytes
(1.94 GiB). Both used two DuckDB threads and a 2 GB DuckDB memory limit. Full historical
operations must remain sequential and memory-aware.
