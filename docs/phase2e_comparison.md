# Phase 2E frozen comparison

Comparison JSON SHA-256: `fefa08c7b72561c22d34d02dfb7faf9f42efb2ac7abc8e18bb35122aff0fc8dc`.

| Rank | Model | Pooled | F01 | F02 | Fold gap | H1 | H2 | H3 | H4 | H5 | H6 | H7 | Runtime s | Peak MiB | Coverage | Fallback rate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | lightgbm_basic | 0.592987 | 0.593578 | 0.592387 | 0.001191 | 0.535286 | 0.605097 | 0.612378 | 0.609151 | 0.623948 | 0.643339 | 0.691007 | 125.33 | 2122.25 | 100% | 0.000000% |
| 2 | persistence | 0.673722 | 0.649746 | 0.697219 | 0.047473 | 0.532489 | 0.641012 | 0.705974 | 0.733276 | 0.808767 | 0.865881 | 0.926619 | 120.61 | 2253.87 | 100% | 0.000000% |
| 3 | global_mean | 0.906959 | 0.964546 | 0.844492 | 0.120054 | 0.892962 | 0.909797 | 0.937345 | 0.904500 | 0.847956 | 0.893452 | 0.960435 | 135.25 | 2206.05 | 100% | 0.000000% |
| 4 | location_mean | 0.909744 | 0.852776 | 0.964139 | 0.111363 | 0.899390 | 0.924626 | 0.889601 | 0.870012 | 0.906925 | 0.975555 | 0.981508 | 126.68 | 2205.79 | 100% | 0.000000% |
| 5 | seasonal_naive | 0.964292 | 0.950403 | 0.978190 | 0.027787 | 0.937237 | 0.933378 | 0.976463 | 0.972827 | 1.009234 | 1.050475 | 1.053734 | 88.65 | 2229.05 | 100% | 0.140770% |
| 6 | location_calendar_month_climatology | 0.972241 | 0.961973 | 0.982556 | 0.020583 | 0.970804 | 0.994963 | 0.941462 | 0.953880 | 0.968234 | 0.996830 | 0.995064 | 144.88 | 2298.00 | 100% | 0.001812% |
| 7 | location_trend_seasonal | 1.309624 | 1.514221 | 1.062359 | 0.451863 | 1.374319 | 1.396853 | 1.120978 | 1.216120 | 1.233588 | 1.348837 | 1.288635 | 80.68 | 2275.71 | 100% | 0.001812% |

## Decision

`lightgbm_basic` is preferred. It improves pooled RMSE over persistence by 0.080735 (11.98%) and improves both folds. It has the smallest fold gap and full coverage. Persistence remains the strongest deterministic baseline, fallback/reference method, and mandatory future comparison.

Measured weaknesses: error rises from horizon 1 to horizon 7; masked inputs are weaker than observed inputs; the [-60,-30) and [-30,0) latitude bands are weakest. Detailed SPEI bins remain in the referenced run metrics. All production evaluators used roughly 2.2 GiB peak RSS, so memory remains a binding laptop constraint.

Possible Phase 3 hypotheses, not findings: horizon-specific calibration and carefully bounded feature improvements may address long-horizon and masked-row degradation. No extra tuning or rerun is justified in Phase 2 because its objective is a trustworthy floor.
