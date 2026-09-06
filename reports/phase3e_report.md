# Phase 3E — P3-M3B no-raw-year residual

## 1. Final decision

**PASS.** P3-M3B is promotion-eligible under every frozen gate. This decision authorizes no production fit or submission.

## 2. Original selection and frozen interpretation

P3-M3B remained the sole P3-M3 selection, made after P3-D1 and before P3-M1/P3-M2 results. The seasonal-anomaly candidate remained rejected and did not run. The prior phrase `phase3_M2_features_excluding_input_year` was ambiguous; before fitting it was clarified to the interpretation required by the original drift hypothesis: the controlled P3-M1 representation with only raw `input_year` removed. No P3-M2 enhanced feature was added and later model results did not redefine the experiment.

The exact ordered model features were: `last_observed_tws`, `effective_horizon`, `latitude`, `longitude`, `input_calendar_month`, `month_sin`, `month_cos`, `SPEI_01_t`, `SPEI_03_t`, `SPEI_06_t`, `SPEI_12_t`, `SOIL_MOISTURE_t`. The `input_month` timestamp remains in provenance/prediction rows. Target = `target - last_observed_tws`; reconstruction = `last_observed_tws + predicted_residual`. Phase 2 LightGBM parameters, 200 rounds, seed 20260904, two threads, and the two-million-row cap were unchanged.

## 3. Identities, population, and provenance

- Configuration SHA-256: `150e872bfc730c58a92c7b515f9a85552b6a12ca2a8ad2249b8db7b34ab1d75f`.
- Phase 2C artifact SHA-256: `078ad361f03159ddd5b1f1f0a30e311d261ce82e1ab938d4e56cf56e2885e31b`; retained-target SHA-256: `4e1fc3745b754ae0020e111fa0d4e65afd3daf8b63034b7095340d3dc15fe95d`.
- Fold training identities: F01 `687d87cee219ca3ee5b177d14ef15e166b70cd2e7561c384b323773780258ba4`; F02 `0cb4eb1ba238ada4fa0d35594f63bafeb95daf24091a1fa8ca0a3e0b8542e690`.
- Validation identity: `dfafe4ae008ac4180f3f92a54ca825c779ab4768b0ba870e22dd1cd4e14088c9`; comparable identity: `2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a`.
- Training rows: F01 1,007,523; F02 992,477. Validation rows: F01 278,059; F02 273,906; pooled 551,965 (100% coverage).
- Anchor checks passed: same canonical location, genuinely observed anchor, explicit source timestamp, source <= input < target, no target-as-anchor, adjacency assumption, recursion, or global target statistic. No fitted feature statistic was introduced.

## 4. Resources

Pre-run availability was 4,609 MB memory and 53,659 MB disk. Estimated runtime was 3–7 minutes, peak RSS 2,600 MB, and disk 100 MB. Actual end-to-end runtime was 119.57 seconds; observed peak RSS was 1,167.39 MB. Fold fit/predict stages were 42.07 seconds (F01) and 40.69 seconds (F02). The six large retained model/prediction artifacts total 81,755,224 bytes (77.97 MiB).

Matrices were F01 1,007,523×12 training / 278,059×12 validation and F02 992,477×12 training / 273,906×12 validation.

## 5. Complete results

| Slice | Rows | RMSE | Δ vs P3-M1 |
|---|---:|---:|---:|
| Pooled | 551,965 | 0.583923 | -0.005374 |
| F01 | 278,059 | 0.583111 | -0.008766 |
| F02 | 273,906 | 0.584746 | -0.001919 |
| Horizon 1 / observed | 184,416 | 0.521314 | -0.007730 |
| Horizon 2 / masked | 122,824 | 0.591404 | -0.010497 |
| Horizon 3 / masked | 91,956 | 0.609467 | +0.000338 |
| Horizon 4 / masked | 61,207 | 0.600118 | -0.005391 |
| Horizon 5 / masked | 30,599 | 0.627580 | +0.003114 |
| Horizon 6 / masked | 30,500 | 0.639221 | -0.004763 |
| Horizon 7 / masked | 30,463 | 0.687764 | -0.000405 |
| All masked | 367,549 | 0.612931 | -0.004384 |

Latitude diagnostics: `[-60,-30)` 20,348 / 0.696525; `[-30,0)` 88,063 / 0.662599; `[0,30)` 104,583 / 0.580080; `[30,60)` 199,414 / 0.545183; `[60,90]` 139,557 / 0.569134. `[-90,-60)` had zero comparable rows.

SPEI diagnostics (bins ordered `(-inf,-2)`, `[-2,-1.5)`, `[-1.5,-1)`, `[-1,1)`, `[1,1.5)`, `[1.5,2)`, `[2,inf)`):

