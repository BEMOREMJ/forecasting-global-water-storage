# Prediction-time availability

**Status:** Phase 1B approved analysis
**Prediction event:** use information available for input month `t` to predict TWS at exact
calendar month `t+1`.

File presence does not by itself prove real-world availability. Supplied current-row SPEI and
soil-moisture values may be used for competition validation when historical folds reproduce
the supplied conditions. Their operational publication latency is unresolved, so no
operational-deployment claim may rely on them without publication evidence.

## Supplied-field availability matrix

| Field | Meaning | Timestamp | Train | Test | Observed or masked | Likely operational availability | Direct use | Lagged or rolling derivation | Leakage mechanism | Required validation control | Clarification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `sample_id` | Train row key encoding date and coordinates | `t` | Yes | No | Observed, unique | Known with row | Conditional: key/parsing only | Parse deterministic components | Opaque ID memorization | Exclude raw string from default features | None for availability |
| `ID` | Test/submission key encoding date and coordinates | `t` | No | Yes | Observed, unique | Known with row | Conditional: alignment/parsing only | Parse deterministic components | Opaque ID memorization | Preserve exact submission alignment | None |
| `time` | Input calendar month | `t` | Yes | Yes | Observed | Known | Allowed | Exact calendar features and offsets | Row-order operations compress gaps | Use calendar arithmetic | None |
| `lat` | Static latitude | Static | Yes | Yes | Observed | Known | Conditional: available, selection deferred | Deterministic or fold-fitted transforms | Learned spatial encoding can leak outcomes | Fit learned transforms inside fold | None for availability |
| `lon` | Static longitude | Static | Yes | Yes | Observed | Known | Conditional, as for `lat` | Same as `lat` | Same as `lat` | Same as `lat` | None for availability |
| `TWS_t` | TWS associated with input month | `t` | Yes | Yes | Train observed; Test has 94,048 observed and 186,913 masked | Available only when genuinely observed and permitted | Conditional | Historical calendar lags/rolls from genuinely observed TWS | Future TWS, backfill, or predictions relabelled as observations | Track timestamp and provenance; reproduce mask conditions | TWS latency and recursive use |
| `SPEI_01_t` | One-month SPEI | Nominally `t` | Yes | Yes | Supplied | Publication timing unresolved | Allowed for matched competition validation; operational claim unresolved | Exact calendar lags/rolls ending by `t` | Late publication or revised data | Match supplied conditions; verify latency for deployment | Publication timing |
| `SPEI_03_t` | Three-month trailing SPEI | Nominally `t` | Yes | Yes | Supplied | Publication timing unresolved | Same as `SPEI_01_t` | Same | Same | Same | Publication timing |
| `SPEI_06_t` | Six-month trailing SPEI | Nominally `t` | Yes | Yes | Supplied | Publication timing unresolved | Same as `SPEI_01_t` | Same | Same | Same | Publication timing |
| `SPEI_12_t` | Twelve-month trailing SPEI | Nominally `t` | Yes | Yes | Supplied | Publication timing unresolved | Same as `SPEI_01_t` | Same | Same | Same | Publication timing |
| `SOIL_MOISTURE_t` | Current-month soil moisture | Nominally `t` | Yes | Yes | Supplied | Publication timing unresolved | Allowed for matched competition validation; operational claim unresolved | Exact calendar lags/rolls ending by `t` | Late publication or revised data | Match supplied conditions; verify latency for deployment | Publication timing |
| `month_sin` | Deterministic seasonal sine | `t` | Yes | Yes | Observed | Known from calendar | Allowed | Deterministic seasonal transforms | Recalculation convention only | Verify against `time` | None |
| `month_cos` | Deterministic seasonal cosine | `t` | Yes | Yes | Observed | Known from calendar | Allowed | Deterministic seasonal transforms | Recalculation convention only | Verify against `time` | None |
| `target` | TWS outcome | `t+1` | Yes | No | Train outcome | Revealed after prediction | Prohibited as input for its row | Only older, already revealed outcomes may support controlled historical statistics | Direct, aggregate, or fold-boundary target leakage | Remove from inputs; enforce event cutoff and fold isolation | None |
| `TWS_t_masked` | TWS availability indicator | `t` | No | Yes | Observed; exactly matches TWS nullness | Supplied at event | Allowed as availability indicator | Historical mask summaries only under predetermined policy | Mask construction could use future information | Recreate validation masks without outcomes | Mask intent remains unresolved |
| Submission `Target` | Prediction output placeholder | `t+1` | No | Output only | Supplied zeros are placeholders | True value unavailable at event | Prohibited as input | None | Placeholder or leaderboard leakage | Populate only with predictions | None |

`TWS_t_masked` reveals whether TWS is available; it does not reveal or estimate the hidden TWS
value. A masked TWS remains unavailable.

## Information states

