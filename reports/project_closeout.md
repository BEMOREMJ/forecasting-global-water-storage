# Project closeout

## Final status

**Portfolio-ready as of 24 September 2026.** The competition closed on 13 September 2026, and
this repository is archived as a completed geospatial machine-learning and time-series forecasting
case study. No further modelling, tuning, submissions, or leaderboard experiments are planned.

The closeout began on `main` at `773d335e594ca63537aa5ae23b98386737a6d823`, synchronized with
`origin/main` at 0/0 divergence. The worktree already contained the completed Phase 5 evidence set;
it was preserved, validated, and included with the portfolio documentation.

## Final model and verified results

The recommended reference remains **P3-M3B**, a deterministic 200-round LightGBM model trained to
predict a persistence residual. It uses the last genuinely observed same-location TWS as its anchor,
models effective horizon explicitly, uses 12 spatial/calendar/drought/soil-moisture features, and
excludes raw year after drift analysis.

| Evidence | RMSE | Status |
|---|---:|---|
| P3-M3B pooled OOF | 0.583923 | Selected reference |
| P3-M3B public leaderboard | 0.766408529 | Uploaded during competition |
| Persistence pooled OOF | 0.673722 | Baseline |
| Persistence public leaderboard | 0.886420231 | Rejected diagnostic |
| P3-E1 ensemble pooled OOF | 0.571686 | Rejected: horizon-6 gate |
| P3-E1 public leaderboard | 0.878413825 | Rejected diagnostic |
| Phase 5 CatBoost pooled OOF | 0.609267883 | Rejected; no candidate or upload |

Local OOF and leaderboard results concern different data. P3-M3B's public-minus-local gap was
0.182485529, so the public result is not presented as confirmation of the local estimate.

## Modelling stages and decisions

1. Phase 0 established the repository, data manifests, memory policy, and organizer evidence.
2. Phase 1 froze leakage-safe rolling-origin validation and historical transplantation of the test
   masking pattern.
3. Phase 2 established deterministic baselines, effective-horizon examples, a fixed LightGBM
   benchmark, and the submission contract.
4. Phase 3 evaluated residual models, temporal drift, specialists, and a guarded ensemble. P3-M3B
   was the only learned design promoted under all applicable gates and was fitted for production.
5. Phase 4 rejected seasonal-change, neighbouring-cell, and recency-weighted challengers.
6. Phase 5 evaluated CatBoost 1.2.8 exactly once on the full two-million-row training population.
   It failed the pooled threshold of 0.578923, fold stability, horizons 6/7, and recent-period gates.

No Phase 5 production model, submission candidate, or upload was created.

## Validation and leakage controls

Validation uses two target-disjoint rolling origins and 551,965 pooled OOF rows. The complete test
masking path is transplanted to each historical window, preserving effective horizons 1-7. Training
targets must be available at the fold origin; learned transformations are fold-local; validation
targets are excluded; anchors are genuinely observed and from the same location; and recursion is
disabled. Pooled RMSE is calculated from total squared error and row count rather than averaging
fold RMSE values.

## Technical lessons

- Masked observations transform a nominal one-step problem into a multi-horizon problem.
- Horizon and mask-state slices exposed risks hidden by aggregate RMSE.
- Removing raw year improved the selected residual representation under temporal shift.
- Greater complexity did not guarantee better generalization: the guarded ensemble and CatBoost
  challenger both failed pre-registered protection gates.
- Fixed configurations, artifact identities, an append-only registry, and explicit promotion rules
  supported honest rejection decisions.
- Polars, DuckDB, bounded audits, fixed sampling, and two-thread training kept the workflow usable
  on approximately 16 GB of local RAM.

## Limitations

The public/local performance gap remains unexplained because hidden test labels are unavailable.
Two historical folds provide limited temporal diversity. Current-month covariate availability in a
real operational setting was not established. Hardware constrained the breadth of experiments.
This is a competition prototype, not a production drought-warning system, and TWS alone is not a
complete drought-impact assessment.

## Reproduction and verification status

The environment is specified by `pyproject.toml`, `.python-version`, and `uv.lock`. Configurations,
source, tests, the experiment registry, compact metrics, manifests, and reporting notebooks are
tracked. Raw and processed data, predictions, submissions, fitted models, caches, and temporary
artifacts remain ignored. Full training was not repeated during closeout; accepted historical
results remain the evidence of record.

Closeout verification covered Git diffs, Ruff, focused Phase 5 and registry/notebook tests,
notebook JSON structure, relative Markdown links, registry validation, ignored-artifact behavior,
tracked-file and history safety, secret patterns, and staged-file review. Exact final command results
are recorded in the closing commit handoff.

## Public-release review

- No raw Train, Test, or SampleSubmission file has ever been tracked.
- No processed competition data, fitted model, generated prediction, or submission payload has ever
  been tracked. Compact JSON metadata under `reports/submissions/` contains scores and hashes only.
- No credential, token, private key, service-account file, or `.env` file was found in the current
  tree or seven-commit history.
- Machine-specific paths found in two Phase 0 records were normalized during closeout.
- The organizer's starter notebook and trustworthiness PDF were intentionally committed in Phase 0.
  The competition page names them as challenge files, identifies challenge data as CC-BY-SA 4.0,
  and expressly permits sharing. Attribution is recorded in `references/official/README.md`.

## License decision

No repository-wide license was added. That avoids applying a software license to mixed-origin
organizer material without a file-level rights review. The organizer files retain the competition's
CC-BY-SA 4.0 terms and attribution. A future code-only release could license the author's original
code separately after confirming the desired license.

## Portfolio positioning

Present this work as a geospatial machine-learning and time-series forecasting project for global
TWS under irregular observation and multi-horizon test conditions. Its strongest evidence is the
validation design, leakage control, reproducible experiment governance, memory-aware execution, and
honest comparison of local and public results-not a competition win or production deployment.

## Files changed during closeout

- `README.md`
- `reports/project_closeout.md`
- `references/official/README.md`
- `docs/competition_rules.md`
- `docs/decisions/0001-phase0-foundation.md`
- `docs/phase_closeouts/phase0_closeout.md`
- `reports/final_report_outline.md`
- the pre-existing Phase 5 evidence and implementation files listed in `reports/phase5_closeout.md`
