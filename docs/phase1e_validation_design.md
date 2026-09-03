# Phase 1E rolling-origin validation design

**Evidence status:** Phase 1E analysis approved
**Design status:** `validation-v1` is frozen. Phase 1F/1G reproduced every recorded count and
invariant twice before freezing `configs/validation_protocol.yaml`.

This design reproduces the supplied Test information pattern with two independent historical
rolling-origin folds. Selection used structural evidence only, before any model results.

## Simulation and information cutoff

Each fold has one fixed training cutoff and one complete 40-calendar-month Test-shaped
simulation. The model is fitted once at the fold origin and is not refitted during that window.
All 18 distinct relative Test input months and corresponding target months must exist globally
at the historical origin. Each retained location is evaluated on every row in its own official
Test template path, which may contain fewer than 18 rows.

A Train row is eligible for fitting only when

```text
target_month = input_month + 1 calendar month
target_month <= fold_origin
```

F01 has 359,007 eligible fitting rows and F02 has 1,155,158. Zero eligible fitting targets are
after their fold origin. This is the competition-aligned availability convention: TWS at the
validation input month may be available when explicitly supplied or historically simulated as
observed. It does not establish real-world publication latency.

At a transplanted observed-reset row, the historical input TWS is exposed as genuinely
observed. At a transplanted masked row it remains unavailable. Later observations cannot
backfill earlier masks, model-generated TWS cannot become observed, recursion is disabled, and
validation targets never update the fitted model.

### Principal policy identifiers

| Role | Identifier |
|---|---|
| Validation design | `validation-v1` |
| Historical mask | `mask-exact-complete-v1` |
| TWS provenance | `tws-observed-only-v1` |
| Recursion | `recursion-disabled-v1` |
| Principal metric | `rmse-row-pooled-v1` |

Scores from different mask, provenance, or recursion policy IDs must never be pooled.

## Candidate-origin audit and deterministic selection

An origin is structurally eligible only if:

1. all 18 relative Test input-month offsets exist globally;
2. all 18 corresponding target months exist globally;
3. all 12 calendar months of the year occur in pre-origin Train history;
4. at least one location passes strict complete-location transplantation relative to its own
   official Test path;
5. every retained location reproduces every actual row in that path at the exact historical
   calendar offset, with a non-null supplied Train target for every reproduced row;
6. every retained location has at least 12 observations strictly before the origin, spanning
   at least 12 calendar months; and
7. the exact location-specific mask path preserves every intended effective horizon.

The audit generated 121 monthly origins from `2002-05` through `2012-05`. Fifty-five had all
required input and target months. Three retained no locations after the history gate and ten
more lacked all 12 calendar months of the year in pre-origin history, leaving **42 eligible
origins**. These yield **861 unordered pairs**, of which **67** have both zero shared validation
target months and zero shared `(location, target_month)` keys.

The pair-selection rule is frozen before any model results:

> After mandatory origin and cohort checks, require zero shared validation target months and
> zero shared `(location, target_month)` keys. Rank admissible pairs lexicographically by
> latest second origin, highest minimum per-fold retained-row percentage, highest pooled
> retained rows, greatest calendar-month separation, ascending first origin, and ascending
> second origin.

This recency-first rule prioritizes the most recent independently simulatable evaluation period
before maximizing retention. It selects `2004-09 + 2008-12` at rank 1 without subjective
candidate intervention. A coverage-first rule would select `2004-08 + 2007-08`; it is rejected
because it reverses the principal rolling-origin priority. The criterion order must not change
after scores are observed.

Compact audit results:

| Population or leading pair | Result |
|---|---:|
| Structurally eligible origins | 42 |
| Structurally eligible pairs | 861 |
| Target-month/key-disjoint pairs | 67 |
| Rank 1: `2004-09 + 2008-12` | 551,965 retained rows; 97.488975% minimum fold coverage |
| Rank 2: `2004-11 + 2008-12` | 549,244 retained rows; 97.488975% minimum fold coverage |
| Rank 3: `2005-05 + 2008-12` | 549,216 retained rows; 97.488975% minimum fold coverage |

## Why three target-disjoint folds are impossible

The relative target-offset set is

```text
S = {1, 5, 6, 7, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21, 22, 35, 39, 40}.
```

Two origins share a target month exactly when their separation is a positive difference between
two elements of `S`. Within the 52-month eligible-origin range, zero overlap is possible only at
separations `{31, 36, 37, 40, ..., 52}`. Thus adjacent origins in a target-disjoint three-fold
set must each be at least 31 months apart, requiring at least `31 + 31 = 62` months. Eligible
origins span only `2004-08` through `2008-12`, or 52 months, so no target-disjoint three-fold
design can exist.

## Selected folds

