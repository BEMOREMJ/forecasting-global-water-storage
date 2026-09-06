# Phase 3B — Recent-period stress diagnostic

## 1. Pre-registration amendment

The repository's remote is expected starting state. After the original Phase 3 prompt was
prepared but before Phase 3A, the owner intentionally configured `origin`, made `main` track
`origin/main`, and backed up the existing history. Phase 3A did not create, modify, or use the
remote. Phase 3 may not push, upload, or change remote configuration without later explicit
authorization.

P3-D1 was initially planned as the latest exact transplantation of the official sparse Test
template. Calendar enumeration established that `2008-12-01` is the latest origin compatible
with all 18 template months because later Train history contains internal calendar gaps. That
origin is already validation-v1 F02, so it would not be a new recent-period diagnostic.

Before the successful execution, P3-D1 was amended to the latest uninterrupted Train-only
input/next-target block: inputs `2014-10-01` through `2015-07-01`, with targets `2014-11-01`
through `2015-08-01`. The fixed stored Phase 2 F02 LightGBM model and its 992,477-row sampled
training artifact were reused. The model was trained only through `2008-12-01`, leaving a
70-month gap to the diagnostic start and preventing target leakage.

## 2. Design and population

- Diagnostic rows: 156,267 complete rows across 15,710 locations.
- Horizon: 156,267 horizon-1 rows; zero rows for horizons 2–7.
- Mask state: 156,267 observed rows; zero masked/unavailable rows.
- Models: stored fixed Phase 2 F02 LightGBM and exact persistence.
- Configuration identity: `25a4afa2e7ac22754d6d07222e1e48abfdbc4a03cd857174d2e960ebe148e185`.
- Role: secondary robustness diagnostic only; it cannot replace validation-v1.

The pre-run estimate after the saved-artifact amendment was 2–6 minutes, at most 1.8 GB peak
RSS and about 80 MB disk. The successful run used 15.20 seconds, 1,000.16 MB peak RSS and
17.65 MB for the two prediction artifacts plus compact JSON evidence.

## 3. Structural differences

Validation-v1 contains 551,965 exact Test-template-transplanted rows over two folds, horizons
1–7, and observed plus masked inputs. Official Test contains 280,961 sparse rows: 94,048
observed and 186,913 masked. P3-D1 is a dense recent Train panel restricted to observed
horizon-1 rows. It measures recent one-step generalization, not sparse-mask or long-horizon
generalization. Complete coverage means 156,267 of its own pre-registered population, not
coverage of validation-v1 or Test.

## 4. Results

| Strategy | Rows | RMSE |
|---|---:|---:|
| Fixed Phase 2 F02 LightGBM | 156,267 | 0.756583 |
| Persistence | 156,267 | 0.839573 |

LightGBM improves on persistence by 0.082990 RMSE in this recent panel. Both are materially
worse than their validation-v1 horizon-1 references (LightGBM 0.535286; persistence 0.532489).
Because P3-D1 has only one horizon and mask state, its pooled, fold, observed, and horizon-1
metrics are identical. Complete latitude-band and SPEI-bin results are stored in
`reports/phase3d1_metrics.json`.

## 5. Drift findings

- Phase 2 sampled training years are 2002–2008. Every recent diagnostic row (2014–2015) and
  every Test row (2015–2018) is outside that range.
- Recent and Test latitude, longitude, month, horizon, and core SPEI/soil-moisture values are
  overwhelmingly within Phase 2 sampled-training ranges. Only about 0.0422% of recent
  last-observed TWS values are outside its training range; Test has none.
- Phase 2 LightGBM prediction mean shifts from 0.1933 on validation-v1 to -0.0278 on P3-D1
  and -0.1038 on Test. Standard deviation contracts from 0.6859 to 0.5499 on P3-D1 and is
  0.5893 on Test.
- No missing values occur in the evaluated fixed feature set. Optional P3-M2 history-feature
  missingness is not yet measurable because those features have not been constructed.
- Test mask counts from visible inputs are 94,048 observed and 186,913 masked; hidden Test
  targets were neither available nor accessed.

## 6. Public–local gap interpretation

Plausible, evidence-supported explanations are raw-year extrapolation, temporal target/process
drift, and a distribution shift visible in model predictions. P3-D1 also shows that the old
fixed model retains an advantage over persistence in recent one-step conditions, so simple
collapse of learned signal is not supported.

Unverified explanations include hidden Test target distribution, masked long-horizon error,
spatial sampling differences in hidden targets, leaderboard sampling variance, and whether a
residual target will close the public gap. The public score is not used as an optimization
objective, and no hidden-target property is inferred from it.

## 7. P3-M3 selection

Exactly one alternative is selected and pre-registered: **B, no-raw-year residual**. Raw year
is out of training range for 100% of recent and Test rows, whereas the measured hydrological
features remain almost entirely in range. P3-M3 will therefore use the selected Phase 3
residual representation with `input_year` removed, fixed LightGBM parameters, unchanged
validation-v1 rows, and the common promotion gate. It has not been run.

## 8. Execution record and safeguards

One P3-D1 execution completed successfully. Earlier launches were invalidated before a valid
metrics result: missing module path, an interrupted overlong materialization/reporting attempt,
an accidental calendar-check Cartesian product, an incorrect hard-coded F02 count, infeasible
exact-template origin, and an incompatible generic config canonicalizer. None retained valid
results. The successful run reused frozen saved artifacts and was not repeated.

No P3-M1, P3-M2, P3-M3, P3-M4, or P3-E1 run occurred. No submission was generated. No commit,
push, upload, or remote modification occurred. `validation-v1` and its manifest remained
unchanged.
