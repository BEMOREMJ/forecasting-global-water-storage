# Phase 3 closeout

## Decision

**PASS.** P3-M3B production fitting succeeded once and its primary 280,961-row candidate passed every local submission-contract check. The five-run budget, frozen validation, leakage controls, drift work, reporting notebook, and non-promotion decisions were respected. Nothing was uploaded.

## State and identities

Phase 3 began and ended on `main` at HEAD `412fe9d2ba0184ca4ae0f13560ffaf1c0be7f327`, tracking `origin/main` 0/0. Origin was an authorized pre-Phase-3 backup and was not used or modified. Validation-v1 remained 551,965 rows with identity `dfafe4ae...`; comparable identity remained `2b27c3e0...4607c0a`; production sample identity was `9526f039...f3e9` (2,000,000 Train-only rows).

The first public result motivated generalization diagnosis but never tuning. P3-D1 found Phase 2 LightGBM 0.756583 versus persistence 0.839573 on a recent observed-only horizon-1 population; it cannot replace validation-v1. Raw year was outside sampled Train range for 100% of recent and Test rows, while most measured predictors remained in range.

## Experiment ledger and decisions

| Strategy | Pooled RMSE | Decision |
|---|---:|---|
| Phase 2 LightGBM | .592987 | Reference |
| Persistence | .673722 | Diagnostic baseline |
| P3-M1 residual | .589296 | Non-promoted: improvement <.005 |
| P3-M2 enhanced residual | .581353 | Non-promoted: h6/h7 protection |
| P3-M3B no-year residual | .583923 | **Promoted**: all gates pass |
| P3-M4 specialists | .583524 | Non-promoted: h5 protection |
| P3-E1 cross-fitted ensemble | .571686 | Non-promoted: h6 protection |

P3-M3B uses the persistence-residual target and reconstruction, exact P3-M1 core schema minus raw year, fixed 200-round LightGBM, two threads, no recursion/external data. Fold, horizon, mask, latitude and SPEI details are preserved in Phase 3C–G reports. P3-M3B improved both folds; P3-M2/M4/E1 showed pooled gains but unacceptable long-horizon concentration. Seasonal anomaly was rejected before execution; post-result hybrids and ensemble repair were rejected.

The artifact-only ensemble used six nonnegative simplex vectors learned on the opposite fold within fixed G1/G23/G47 groups. It was leakage-safe and broad-ranging except its h6 regression. It trained no model.

## Production and candidates

Production reused the established deterministic Phase 2G two-million-row artifact and 280,961-row Test feature artifact. Every residual target/anchor is same-location and genuinely observed with source <= input < target; Test uses no hidden target, recursion, clipping, fallback, ensemble, or public information. Exact 12-feature order excludes `input_year`.

Configuration SHA: `c1cdd380...178b8`. Model: 727,562 bytes, SHA `0cbefb4e...9203e`. Test provenance/predictions: 19,376,066 bytes, SHA `d666f6de...6441`. Primary `submissions/phase3h_p3m3b_primary.csv`: 280,961 rows, `ID,Target`, SHA `b9b1b95e7f4d255cbeae780a2be33b1c107178d98a1b404b79ae7ea93537f11e`; mean -.032742, SD .685816, range [-2.700959,3.183572]. Persistence diagnostic: SHA `edf8a40f74ab227e0485b02a4cf489893a3118dda2eafc896a8ffd063b9de9c7`, explicitly not preferred. Both are generated, Git-ignored, independently validated, and not uploaded.

The model fitted once. A pre-fit Arrow audit error produced no model. After the valid fit, a CSV validator variable error occurred; hash-verified model, predictions and candidates were retained and the manifest resumed without refitting. Exact fit runtime/RSS were lost and not recreated; Phase 3 validation runtimes and resource evidence remain in the individual reports.

## Reporting, risks, and Phase 4 inputs

`notebooks/02_core_modeling.ipynb` is reporting-only and consumes compact JSON. Evidence matrix, final-report outline, README, production manifest and this closeout were updated. Risks remain: public/local mismatch is unexplained, two folds provide limited temporal diversity, Test is entirely out-of-range in year, P3-D1 is horizon-1/observed-only, and extreme bins are sparse.

Phase 4 should start from the frozen P3-M3B primary candidate and its production manifest, decide whether to upload the primary and/or diagnostic candidate, record results without retroactive tuning, and complete trustworthiness/interpretability and packaging evidence.

Focused production/submission tests passed, along with affected tests, Ruff, notebook JSON validation, artifact hashes/rows, git-ignore, unstaged-path, and validation-v1 checks. No successful experiment, specialist, optimization, production fit, or prediction was unnecessarily rerun. No submission upload, commit, push, branch operation, or remote change occurred.

## Post-closeout owner-requested P3-E1 diagnostic candidate

On 2026-09-06, after approving the Phase 3 closeout, the owner requested a local P3-E1 candidate solely to observe leaderboard generalization. P3-E1 remains non-promoted because frozen cross-fitted h6 RMSE 0.655841 exceeded 0.648339. No validation experiment, optimizer, ensemble repair, retuning, or H6 override occurred. Weights are exactly the arithmetic mean of the two saved directional vectors within G1/G23/G47, renormalized to one.

Persistence, Phase 2, and P3-M3B production predictions were reused. Missing P3-M1, P3-M2, and three P3-M4 specialists were production-fitted once with registered configurations. The generated diagnostic is `submissions/phase3_p3e1_guarded_ensemble_diagnostic.csv`, SHA-256 `7e8a70bd8410988b892c1603959eabcc8921cfae78a26a526e0de5eab2d93efc`. It is not uploaded and does not replace the unchanged P3-M3B primary. Any later public result is diagnostic evidence only and cannot alter validation-v1.
