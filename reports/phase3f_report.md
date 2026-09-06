# Phase 3F — P3-M4 horizon-group specialists

## Final decision

**FAIL (valid non-promoted evidence).** P3-M4 achieved pooled RMSE 0.583524 but failed the frozen masked-horizon protection gate. Its cross-fitted predictions remain eligible for later P3-E1 consideration. No production fit or submission is authorized.

## Ledger and frozen design

P3-D1, P3-M1, P3-M2, P3-M3B, and now P3-M4 each completed once; the five-run expensive-validation budget is exhausted. P3-E1 remains artifact-only and may train no LightGBM model.

P3-M4 used P3-M3B's persistence-residual target, anchor reconstruction, exact ordered 12 features (P3-M1 core minus only `input_year`), Phase 2 parameters, 200 rounds, seed 20260904, two threads, unchanged Phase 2C examples and validation-v1, no recursion, enhanced features, external data, or fitted target statistic. Fixed routing was G1={1}, G23={2,3}, G47={4,5,6,7}. Learned G1 was selected before fitting because P3-M3B h1 0.521314 beat persistence 0.532489.

## Population and deterministic identities

| Fold-group | Train | Validation | Training subset SHA-256 |
|---|---:|---:|---|
| F01-G1 | 336,960 | 92,995 | `4b3a24cc6db84aa5f6f95fd2acef4e68c6d5f9f0fcdc4388647855ef7bf2205e` |
| F01-G23 | 392,184 | 108,236 | `3646ed827241d02320b75b6e2c23edb186633e02da5c55f5df79f1156ebda361` |
| F01-G47 | 278,379 | 76,828 | `5e5f72d1f6f4c3a8487c472f215028a24227946af85d062c52e9ceb54ad59b33` |
| F02-G1 | 331,257 | 91,421 | `f588f4fc17c6df2bc57ba329277518a645a7ba58302198db5d5ea195649d5b79` |
| F02-G23 | 386,054 | 106,544 | `b2fbf2e7536f154063eb11b95046844b18d24c499cedd42956b8a5c7ba305287` |
| F02-G47 | 275,166 | 75,941 | `c22ba37ea1a22e34602a0dd1bdb1d193228c52ee573327fa79f7d7f9259a45ec` |

All training examples and validation rows mapped to exactly one group; routed rows were globally key-sorted with no omission or duplication. Fold totals remained 278,059 and 273,906; pooled coverage was 551,965. Comparable identity remained `2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a`; Phase 2C artifact identity remained `078ad361f03159ddd5b1f1f0a30e311d261ce82e1ab938d4e56cf56e2885e31b`. Stored Phase 2C input range was 2002-05-01–2008-11-01 and target range 2002-06-01–2008-12-01. Residuals were finite and all source/location/timestamp, observed-anchor, no-recursion, and no-cross-specialist safeguards were retained.

## Results

| Slice | Rows | RMSE | Δ vs general P3-M3B |
|---|---:|---:|---:|
| Pooled | 551,965 | 0.583524 | -0.000398 |
| F01 | 278,059 | 0.585932 | +0.002822 |
| F02 | 273,906 | 0.581070 | -0.003676 |
| G1 / h1 / observed | 184,416 | 0.513982 | -0.007332 |
| G23 | 214,780 | 0.601177 | +0.001973 |
| G47 | 152,769 | 0.635006 | +0.003279 |
| h2 | 122,824 | 0.593732 | +0.002327 |
| h3 | 91,956 | 0.610981 | +0.001514 |
| h4 | 61,207 | 0.604566 | +0.004448 |
| h5 | 30,599 | 0.631019 | +0.003438 |
| h6 | 30,500 | 0.640220 | +0.001000 |
| h7 | 30,463 | 0.690984 | +0.003220 |
| All masked | 367,549 | 0.615464 | +0.002532 |

Latitude RMSE: `[-60,-30)` 0.701982; `[-30,0)` 0.658090; `[0,30)` 0.583857; `[30,60)` 0.543629; `[60,90]` 0.569071 (`[-90,-60)` has zero rows).

SPEI RMSE by bins `(-inf,-2),[-2,-1.5),[-1.5,-1),[-1,1),[1,1.5),[1.5,2),[2,inf)`: SPEI-01 0.547252/0.569575/0.568051/0.579194/0.615418/0.622950/0.619960; SPEI-03 0.617075/0.557896/0.555248/0.580578/0.612461/0.643725/0.640196; SPEI-06 0.598144/0.561366/0.559660/0.578946/0.615993/0.653124/0.660732; SPEI-12 0.609645/0.583194/0.576228/0.581244/0.598743/0.608945/0.562785. Counts are identical to the Phase 3E report.

Context pooled RMSE: P3-M2 0.581353; P3-M4 0.583524; P3-M3B 0.583923; P3-M1 0.589296; Phase 2 0.592987; persistence 0.673722. Specialization materially helped only G1.

## Gates, resources, artifacts, and execution record

Pooled, both folds, coverage, deterministic routing, training support, and leakage gates passed. Masked protection failed: h5 0.631019 exceeded its Phase 2+0.005 limit 0.628948 (the other masked horizons passed).

Pre-run resources were 4,964 MB RAM and 53,615 MB disk; estimate was 3–8 minutes, 1,800 MB RSS, and 120 MB disk. Maximum captured specialist RSS was 1,014.12 MB. Final resume/aggregation took 42.16 seconds; exact total wall telemetry was interrupted by checkpoint/reporting failures and was not recovered by rerunning models.

Configuration SHA-256: `6f8e02792b308fc26b1a0643b22dcae93297bce08db1c30c14504d9f9397dbae`. OOF artifacts: absolute 33,574,200 bytes / `5ff1e63c219376c3d6cd40382224b1b99386c169fb81d8d64f461fd14511cb26`; residual 6,662,382 bytes / `0977748db52239af17aaf63d77c8735145ab28d2575e3e1f5871db2e2c77269e`. Individual model, prediction, checkpoint hashes and sizes are recorded in `reports/phase3m4_metrics.json`.

Eight focused pre-fit tests passed. Six specialists fitted successfully exactly once. F01-G1 checkpoint identity reporting initially failed after its model/prediction save and was recovered without refitting. After all fits, two aggregation-only failures exposed noncompliant shared metadata and unsorted concatenation; all six checkpoint hashes were verified, metadata was repaired, and predictions globally sorted without retraining or reprediction.

Phase 3F added/changed the P3-M4 config, specialist implementation/tests, six checkpoints, metrics, ignored specialist/OOF artifacts, this report, and the Phase 3 ledger. Validation-v1 remained unchanged. P3-E1 did not run. No production fit, submission, commit, push, upload, or remote change occurred.
