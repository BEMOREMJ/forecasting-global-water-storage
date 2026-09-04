# Phase 2 closeout

## 1. Final decision

**Pass.** Phase 2 met its modeling, leakage-safety, coverage, comparison, notebook,
and local-submission objectives. Six deterministic baselines and one fixed LightGBM benchmark
were evaluated on the unchanged 551,965-row validation-v1 population; LightGBM improved over
persistence without tuning; and the 280,961-row submission candidate passed an independent
disk-based structural and ID/order validator.

The three incorrectly transcribed official-CSV SHA-256 values in the Phase 2G configuration and
manifest were corrected directly from the authoritative Phase 0 manifest. This metadata-only
correction did not regenerate or change the candidate, model, training artifacts, predictions,
accepted metrics, diagnostics, validation results, or resource evidence.

## 2. Repository bounds

- Starting checkpoint and current HEAD: `b3003209ec29c860498a93bf5163784fe720a64c`.
- Ending branch: `main`.
- Ending state: uncommitted Phase 2 source, tests, configurations, compact evidence, notebook,
  dependency-lock, README, registry, and documentation changes; protected and large outputs are
  unstaged and ignored.
- No commit, index modification, push, remote creation, upload, leaderboard inspection, or Phase
  3 implementation occurred.

## 3. Manifest and frozen validation identities

| Identity | Stored value | Verification |
|---|---|---|
| Phase 0 manifest | `445ce8f92d21abe7e103ad77f38091a4f55e0466d31515d33fbd40c06fb8e533` | Consistent across Phase 2A, registry, and Phase 2D |
| validation-v1 structural audit | `dfafe4ae008ac4180f3f92a54ca825c779ab4768b0ba870e22dd1cd4e14088c9` | Consistent across Phase 1 and Phase 2 |
| comparable rows | `2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a` | 551,965 rows; all seven experiments match |
| Test mask template | `78a51b2611a9c02dd0c7960bb25a23eae51d051a3d14dbb4cee18f75858072c8` | Frozen Phase 1 record |
| official starter Git identity | `4cd7b8ec4a6a819011a9cd807f6cc107925783fb` | Rechecked and matched |

Authoritative official-file hashes from `configs/data_manifest.json` are Train
`97ff1912b35871574a01900c24a792a9a418653e87f01dccc1788c6838d94b1f`, Test
`314da7996fa947b30797d82ea8d0ea34240fe52683ecf102a21c37f00f61c196`, and
SampleSubmission `77881bc7257791d583c5a1f496a5639864d490a0237515338fc5305ec943db22`.
Phase 2G now records these same authoritative identities. The prior transcription values were
replaced without reading or hashing the large files.

`git status --short` restricted to validation-v1 code, configuration, manifest, and documentation
was empty. The frozen protocol was not rebuilt or modified.

## 4. Phase 2A: common prediction contract

The canonical row contains run, fold, canonical location, input month, target month, horizon,
mask state, prediction, validation actual, model name, configuration identity, data-manifest
identity, and validation identity. Its key is `(fold_id, location_id, input_month, target_month)`.
Validation rejects missing/nonfinite output, duplicate or non-comparable rows, bad horizons,
calendar inconsistencies, identity mismatches, and incorrect official ID/order.

Every configured fallback chain terminates at fold-local global mean:

- global mean;
- location mean -> global mean;
- location/calendar-month climatology -> location mean -> global mean;
- persistence -> climatology -> location mean -> global mean;
- seasonal naive -> persistence -> climatology -> location mean -> global mean;
- location trend/seasonal -> seasonal naive -> persistence -> climatology -> location mean ->
  global mean.

Each selected level and missing-stage reason is recorded; difficult rows cannot be dropped.
Details: `configs/phase2a_prediction_contract.yaml` and
`docs/phase2a_prediction_contract.md`.

## 5. Phase 2B: deterministic baselines

All runs used fold-local target histories, exact calendar joins, observed-only TWS, no recursion,
the Phase 2A validator before metrics, and full comparable-row coverage.

| Baseline | Pooled RMSE | F01 | F02 | Runtime s | Peak MiB | Coverage | Fallback rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| global mean | 0.906959 | 0.964546 | 0.844492 | 135.25 | 2206.05 | 100% | 0% |
| location mean | 0.909744 | 0.852776 | 0.964139 | 126.68 | 2205.79 | 100% | 0% |
| location/calendar climatology | 0.972241 | 0.961973 | 0.982556 | 144.88 | 2298.00 | 100% | 0.001812% |
| persistence | 0.673722 | 0.649746 | 0.697219 | 120.61 | 2253.87 | 100% | 0% |
| seasonal naive | 0.964292 | 0.950403 | 0.978190 | 88.65 | 2229.05 | 100% | 0.140770% |
| location trend/seasonal | 1.309624 | 1.514221 | 1.062359 | 80.68 | 2275.71 | 100% | 0.001812% |