| Property | F01 | F02 |
|---|---:|---:|
| Origin | `2004-09-01` | `2008-12-01` |
| Training input range | `2002-05`--`2004-08` | `2002-05`--`2008-11` |
| Maximum permitted training target | `2004-09` | `2008-12` |
| Eligible fitting rows | 359,007 | 1,155,158 |
| Validation input range | `2004-09`--`2007-12` | `2008-12`--`2012-03` |
| Validation target range | `2004-10`--`2008-01` | `2009-01`--`2012-04` |
| Retained locations | 15,526 | 15,233 |
| Excluded locations | 189 | 482 |
| Retained rows | 278,059 | 273,906 |
| Excluded rows | 2,902 | 7,055 |
| Retained percentage | 98.967116% | 97.488975% |
| Minimum eligible history: observations/span | 12 / 17 months | 61 / 74 months |
| Deterministic seed | `null` (not applicable) | `null` (not applicable) |

Test contains 15,715 locations: 15,226 have all 18 rows, while 489 have sparse official paths,
creating 1,909 omitted location-month slots. The selected folds contain **671 excluded
fold-location instances**: 189 in F01 and 482 in F02. Their union contains **617 unique excluded
locations**. These quantities are not interchangeable because a location may be excluded in
both folds.

Exact validation input months:

- **F01:** `2004-09`, `2005-01`, `2005-02`, `2005-03`, `2005-06`, `2005-07`,
  `2005-08`, `2005-09`, `2005-12`, `2006-01`, `2006-02`, `2006-03`, `2006-04`,
  `2006-05`, `2006-06`, `2007-07`, `2007-11`, `2007-12`.
- **F02:** `2008-12`, `2009-04`, `2009-05`, `2009-06`, `2009-09`, `2009-10`,
  `2009-11`, `2009-12`, `2010-03`, `2010-04`, `2010-05`, `2010-06`, `2010-07`,
  `2010-08`, `2010-09`, `2011-10`, `2012-02`, `2012-03`.

### Effective horizons

| Horizon | F01 rows | F02 rows | Pooled rows |
|---:|---:|---:|---:|
| 1 | 92,995 | 91,421 | 184,416 |
| 2 | 61,918 | 60,906 | 122,824 |
| 3 | 46,318 | 45,638 | 91,956 |
| 4 | 30,782 | 30,425 | 61,207 |
| 5 | 15,412 | 15,187 | 30,599 |
| 6 | 15,334 | 15,166 | 30,500 |
| 7 | 15,300 | 15,163 | 30,463 |
| **Total** | **278,059** | **273,906** | **551,965** |

Both folds have zero horizon mismatches. Cross-fold checks found zero shared input months,
target months, `(location, input_month)` keys, and `(location, target_month)` keys. Earlier-fold
history may legitimately occur in a later fold's fitting period because each origin is simulated
independently; duplicate principal OOF targets remain prohibited.

## Cohort, missingness, and exclusion rules

Strict complete-location transplantation maps the actual sparse Test rows at relative calendar
offsets. “Complete-location” means that a retained location reproduces 100% of its own expected
path, including each existing row's mask state; it does not mean that the location must have all
18 global Test months. Official location-month omissions remain absent and are never created or
labelled as masked. The history gate uses only genuinely observed rows with
`time < fold_origin`; validation inputs, validation targets, later observations, and generated
values cannot affect it.

- Missing any historical input row or supplied target required by the location's own template
  path excludes the whole location from that fold. A shorter official Test path is not itself an
  exclusion reason.
- Locations failing the minimum observation count or calendar span are excluded rather than
  retained through future-aware imputation.
- Missing calendar months remain absent; they do not become masked rows.
- An exact missing lag stays missing and never becomes the previous available observation.
- Later-value backfill is prohibited.
- Partial transplantation is prohibited when it changes effective horizons.
- Exclusions are reported by fold, reason, and the fixed latitude bands below.

F01 retains 15,526 locations and all 278,059 rows in their expected paths; its 189 excluded
locations account for 2,902 template rows. F02 retains 15,233 locations and all 273,906 rows in
their expected paths; its 482 excluded locations account for 7,055 template rows. Both folds
have zero incomplete-transplant rows among retained locations. The origins, lexicographic rank,
horizon counts, overlap checks, and 551,965-row pooled total are unchanged by this clarification.

Exclusion is spatially non-uniform and may introduce mild representativeness bias, especially in
`[0,30)`. This is bias rather than leakage and does not justify weakening horizon fidelity.

| Fixed latitude band | F01 retained / excluded locations | F02 retained / excluded locations |
|---|---:|---:|
| `[-90,-60)` | 0 / 0 | 0 / 0 |
| `[-60,-30)` | 567 / 3 | 564 / 6 |
| `[-30,0)` | 2,451 / 61 | 2,455 / 57 |
| `[0,30)` | 3,053 / 110 | 2,828 / 335 |
| `[30,60)` | 5,566 / 7 | 5,517 / 56 |
| `[60,90]` | 3,889 / 8 | 3,869 / 28 |

## Metrics and aggregation

