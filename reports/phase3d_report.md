# Phase 3D — P3-M2 enhanced persistence-residual LightGBM

## Decision

P3-M2 completed successfully and materially improves pooled RMSE, but **fails promotion** because
masked horizons 6 and 7 degrade by more than the fixed 0.005 protection tolerance. It remains
valid experimental evidence; no production fit or submission was created.

## Pre-registered feature table

P3-M2 retained all 13 P3-M1/Phase 2 features, including raw `input_year`, and added:

| Feature family | Frozen features | Source/state | Missing treatment |
|---|---|---|---|
| Forecast history | second-last TWS, observation gap, historical slope | Same-location timestamp history | Native NaN plus second-last/slope indicators |
| Seasonal history | latest earlier target-calendar-month TWS, timestamp age, seasonal difference | Same-location timestamp history | Native NaN plus history/difference indicators |
| Hydrology | SPEI-01−03, SPEI-03−06, SPEI-06−12 | Row-derived | Reject nonfinite input |
| Soil context | soil-moisture anomaly | Fold-fitted predictor-only mean | Fixed fallback plus reference indicator |
| Spatial | latitude/longitude sine and cosine | Row-derived degrees→radians | Reject nonfinite input |

All proposed features were accepted before execution. None was substituted after results. Original
latitude/longitude and raw year were retained. Optional history was never zero-imputed.

Soil means were fitted separately per fold from distinct training-example location/input-month
predictors. The frozen fallback was location-month → location → global month → global. F01 used
355,929 unique predictor events; F02 used 705,672. Compact statistic artifacts contain 187,408
and 186,865 location-month groups, respectively, plus 15,715 location groups, 12 month groups,
and one global group per fold.

## Identity and provenance

- Phase 2C F01 identity: `687d87cee219ca3ee5b177d14ef15e166b70cd2e7561c384b323773780258ba4`
- Phase 2C F02 identity: `0cb4eb1ba238ada4fa0d35594f63bafeb95daf24091a1fa8ca0a3e0b8542e690`
- Comparable identity: `2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a`
- P3-M2 configuration: `c269a0e5f4614426c45b429c688606fca43ec74d9d067e7f09c08494816f492f`

Training remained F01 1,007,523 and F02 992,477; validation remained F01 278,059 and F02
273,906. Same-location and timestamp ordering checks passed. TWS sources were last, strictly
earlier second-last, or most recent earlier target-calendar-month observations. No future row,
validation target, physical-row adjacency, global target statistic, or recursive value was used.

## Feature availability

| Population | Second-last/slope | Seasonal history/difference | Soil reference |
|---|---:|---:|---:|
| F01 training | 97.483% | 55.716% | 100% |
| F01 validation | 100% | 99.818% | 100% |
| F02 training | 99.295% | 87.485% | 100% |
| F02 validation | 100% | 100% | 100% |

F01 validation seasonal availability was 99.790% for observed and 99.831% for masked rows; F02
was 100% for both. Complete per-horizon and mask summaries are saved in
`reports/phase3m2_feature_availability.json`.

## Results

| Metric | P3-M2 | P3-M1 | Phase 2 LightGBM | Persistence |
|---|---:|---:|---:|---:|
| Pooled | 0.581353 | 0.589296 | 0.592987 | 0.673722 |
| F01 | 0.587596 | 0.591877 | 0.593578 | 0.649746 |
| F02 | 0.574947 | 0.586665 | 0.592387 | 0.697219 |
| Observed | 0.523610 | 0.529044 | 0.535286 | 0.532489 |
| Masked overall | 0.608264 | 0.617316 | 0.619919 | 0.734424 |

P3-M2 improves pooled RMSE by 0.011634 versus Phase 2 and 0.007943 versus P3-M1.

| Horizon | Rows | P3-M2 | P3-M1 | Phase 2 |
|---:|---:|---:|---:|---:|
| 1 | 184,416 | 0.523610 | 0.529044 | 0.535286 |
| 2 | 122,824 | 0.585813 | 0.601901 | 0.605097 |
| 3 | 91,956 | 0.594264 | 0.609129 | 0.612378 |
| 4 | 61,207 | 0.585338 | 0.605509 | 0.609151 |
| 5 | 30,599 | 0.616745 | 0.624467 | 0.623949 |
| 6 | 30,500 | 0.676002 | 0.643984 | 0.643340 |
| 7 | 30,463 | 0.697380 | 0.688169 | 0.691007 |

Latitude RMSEs in ordered bands `[-90,-60)`, `[-60,-30)`, `[-30,0)`, `[0,30)`, `[30,60)`,
`[60,90]` are: unavailable (zero rows), 0.644641, 0.655135, 0.575249, 0.544339, 0.577858.

SPEI-bin RMSEs (ordered `<-2`, `[-2,-1.5)`, `[-1.5,-1)`, `[-1,1)`, `[1,1.5)`,
`[1.5,2)`, `>=2`) are:

- SPEI-01: 0.596690, 0.594909, 0.570984, 0.575114, 0.603311, 0.617597, 0.619877.
- SPEI-03: 0.626259, 0.577182, 0.564815, 0.574739, 0.607382, 0.642689, 0.642123.
- SPEI-06: 0.624416, 0.565156, 0.565039, 0.574695, 0.610033, 0.653844, 0.666165.
- SPEI-12: 0.618754, 0.589086, 0.582485, 0.577339, 0.586971, 0.615728, 0.588316.

## Promotion gates

- Pooled RMSE ≤0.587987: pass.
- Fold limits: pass (F01 0.587596; F02 0.574947).
- Frozen 551,965-row coverage and identity: pass.
- Leakage/unsafe fallback: pass.
- Overall masked RMSE: improves by 0.011655.
- Masked horizons 2–5: improve by 0.007203–0.023812.
- Masked horizon 6: **fails**, degrading by 0.032663.
- Masked horizon 7: **fails**, degrading by 0.006373.
- Recent-period credibility: unresolved; P3-M2 recent scoring was not pre-registered.

The generated metrics file initially summarized masked protection at aggregate level. The
authoritative correction is `reports/phase3m2_promotion_amendment.json`; predictions and metrics
are unchanged. Final promotion decision: **not eligible**.

## Runtime and artifacts

Runtime was 186.03 seconds and measured peak RSS was 2,945.84 MB. F01 used 74.51 seconds and
2,133.51 MB; F02 used 79.95 seconds and 2,945.84 MB. Models total 1,445,852 bytes. Materialized
training features total 215,149,831 bytes; validation features total 55,097,633 bytes. Fold
predictions total 35,601,287 bytes; pooled absolute/residual OOF total 44,748,402 bytes. Soil
statistics total 4,208,451 bytes. Actual disk use stayed below the 650 MB estimate.

Artifact hashes, sizes, model identities, and fold checkpoints are in
`reports/phase3m2_metrics.json` and `reports/phase3m2_provenance.json`.

## Execution and scope

Two failed pre-fit attempts were recorded: a reserved SQL metadata identifier and a Phase 2C
anchor-timestamp alias mismatch. Neither produced a model or prediction. After correction, F01
and F02 each fitted exactly once and the experiment completed without a resume.

No P3-M3, P3-M4, or P3-E1 run occurred. No P3-D1 or Phase 2 process was rerun. No production fit,
submission, commit, push, upload, or remote change occurred. Validation-v1 remained unchanged.