| State | Definition | Required treatment |
|---|---|---|
| Input month `t` | Calendar month represented by the row | Prediction-event anchor |
| Target month `t+1` | Exact next calendar month | Unavailable outcome at prediction time |
| Last genuinely observed TWS month | Latest permitted observed TWS month at or before the event | Anchor for history and later horizon analysis |
| Masked TWS | Withheld Test TWS represented by null plus mask flag | Remains unavailable; never backfill from later TWS |
| Model-generated TWS | A model prediction, not an observation | Retain predicted provenance; disabled in principal policy |
| Future observed TWS | Genuine TWS revealed after the event | Prohibited for the event |
| Current covariates | Supplied SPEI and soil moisture nominally at `t` | Allowed under matched competition conditions; operational timing unresolved |
| Lagged/rolling statistic | Feature using declared calendar offsets or intervals | Must satisfy cutoff, provenance, missing-month, and fold controls |

## Derived-feature availability rules

| Family | Status at prediction event | Construction and validation rule |
|---|---|---|
| Historical TWS lags | Conditional | Use only genuinely observed TWS at exact `t-k` calendar months. Missing means unavailable. |
| TWS differences and trends | Conditional | Every endpoint must be observed and safe. Declare elapsed calendar span; fit trends inside the fold. |
| Rolling TWS statistics | Conditional | Use a declared trailing calendar interval ending by `t`; declare minimum count and missing-month behavior; never backfill. |
| SPEI and soil-moisture lags/rolls | Competition-allowed under matched conditions; operationally unresolved | Use exact calendar windows and fold cutoffs. Deployment claims require publication-latency evidence. |
| Location climatologies | Conditional | Fit from training-fold information available before the simulated event; define sparse-history fallback. |
| Spatial-neighbour features | Conditional | Fix deterministic topology safely; include only neighbour values available at the event; fit learned weights inside fold. |
| Coordinate transforms | Allowed if deterministic; conditional if learned | Fixed calendar/coordinate formulas need no fit. Clusters, encoders, smoothers, or embeddings fit inside fold. |
| Target-derived statistics | Conditional with high leakage risk | Same-row, future, and validation targets are prohibited. Use only already revealed outcomes with event cutoff and fold-local or out-of-fold construction. |
| Recursively generated TWS | Unresolved and disabled in principal policy | If later supported, implement as a separately named sequential policy; preserve predicted provenance and never mix its scores with observed-only results. |

These rules describe availability controls, not final feature selections.

## Fold-specific transformation rule

Every learned transformation—including imputation, scaling, normalization, climatologies,
encoders, neighbour weights, trend fits, and target statistics—must be fitted inside each
training fold. Validation and future rows may only use the resulting fitted state. Purely
deterministic calendar and coordinate transformations contain no learned state and need no
fold-specific fitting.

## Discontinuous-calendar policy

A one-month lag means exact calendar month `t-1`, not the previous row, previous supplied
month, or most recent nonmissing observation. An absent exact-calendar lag remains unavailable
and must not silently become the previous available observation.

Every temporal feature must declare its calendar offsets or interval, inclusion of `t`, minimum
observation count, missing-month behavior, accepted provenance classes, and maximum source
timestamp. The leakage-safe default for a missing required lag is a missing feature plus an
availability or count indicator.

## Prediction-event timeline

1. **History through `t-1`:** only genuinely observed, permitted values may enter history.
   Preserve each value's calendar month, availability, and provenance; calendar gaps stay gaps.
2. **Input month `t`:** the row supplies time, coordinates, ID, seasonal encodings, current
   SPEI, soil moisture, the Test mask indicator, and either observed or masked `TWS_t`.
3. **Immediately before prediction:** masked TWS, target `t+1`, and future observed TWS are
   unavailable. Learned features must already have been fitted on the training fold. Current
   covariates are permitted for matched competition validation but not yet proven operational.
4. **Prediction event:** produce one estimate for exact month `t+1` under the same information
   policy used in historical validation. The principal policy cannot consume recursive TWS.
5. **After prediction:** true `t+1` TWS may be used only after genuine release for scoring or a
   later event. It cannot retroactively fill an earlier masked input or alter the prediction.

## Unresolved risks and controls

- **Current-covariate latency:** supplied competition use is confirmed; operational timing is
  not. Control: make no deployment claim without observation, processing, publication, and
  revision evidence.
- **Recursive TWS:** permission to feed predictions into later Test events is unresolved.
  Control: disable it in the principal observed-only policy; isolate any later-approved
  recursive policy and its scores.
- **Mask intent:** the file proves exact mask/null consistency, not organizer intent. Control:
  treat exact-mask reproduction as a Phase 1C empirical comparison before requesting further
  clarification.
- **Future TWS:** the exact target identity does not make future TWS available. Control: enforce
  event timestamps, provenance, fold cutoffs, and a prohibition on later-observation backfill.
- **Learned summaries:** full-data fitting leaks future or validation information. Control: fit
  all data-dependent state inside each fold.
