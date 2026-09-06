# Phase 4 closeout

## 1. Decision

PASS — experimentation completed successfully, with no model promoted.

Retain P3-M3B as the production reference. None of the three pre-registered Phase 4 experiments
met the pooled OOF promotion gate of 0.578923. No production model, predictions, submission
candidate, ensemble, upload, commit, or push was created.

## 2. Starting state

Phase 4 began on clean `main` at `ff480679ef0de953d37e141eb5fa0b1f9e27b8fb`, with
`origin/main` at 0/0 and validation-v1 unchanged. P3-M3B was the reference: local OOF 0.583923
and public RMSE 0.766408529. The deterministic two-million-row sample and recursion-disabled
policy remained fixed.

## 3. Pre-registered experiments

- P4-M1 used a fold-local location/month-pair climatological TWS change, with latitude-band,
  global-month-pair, then zero fallbacks, as the residual anchor.
- P4-M2 retained the P3-M3B representation and added current supplied covariate means,
  fold-local climatology, and availability counts from four cardinal 0.5-degree neighbours.
- P4-M3 first assessed CatBoost. It was not installed; the fixed fallback used P3-M3B with
  training weight `0.5 ** (age_months / 24)`.

## 4. Results

| Experiment | Pooled | F01 | F02 | H6 | H7 | Recent | Runtime s | Peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P3-M3B | 0.583923 | 0.583111 | 0.584746 | 0.639221 | 0.687764 | 0.562832 | 119.6 | 1167.4 |
| P4-M1 | 0.811096 | 0.831369 | 0.789982 | 0.902636 | 0.974729 | 0.747939 | 99.0 | 1930.7 |
| P4-M2 | 0.778214 | 0.796597 | 0.759097 | 0.863489 | 0.934871 | 0.720886 | 121.9 | 2782.4 |
| P4-M3 | 0.584126 | 0.584396 | 0.583852 | 0.638641 | 0.687823 | 0.564216 | 95.1 | 1957.2 |

All experiments covered 551,965/551,965 validation rows. Recent diagnostics use the latest 12
input months within each fold (92,044 rows).

## 5. Feature-engineering findings

The seasonal-change anchor was harmful at every key level. The location/month-pair statistic was
available for all sampled training examples, so fallback scarcity does not explain the failure;
fold-to-validation transfer is the likely weakness. Cardinal-neighbour means and climatology also
degraded heavily and raised peak memory close to the ceiling. Recency weighting was the only
credible idea: it improved H6 slightly and retained recent-period credibility, but its pooled score
was 0.000204 worse than P3-M3B.

## 6. Promotion decisions

P4-M1 and P4-M2 failed pooled, fold, H6/H7, and recent-period gates. P4-M3 passed fold stability,
H6/H7 protection, coverage, recent-period, leakage, and memory gates, but failed the decisive pooled
gate. All three are rejected without leaderboard repair.

## 7. Production candidate

None. The submission policy was not triggered.

## 8. Runtime and memory

Successful two-fold runs took 95.1--121.9 seconds and peaked at 1,930.7--2,782.4 MB. Spatial SQL
materialization required execution-plan correction before model fitting; incomplete pre-fit attempts
produced no metrics and are not additional model runs.

## 9. Risks

Two historical folds remain an imperfect proxy for the public period. Seasonal statistics may be
overly granular or duplicatively weighted by horizon examples, while cardinal adjacency may not
match hydrological connectivity. These are limitations, not authorization for post-hoc variants.

## 10. Files changed

`configs/phase4.yaml`, `src/drought_forecasting/phase4_models.py`,
`tests/test_phase4_models.py`, `reports/phase4_results.json`, this closeout,
`experiments/registry.csv`, and `reports/final_report_outline.md`.

## 11. No unnecessary reruns

Focused tests ran once and passed 4/4. Each successful model experiment ran once. No prior phase
model or audit was rerun. P4-M2's interrupted SQL attempts ended before fitting and were replaced
only by execution-equivalent pre-aggregation.

## 12. Recommended finalization work

Carry P3-M3B unchanged into the authoritative final notebook and report. Use Phase 4 as negative
feature-engineering evidence, retain the public/local generalization warning, and do not spend more
competition runs on seasonal anchors, cardinal neighbours, recency decay variants, or ensembles.