For row `i`, define error `e_i = prediction_i - target_i` and squared error `s_i = e_i^2`.
For a non-empty set `A`:

```text
RMSE(A) = sqrt(sum(s_i for i in A) / count(A)).
```

The principal value is pooled OOF RMSE over all 551,965 disjoint target keys. It is computed
from pooled SSE and total rows, not by averaging fold RMSE values. The unweighted mean of the
two fold RMSE values is diagnostic only because it gives unequal-sized folds equal influence.

Required diagnostics report RMSE, SSE, and row count by:

- fold;
- effective horizon 1--7;
- observed versus masked current TWS input;
- each supplied SPEI scale using bins `(-inf,-2)`, `[-2,-1.5)`, `[-1.5,-1)`, `[-1,1)`,
  `[1,1.5)`, `[1.5,2)`, and `[2,inf)`; and
- fixed latitude bands `[-90,-60)`, `[-60,-30)`, `[-30,0)`, `[0,30)`, `[30,60)`, and
  `[60,90]`.

Missing-history and exclusion diagnostics report fold-location and unique-location counts by
reason and latitude band. Longitude bands and coordinate-cell metrics are not mandatory; they
may be introduced as optional Phase 2 diagnostics only if defined before model comparison.

An empty slice reports `row_count = 0`, `SSE = 0`, and `RMSE = null`; it never reports RMSE
zero. Any NaN or infinite prediction fails the evaluation rather than being dropped. Unequal
fold sizes are handled by summing SSE and row counts. Aggregate and subgroup RMSE must always be
recomputed from their component SSE and counts.

Robustness and sensitivity results must carry complete policy IDs. Deterministic synthetic
masking is `mask-synthetic-deterministic-v1`; simple month-block masking is
`mask-month-block-diagnostic-v1` and diagnostic only. `recursion-reserved-v0` remains inactive
pending clarification. None may be pooled with the principal policy.

## Determinism, configuration, and manifests

Canonical row order is `fold_id`, `input_month`, lossless `2*lat`, lossless `2*lon`, then the
source row ID. Exact transplantation is non-stochastic and records seed `null`. A future
synthetic sensitivity uses global seed `20260903` with a stable fold-specific derivation.
Implementations cannot depend on filesystem order, unordered SQL output, hash-map order, or
thread completion order.

Proposed configuration fields are:

- validation version and fold IDs;
- origins, relative input offsets, and exact target-offset rule;
- training availability and history-gate rules;
- complete-location and missing-row policies;
- mask, TWS provenance, recursion, and metric policy IDs;
- fixed latitude and SPEI diagnostic bins;
- ordering and seed policy; and
- expected counts, horizons, uniqueness checks, and schema version.

Configuration validation must reject duplicate folds, noncanonical offsets, target offsets other
than input plus one month, post-origin fitting targets, unknown policy IDs, active recursion in
the principal policy, non-unique validation keys, cross-fold target overlap, unexpected horizon
counts, nonfinite predictions, and unknown configuration fields.

A compact fold manifest should record version, origin and boundaries, exact months, counts,
exclusions, horizons, policy IDs, seed, check results, generation time, implementation commit,
and SHA-256 hashes of the source-data manifest, canonical configuration, Test mask template, and
implementation. Only compact configurations, summaries, checks, counts, and hashes are tracked.
Row-level assignments, predictions, lineage tables, and feature matrices remain ignored.

Phase 1F.2 must construct folds by mapping actual Test template rows, never by generating the
`15,715 locations × 18 months` Cartesian set. Global 18-input/18-target coverage and
location-specific path completeness are separate assertions.

`configs/validation_protocol.yaml` remains unchanged until Phase 1F reproduces the recorded
evidence and Phase 1G performs the final freeze.

## Runtime and rejected alternatives

The systematic candidate scan used DuckDB with two threads, a 2 GB memory limit, Parquet views,
and insertion-order preservation disabled. It ran in 12.61 seconds with peak RSS 1,563,209,728
bytes (about 1.46 GiB). The final two-fold audit ran in 6.09 seconds with peak RSS 451,633,152
bytes (about 431 MiB). Origin processing should remain sequential or use compact cached
summaries to avoid the memory ceiling.

Rejected alternatives:

- **Three principal folds:** impossible with disjoint target months within the eligible span.
- **`2006-09` selected for raw coverage:** rejected as a selection rule; maximum coverage alone
  does not satisfy the pair-level recency and disjointness objective.
- **Coverage-first pair:** deterministic but rejected because it selects an older latest fold
  (`2004-08 + 2007-08`) instead of prioritizing recent rolling-origin evidence.
- **Partial row-wise transplantation:** rejected after 87 horizon mismatches and an artificial
  maximum horizon of 13 at the best raw-coverage origin.
- **Synthetic masking:** retained only as a separately scored sensitivity.
- **Month-block masking:** diagnostic only.
- **Recursive simulation:** inactive pending organizer clarification and never mixed with the
  observed-only score.