Persistence is the deterministic performance floor and remains the required reference/fallback.
Full fold, horizon, mask, latitude, SPEI, fallback, runtime, and artifact records are under
`reports/phase2b/`.

## 6. Phase 2C: horizon-aware examples

For target `y` and horizon `h`, covariates come from exact month `y-1` and observed TWS from
exact month `y-h` at the same canonical location. Targets are restricted to each fold cutoff;
missing source months are excluded without adjacent-row replacement. Fold construction is
independent and validation targets cannot enter fitting.

The 9,470,789-row eligible expansion was too large for safe downstream in-memory learning, so a
single seed-20260904 SHA-256-ranked sample retained 2,000,000 rows with fold/horizon quotas and
population/retained weights. Configuration identity is
`ac6e737441d115475f8062d2e53bff57b16d4d8b3786aa54f8ac9a34866dd05e`; retained identity is
`4e1fc3745b754ae0020e111fa0d4e65afd3daf8b63034b7095340d3dc15fe95d`; artifact hash is
`078ad361f03159ddd5b1f1f0a30e311d261ce82e1ab938d4e56cf56e2885e31b`.
Materialization took 231.787 seconds, peaked at 2093.36 MiB, and produced 214,652,339 bytes.
See `reports/phase2c_horizon_examples_manifest.json`.

## 7. Phase 2D: fixed LightGBM benchmark

One deterministic CPU GBDT used 13 float32 features, 200 rounds, seed 20260904, two threads, no
early stopping, no tuning, and the Phase 2C stratum weights. Folds trained independently. Its
configuration identity is
`45252c89a4f4a33e15ce0a6f53d0e65989bf656de3cb46cd8d04504ef4ec70dc`.

| Measure | LightGBM | Persistence | LightGBM improvement |
|---|---:|---:|---:|
| pooled RMSE | 0.592987 | 0.673722 | 0.080735 / 11.983% |
| F01 RMSE | 0.593578 | 0.649746 | 0.056168 |
| F02 RMSE | 0.592387 | 0.697219 | 0.104832 |
| fold gap | 0.001191 | 0.047473 | 0.046283 smaller |
| horizon 1 | 0.535286 | 0.532489 | -0.002797 |
| horizon 2 | 0.605097 | 0.641012 | 0.035915 |
| horizon 3 | 0.612378 | 0.705974 | 0.093596 |
| horizon 4 | 0.609151 | 0.733276 | 0.124126 |
| horizon 5 | 0.623948 | 0.808767 | 0.184819 |
| horizon 6 | 0.643339 | 0.865881 | 0.222542 |
| horizon 7 | 0.691007 | 0.926619 | 0.235612 |
| observed RMSE | 0.535286 | 0.532489 | -0.002797 |
| masked RMSE | 0.619918 | 0.734424 | 0.114505 |
| runtime seconds | 125.329 | 120.614 | -4.715 |
| peak MiB | 2122.25 | 2253.87 | 131.61 lower |

The LightGBM OOF artifact is 28,655,023 bytes; fitted models total 1,433,549 bytes. Exact hashes
and metrics are in `reports/phase2d/run-20260904T064720Z-lightgbm_basic-metrics.json`.

## 8. Phase 2E: registry and comparison

The registry contains exactly seven validation experiments. All seven compact metrics paths
exist; registry and comparison run-ID sets agree; pooled, both-fold, and horizons 1--7 values
match exactly. Phase 2E ranks LightGBM first and persistence second. Comparison details and its
latitude/SPEI summaries are in `reports/phase2e_comparison.json` and
`docs/phase2e_comparison.md`.

## 9. Phase 2F: educational evidence

`notebooks/01_baseline_walkthrough.ipynb` explains the frozen validation design, deterministic
floor, horizon-example provenance, fixed LightGBM benchmark, diagnostic interpretation, and
submission safeguards without replacing or modifying the official starter notebook. README,
evidence-matrix, and final-report-outline updates connect the notebook to the compact artifacts.

## 10. Phase 2G: first-submission candidate