- SPEI-01 RMSE: 0.550730, 0.568136, 0.566161, 0.579879, 0.615156, 0.626318, 0.624136; rows: 4,810, 27,448, 65,905, 365,953, 53,454, 27,821, 6,574.
- SPEI-03 RMSE: 0.616067, 0.555661, 0.554399, 0.580847, 0.615033, 0.646744, 0.643373; rows: 5,829, 29,734, 66,331, 366,933, 53,181, 24,652, 5,305.
- SPEI-06 RMSE: 0.603437, 0.556069, 0.558262, 0.579942, 0.617135, 0.653962, 0.657600; rows: 6,216, 31,157, 65,559, 370,555, 50,078, 23,478, 4,922.
- SPEI-12 RMSE: 0.611976, 0.580906, 0.576350, 0.581296, 0.599987, 0.616200, 0.570348; rows: 5,566, 28,679, 63,480, 382,058, 47,988, 20,360, 3,834.

## 6. Comparisons and gates

| Model | Pooled RMSE | Role |
|---|---:|---|
| P3-M2 enhanced residual | 0.581353 | Context only; not a controlled comparison |
| P3-M3B no-year residual | 0.583923 | Current experiment |
| P3-M1 residual | 0.589296 | Primary controlled reference |
| Phase 2 raw LightGBM | 0.592987 | Frozen baseline |
| Persistence | 0.673722 | Deterministic baseline |

Removing raw year helped both folds and improved pooled RMSE by 0.005374 versus P3-M1. It improved observed rows and the aggregate masked population. Small regressions occurred at horizons 3 (+0.000338) and 5 (+0.003114) versus P3-M1, but every masked horizon remained within the frozen Phase 2 +0.005 protection limit: h2 0.610097, h3 0.617378, h4 0.614151, h5 0.628948, h6 0.648339, h7 0.696007. Thus error was not shifted into unprotected long masked horizons.

All gates passed: pooled <= 0.587987; F01 <= 0.598578; F02 <= 0.597387; complete coverage; leakage safety; and each masked horizon protected. The result is consistent with the no-year drift hypothesis on validation-v1, while P3-D1 remains separate recent-period evidence; P3-M3B was not scored on P3-D1.

## 7. Artifacts

- F01 model: 714,294 bytes, `df4d80794b77cb2d8b6190e398fa8494b538d546d35d1efec4bea6e50dbbd62f`; predictions: 17,912,353 bytes, `a8f280c0bdcb50585ec1a53454fb1aa51bfcd77d1f04d7ed664cabb50cdbdf74`.
- F02 model: 721,338 bytes, `24e829668badec12f030efe6b06c5ea7e857ed88d91e5209d4e0085574d2a2d6`; predictions: 17,683,262 bytes, `d0c1181971c4c54be9b900f6e8f97a96592643f54f7292cc85d0ba58f1d6f3db`.
- Absolute OOF: 33,580,682 bytes, `3208f569c748d925de736bff786451ee9472ca5052325cad2e01c7f4030e77dc`.
- Residual OOF: 11,143,295 bytes, `a8ef1828b7f4705f7231d9882b3d1506e1e16e3155046051c0af21c6c78d6d55`.
- Checkpoints: F01 `413847c2113bc59a6046de166e3c0b2a8e7ab5491bc72f83e3bc73b4c78b077f`; F02 `9907d02c56a6cc9d6263edfa5f5284fd6c032e29db131191ad91b6014ee1dcc1`.

## 8. Verification and execution record

Eight focused tests passed before fitting. They covered exact schema equality except year, year absence, calendar-month presence and ordering, residual/reconstruction equivalence, frozen identities/populations, and deterministic configuration identity; the reused provenance predicates cover location and timestamp safety. Final focused tests and lint passed after execution.

Two launcher failures occurred before the experiment module loaded: system Python lacked dependencies, then `uv` cache access was denied. Neither reached configuration loading, fitting, prediction, or artifact creation. The subsequent authorized execution successfully fit F01 once and F02 once; neither was retrained or resumed.

Files added/changed for Phase 3E: `configs/phase3_preregistration.yaml`, `configs/phase3m3b_no_year_residual.yaml`, `src/drought_forecasting/residual_benchmark.py`, `src/drought_forecasting/no_year_residual.py`, `tests/test_no_year_residual.py`, `reports/p3m3b_F01_checkpoint.json`, `reports/p3m3b_F02_checkpoint.json`, `reports/phase3m3b_metrics.json`, `reports/phase3m3b_provenance.json`, this report, and Git-ignored `artifacts/phase3m3b/*`.

Validation-v1 remained unchanged. P3-D1, P3-M1, P3-M2, Phase 2, the seasonal-anomaly alternative, P3-M4, and P3-E1 did not run. No production fit or submission was generated. HEAD remained `412fe9d2ba0184ca4ae0f13560ffaf1c0be7f327`; no commit, push, upload, branch operation, remote use, or remote configuration change occurred.
