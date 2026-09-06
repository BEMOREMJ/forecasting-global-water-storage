# Phase 3C — P3-M1 persistence-residual LightGBM

## Decision

P3-M1 is a valid, informative experiment but **fails the production-promotion gate**. Its pooled
OOF RMSE is `0.589296`, improving on Phase 2 LightGBM by `0.003691`, below the required
`0.005` improvement. No production fit or submission is authorized.

## Pre-run verification and design

The Phase 3 fold-degradation rule was finalized before P3-M1 results: a fold materially degrades
when RMSE increases by more than `0.005` versus the corresponding stored Phase 2 LightGBM fold.
The limits are F01 `0.598578` and F02 `0.597387`. P3-M3B (no-raw-year residual) was already
fixed and cannot be changed in response to P3-M1/M2. P3-D1 has exactly one successful execution.
Validation-v1 and comparable identity
`2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a` were unchanged.

P3-M1 changed only the target to `target - last_observed_tws`. Absolute predictions were
reconstructed as `last_observed_tws + predicted_residual`. It retained raw year, the exact 13
Phase 2 features, fixed 200-round LightGBM parameters, deterministic seed 20260904, two threads,
the stored two-million Phase 2C examples, validation-v1, and recursion-disabled-v1.

Training rows were F01 1,007,523 and F02 992,477. Validation rows were F01 278,059 and F02
273,906, totaling 551,965. Pre-run resources were 4,415 MB available memory and 54,184 MB free
disk; estimates were 3–7 minutes, 2,600 MB peak RSS, and 100 MB incremental disk.

## Provenance and leakage controls

Every training anchor preserved canonical location, input/target/source timestamps, exact
same-location TWS provenance, and `source_month <= input_month < target_month`. Every validation
row persisted location, fold, mask state, input, target, last-observed timestamp/value, and
effective horizon. Checks rejected later, nonfinite, cross-location, target-derived, adjacent-row,
recursive, and global-statistic anchors. All checks passed; no fallback was used.

## Results

| Metric | P3-M1 | Phase 2 LightGBM | Persistence |
|---|---:|---:|---:|
| Pooled | 0.589296 | 0.592987 | 0.673722 |
| F01 | 0.591877 | 0.593578 | 0.649746 |
| F02 | 0.586665 | 0.592387 | 0.697219 |
| Observed | 0.529044 | 0.535286 | 0.532489 |
| Masked/unavailable | 0.617316 | 0.619919 | 0.734424 |

| Horizon | Rows | P3-M1 | Phase 2 LightGBM | Persistence |
|---:|---:|---:|---:|---:|
| 1 | 184,416 | 0.529044 | 0.535286 | 0.532489 |
| 2 | 122,824 | 0.601901 | 0.605097 | 0.641012 |
| 3 | 91,956 | 0.609129 | 0.612378 | 0.705974 |
| 4 | 61,207 | 0.605509 | 0.609151 | 0.733276 |
| 5 | 30,599 | 0.624467 | 0.623949 | 0.808767 |
| 6 | 30,500 | 0.643984 | 0.643340 | 0.865881 |
| 7 | 30,463 | 0.688169 | 0.691006 | 0.926618 |

| Latitude band | Rows | RMSE |
|---|---:|---:|
| [-90,-60) | 0 | — |
| [-60,-30) | 20,348 | 0.692881 |
| [-30,0) | 88,063 | 0.676613 |
| [0,30) | 104,583 | 0.584858 |
| [30,60) | 199,414 | 0.549039 |
| [60,90] | 139,557 | 0.572313 |

| SPEI feature/bin | RMSE |
|---|---:|
| SPEI-01: `<-2`, `[-2,-1.5)`, `[-1.5,-1)`, `[-1,1)`, `[1,1.5)`, `[1.5,2)`, `>=2` | 0.574810, 0.589647, 0.577637, 0.584427, 0.614185, 0.624470, 0.623065 |
| SPEI-03: same ordered bins | 0.630335, 0.578735, 0.568159, 0.583901, 0.617502, 0.649710, 0.645049 |
| SPEI-06: same ordered bins | 0.641234, 0.574146, 0.568917, 0.582987, 0.619884, 0.660283, 0.670744 |
| SPEI-12: same ordered bins | 0.642645, 0.599284, 0.588455, 0.583074, 0.604765, 0.636320, 0.607539 |

Full subgroup row counts and exact metrics are in `reports/phase3m1_metrics.json`.

P3-D1 remains separate context: the stored F02 raw model scored 0.756583 and persistence
0.839573 on its recent observed horizon-1 panel. P3-M1 was not scored there because that
comparison was not pre-registered.

## Runtime, memory, disk, and identities

The initial two-fold process started at 11:53:10Z; verified F01 and F02 checkpoints were written
at 11:53:53Z and 11:54:35Z. Thus both fold fits/predictions completed once in approximately 85
seconds. A reporting-label defect then interrupted final aggregation. The checkpoint-only resume
took 36.92 seconds and did not retrain or repredict either fold, for about 122 seconds measured
compute. Initial peak-RSS telemetry was lost at the reporting exception; the conservative
pre-registered ceiling was 2,600 MB. The resume performed no fit and its saved payload therefore
does not claim a meaningful fit peak. This telemetry limitation does not affect predictions.

Configuration SHA-256 is `379020de9b1644545241a2b7ab297bf5af78ce348cb772182dffb3a173c49479`.
Models total 1,434,838 bytes. Prediction/model artifacts total 81,738,742 bytes:

- F01 model: `870a2629c121b336406fc4b8ef6058b5e6a2a3602933bef37df1816ef57754a4`
- F02 model: `ec2ad1b49b7df55b309394e25fed2212b35a5d851e3d1b4ca9ef8c648284efe1`
- F01 predictions: `addae047fc7292536bd084a233e7857b569f77d529d6ed30b22dd061991f98c6`
- F02 predictions: `e60cbc52f96d5944b7b85892319c89c1eb3f52bb691fbb5cffef0749be5df5ed`
- Absolute OOF: `d9f54a908058c039020dc5b88e45712f2dc5f614957f35fc10a3847010f44ea1`
- Residual OOF: `e9708d8abcf0ab0786e1effe490911140def7ff61e4a355d2e14575c224813d9`
- Provenance: `e631781cccc84fdeebf4d3bc6fd87b2a023140aa0b11e47568a2a162018d7deb`

## Promotion gates

- Pooled improvement ≥0.005: **fail** (`0.003691`).
- F01 degradation ≤0.005: pass; P3-M1 improves by `0.001701`.
- F02 degradation ≤0.005: pass; P3-M1 improves by `0.005722`.
- Complete coverage and frozen identity: pass.
- Leakage/unsafe fallback: pass.
- Masked performance protected: pass; improves by `0.002603` overall.
- Recent-period credibility: neutral; no P3-M1 recent scoring was pre-registered.

Final decision: retain P3-M1 as valid evidence and a possible ensemble component, but do not
promote it independently.

## Execution record and scope confirmation

One initial process fitted and predicted each fold exactly once. Its final report step failed due
to a hard-coded P3-D1 fold label. Both hash-verified fold checkpoints were resumed without any
retraining or reprediction. No successful fold or experiment was unnecessarily rerun.

Focused residual/provenance tests passed before execution. Final checks cover the complete test
suite, lint, artifact hashes/row counts, validation files, Git state, and remote state.

No P3-M2, P3-M3, P3-M4, or P3-E1 run occurred. No production fit or submission was generated.
No commit, push, upload, or remote configuration change occurred. Validation-v1 remained
unchanged.