The production population was explicitly rebuilt at the 2015-09-01 Test cutoff rather than
concatenating validation folds. Of 13,448,677 eligible examples, exactly 2,000,000 were selected
once using the Test horizon distribution and seed 20260904. Retained identity is
`9526f039a7d8a0cb5ddc46d605936a265d416d7dcb12872610136cbbd915f3e9`.

The ignored candidate `submissions/phase2g_lightgbm_basic.csv` has 280,961 rows, exactly columns
`ID,Target`, official Test and SampleSubmission ID order, zero duplicate IDs, zero missing or
nonfinite targets, and no index column. Independent on-disk validation passed. It was not
uploaded. Candidate SHA-256 is
`ebb1f53ac5ef75a16f618e714bc2a95ba7a84269ac86c80315896944a5e1b124`
and size is 11,307,814 bytes. Prediction range is -2.055248 to 2.064340, mean -0.103831,
standard deviation 0.589283, with no values outside the final-fit target range. Full artifact
hashes and diagnostics are in `reports/phase2g_submission_manifest.json`.

The initial production process failed at Test-view creation after successful materialization and
fitting because DuckDB rejected a prepared parameter in `CREATE VIEW`. The saved valid upstream
artifacts were not rerun; only incomplete downstream stages resumed. Exact upstream timing and
peak telemetry were lost. Approximate end-to-end wall time was seven minutes; recovery took
20.557 seconds, with prediction/write taking 8.257 seconds at 348.22 MiB and independent
validation taking 3.500 seconds. Phase 2C and Phase 2D retain exact comparable resource evidence.

## 11. Diagnostic interpretation

Measured LightGBM error rises from 0.535286 at horizon 1 to 0.691007 at horizon 7. It slightly
underperforms persistence at horizon 1 but materially improves horizons 2--7. Masked rows are
weaker than observed rows (0.619918 versus 0.535286). The weakest populated latitude bands are
`[-60,-30)` at 0.702696 and `[-30,0)` at 0.677973; `[30,60)` is strongest at 0.555143.
Higher-error LightGBM SPEI slices include positive extreme SPEI-06 (`[2,inf)`, 0.669609),
positive-high SPEI-06 (`[1.5,2)`, 0.662704), and positive-high SPEI-03 (`[1.5,2)`, 0.651932).
These are descriptive findings, not tuning decisions. Complete subgroup counts are stored in the
Phase 2D compact metrics.

## 12. Acceptance criteria

| Criterion | Result | Concise evidence | Artifact |
|---|---|---|---|
| Common contract and terminal fallbacks | Pass | Strict schema, comparable identity, explicit chains | `configs/phase2a_prediction_contract.yaml` |
| Six deterministic baselines | Pass | Six full-coverage runs on common rows | `reports/phase2b/` |
| Deterministic floor | Pass | Persistence pooled RMSE 0.673722 | persistence metrics JSON |
| Leakage-safe horizon examples | Pass | Exact-calendar provenance checks; 2M deterministic rows | Phase 2C manifest |
| Fixed supervised benchmark | Pass | One frozen LightGBM run, pooled 0.592987 | Phase 2D metrics |
| Improvement without tuning | Pass | 0.080735 / 11.983% pooled improvement; both folds improve | Phase 2E comparison |
| Registry integrity | Pass | Seven compact artifacts; IDs and accepted metrics agree exactly | `experiments/registry.csv` |
| Educational notebook/reporting | Pass | Notebook and linked reporting files exist | baseline notebook |
| Submission structure | Pass | Independent disk validator passed 280,961 `ID,Target` rows | Phase 2G manifest |
| Official identity metadata | Pass | Phase 2G values exactly match the authoritative Phase 0 hashes | Phase 0 manifest; Phase 2G manifest |
| validation-v1 protected state | Pass | Targeted worktree status empty | validation-v1 paths |
| Scope controls | Pass | No upload, external data, recursion, AutoML, paid compute, or tuning | phase documentation |

## 13. Tests and checks by subphase

Accepted review evidence records focused passing suites for Phase 2A prediction contracts, Phase
2B baselines/fallbacks, Phase 2C provenance, Phase 2D LightGBM, Phase 2E comparison, and Phase 2F
notebook structure. Their test files are respectively `tests/test_prediction_contract.py`,
`tests/test_deterministic_baselines.py`, `tests/test_horizon_examples.py`,
`tests/test_lightgbm_benchmark.py`, `tests/test_phase2_comparison.py`, and
`tests/test_phase2_notebook.py`. Exact pytest counts/timings for A--F were not persisted in compact
artifacts and were not recreated during closeout.

Phase 2G initially reported 3 passes and 2 environment setup errors because pytest could not
access its system temporary directory; no assertion failed. The corrected focused command was:

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=tmp/phase2g_pytest tests/test_submission_candidate.py
..... [100%]
5 passed in 2.45s
```

No earlier Phase 2 test, full suite, audit, fold construction, example materialization, baseline,
benchmark, comparison, notebook, generator, or submission validator was rerun for this closeout.

## 14. Failed and rejected approaches

- Row-position temporal lookup, later-value backfill, recursive predicted TWS, validation-target
  fitting, implicit/drop-on-failure fallbacks, and submission sorting were rejected by design.
- Full Phase 2C expansion was rejected for downstream in-memory training because of memory risk.
- Broad tuning, multiple caps, alternative final models, AutoML, and leaderboard-guided selection
  were outside scope.
- Phase 2G's prepared-parameter view creation failed downstream; successful upstream work was
  preserved, and only incomplete stages resumed.
- Exact Phase 2G upstream telemetry is irrecoverable without an unauthorized rerun.
- Phase 2G initially contained incorrectly transcribed official hashes. They were corrected from
  the authoritative Phase 0 manifest as metadata only; no result artifact was regenerated.

## 15. Risks, limitations, and organizer questions

- Long-horizon and masked-input errors remain materially higher; weak latitude and extreme SPEI
  slices need cautious robustness evaluation.
- LightGBM is marginally worse than persistence at horizon 1, so persistence must remain a
  reference and potential fallback/blending component.
- Evaluation peaks near 2.2 GiB; future work must retain bounded memory, sequential execution,
  and explicit spill/resource estimates.
- The 2M training sample is deterministic and weighted but not the full eligible population.
- Validation has two historical folds; temporal/regional generalization remains uncertain.
- Organizer clarification remains desirable for any future recursive policy, interpretation of
  masked TWS beyond the published template, and whether any post-submission feedback may be used.
- Phase 2G upstream materialization/fitting telemetry is incomplete, as disclosed above.

## 16. Recommended Phase 3 inputs (recommendations only)

1. Preserve validation-v1, comparable-row identity, persistence, and the fixed LightGBM result as
   immutable references.
2. Pre-register a small number of hypothesis-driven experiments addressing horizons 2--7,
   masked inputs, weak latitude bands, and high-error SPEI bins; avoid broad hyperparameter search.
3. Evaluate a horizon-aware strategy and a guarded persistence/model combination, explicitly
   checking horizon 1 rather than assuming the learned model dominates.
4. Keep each experiment under the observed approximately 2.2 GiB envelope and require the same
   fold, coverage, subgroup, artifact, and one-run evidence.

These are candidate inputs for later scoping, not Phase 3 approval or implementation.

## 17. Proposed commit contents

Do not stage or commit before planner review. Proposed contents are:

- source: `src/drought_forecasting/{prediction_contract,deterministic_baselines,horizon_examples,lightgbm_benchmark,phase2_comparison,submission_candidate}.py`;
- tests: the corresponding seven `tests/test_*.py` Phase 2 files;
- configuration: `configs/phase2a_prediction_contract.yaml`,
  `configs/phase2c_horizon_examples.yaml`, `configs/phase2d_lightgbm.yaml`, and
  `configs/phase2g_submission.yaml`;
- compact reports: `reports/phase2b/`, Phase 2C manifest, `reports/phase2d/`, Phase 2E JSON,
  Phase 2G manifest and this closeout;
- notebook: `notebooks/01_baseline_walkthrough.ipynb`;
- documentation: all Phase 2A--2G docs, `README.md`, `docs/competition_evidence_matrix.md`, and
  `reports/final_report_outline.md`;
- registry/dependencies: `experiments/registry.csv`, `pyproject.toml`, and `uv.lock`.

Explicitly exclude all `artifacts/phase2b/` OOF files, Phase 2C production Parquet, Phase 2D models
and OOF predictions, Phase 2G final-fit examples/model/Test features/raw predictions,
`submissions/phase2g_lightgbm_basic.csv`, all raw/processed competition data, official files,
`references/official/StarterNotebook.ipynb`, pytest caches, and temporary directories.

## 18. Scope confirmation

Validation-v1 and protected inputs remained unchanged. No upload, external data, recursion,
AutoML, paid compute, leaderboard-driven tuning, or out-of-scope model work occurred. The
submission remains `not_uploaded`. This closeout performed only small-artifact reads, an official
starter Git-identity check, path/status checks, and report creation.
