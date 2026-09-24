# Phase 0 closeout

## 1. Final Phase 0 decision

**Decision: Pass.** All mandatory foundation, integrity, reproducibility, rule-documentation,
and reporting-infrastructure criteria pass. Tracked organizer questions do not prevent the
next phase's read-only data audit. Phase 1 must establish an approved prediction-time,
leakage-control, and validation protocol before modelling begins.

| # | Acceptance criterion | Result | Direct evidence |
| ---: | --- | --- | --- |
| 1 | Five official artifacts accounted for | PASS | `configs/data_manifest.json`; fresh hash/size verification |
| 2 | Competition rules documented | PASS | `docs/competition_rules.md` |
| 3 | Confirmed rules separated from questions | PASS | `docs/competition_rules.md`; `docs/organizer_clarifications.md` |
| 4 | Raw data protected from Git | PASS | `git check-ignore data/raw/example.csv` |
| 5 | Derived data, models, secrets, temp and submissions protected | PASS | Representative `git check-ignore` checks against `.gitignore` |
| 6 | Reproducible uv/Python 3.12 environment | PASS | `.python-version`, `pyproject.toml`, `uv.lock`; `uv lock/sync --check` |
| 7 | Data files readable | PASS | Phase 0C full DuckDB and isolated pandas/Polars reads |
| 8 | Hashes and sizes reproducible | PASS | Manifest verification: five of five matched |
| 9 | Counts, schemas, missingness and ID uniqueness verified | PASS | `reports/phase0_data_benchmark.json` |
| 10 | Submission schema and Test ID alignment verified | PASS | Same row count and ID-sequence digest; exact `ID,Target` header |
| 11 | Hardware and gated benchmarks complete | PASS | `reports/phase0_data_benchmark.json`; every stage `completed` |
| 12 | Parquet caches verified and justified | PASS | Three integrity-equivalent caches; measured size/query benefits |
| 13 | Local/Colab workload policy documented | PASS | `docs/compute_reproducibility_policy.md` |
| 14 | Empty valid experiment registry | PASS | CLI: `Registry valid: 0 record(s)` |
| 15 | Validation placeholder unassigned/unapproved | PASS | `configs/validation_protocol.yaml` |
| 16 | Evidence matrix exists | PASS | `docs/competition_evidence_matrix.md` |
| 17 | Living report outline exists | PASS | `reports/final_report_outline.md` |
| 18 | Compute/reproducibility policy exists | PASS | `docs/compute_reproducibility_policy.md` |
| 19 | No modelling or Phase 1 leakage work occurred | PASS | Zero files in models/submissions/artifacts/tmp; dependency and registry audit |
| 20 | No blocker prevents Phase 1 read-only data auditing | PASS | Risks are registered; none blocks data auditing |

## 2. Starting repository state

Canonical path: the repository root.
The repository was on unborn branch `main`: no HEAD commit, no staged files, no modified
tracked files, 37 untracked non-ignored foundation files, and no remotes. No commit hash exists.

## 3. Ending repository state

The branch remains unborn `main`. The closeout is an additional untracked file. Nothing is
staged, committed, or pushed; no remote exists. Generated data, the virtual environment, and
caches remain ignored.

## 4. Hardware and compute assessment

- OS/architecture: Windows 11 AMD64.
- CPU: 2 physical cores, 4 logical processors.
- Physical RAM: 17,054,662,656 bytes (15.88 GiB).
- Audit-time available RAM: 7,235,289,088 bytes (6.74 GiB), 57.6% utilized.
- Disk: 255,045,136,384 bytes total; 70,942,769,152 bytes (66.07 GiB) free.
- Intel GPU is not a project dependency.

Operation-specific Class A–D gates preserve `max(4 GiB, 30% RAM)` and require isolated,
sequential children. Phase 0C completed within the gates without weakening the reserve.

## 5. Colab fallback assessment

The laptop is authoritative and adequate for verified sequential data work under the memory
gates. Free Colab is a provisional, free-first fallback only; official permission has not been
confirmed. Remote work is incomplete until configuration, logs, metrics, and artifacts return
to this repository. Paid services and card-required trials are prohibited.

## 6. Official files inventoried

The official set is `data/raw/Train.csv`, `data/raw/Test.csv`,
`data/raw/SampleSubmission.csv`,
`StarterNotebook.ipynb`, and `Trustworthiness_Evaluation.pdf`. The trustworthiness artifact is
a PDF, not a DOCX. Raw/reference artifacts are immutable and represented in the tracked
manifest.

## 7. Competition-rule findings

Confirmed evidence covers the next-month TWS task, effective 1–7-month horizons, prohibition
on future observations, RMSE and final weights (50%/30%/20%), submission format and limits,
team rules, two-submission private selection, open-source requirements, AutoML and paid-service
restrictions, external-data availability, top-10 72-hour review, possible 24-hour code request,
and the trustworthiness rubric. Source inconsistencies and unresolved interpretations are
separated in `docs/competition_rules.md` and `docs/organizer_clarifications.md`.

## 8. Repository structure created

The project now separates configs, documentation, decisions, closeouts, experiment records,
notebooks, reports, source, tests, ignored raw/processed data, ignored models/artifacts/temp,
and ignored submissions. `src/drought_forecasting` contains bounded preflight, benchmark, and
registry utilities. Protective ignore rules keep source and governance artifacts visible.

## 9. Python environment and locked dependencies

uv 0.12.9 manages CPython 3.12.14 AMD64 at `.venv/Scripts/python.exe`; Python is constrained
to `>=3.12,<3.13`. Exact installed distributions are:

`duckdb==1.5.5`, `numpy==2.5.2`, `pandas==3.0.5`, `polars==1.44.1`,
`polars-runtime-32==1.44.1`, `psutil==7.2.2`, `pyarrow==25.0.1`, `PyYAML==6.0.3`,
`pytest==9.1.1`, `ruff==0.16.5`, `colorama==0.4.6`, `iniconfig==2.3.0`,
`packaging==26.3`, `pluggy==1.6.0`, `Pygments==2.21.0`,
`python-dateutil==2.9.0.post0`, `six==1.17.0`, and `tzdata==2026.3`.

No modelling or geospatial dependencies were installed.

## 10. File hashes, schemas and integrity

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/raw/Train.csv` | 289,126,551 | `97ff1912b35871574a01900c24a792a9a418653e87f01dccc1788c6838d94b1f` |
| `data/raw/Test.csv` | 34,365,988 | `314da7996fa947b30797d82ea8d0ea34240fe52683ecf102a21c37f00f61c196` |
| `data/raw/SampleSubmission.csv` | 6,105,524 | `77881bc7257791d583c5a1f496a5639864d490a0237515338fc5305ec943db22` |
| `references/official/StarterNotebook.ipynb` | 1,236,676 | `a9adf72aa1b75c41c72357f1e5bbe2e1b2c90d787d0c9c9fbce7a46bfb3874b4` |
| `references/official/Trustworthiness_Evaluation.pdf` | 94,458 | `217d7da35de4bff29d66377f20fd80d2fc26ed9e4946060613bb4f9f4de1c792` |

Verified parsed counts—not provisional line estimates—are 2,154,021 Train rows and 280,961
rows each for Test and SampleSubmission. Train/Test have 13 columns; SampleSubmission has 2.
Scientific numeric fields are Float64/DOUBLE, identifiers are strings, dates parsed completely,
and the mask is Boolean. Train has no nulls or numeric NaNs. Test has 186,913 null `TWS_t`
values, zero other nulls, and zero numeric NaNs. IDs are non-null and unique. Test and
SampleSubmission row counts and ordered ID digests match exactly.

## 11. Load-time, memory and storage benchmarks

| Dataset | Pandas CSV load | Polars CSV load | Parquet load | Pandas dataframe memory | Polars dataframe memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 7.679 s | 1.881 s | 0.350 s | 285,904,602 B | 238,516,008 B |
| Test | 1.096 s | 0.254 s | 0.055 s | 35,325,590 B | 28,923,846 B |
| SampleSubmission | 0.375 s | 0.023 s | 0.024 s | 9,758,139 B | 7,510,319 B |

Dataframe memory above is distinct from child process peak RSS. Maximum measured child peaks
were 696,774,656 bytes for Train Polars CSV, 205,062,144 bytes for Test Polars CSV, and
158,031,872 bytes for SampleSubmission pandas CSV.

All three Parquet files were much smaller: Train 116,573,052 bytes (2.48× reduction), Test
11,721,748 bytes (2.93×), and SampleSubmission 273,900 bytes (22.29×). Parquet improved
Train/Test loading but was marginally slower for loading the small SampleSubmission. Streaming
aggregation was faster for all three and equal to CSV within relative tolerance `1e-10`.

## 12. Local-versus-Colab workload matrix

| Workload | Location/status | Control |
| --- | --- | --- |
| Streaming integrity/hash | Local | Class A gate |
| Parquet conversion/verification | Local | Class B gate |
| Single Polars/Parquet materialization | Local when authorized | Class C gate |
| Naive pandas materialization | Local when authorized; skip allowed | Class D gate |
| Phase 1 audit | Local-first | Prediction-time controls required |
| Modelling/tuning | Not authorized yet | Approved Phase 1 protocol required |
| Free Colab | Provisional fallback | Organizer permission unresolved |
| Paid/card-required service | Prohibited | Do not use |

## 13. Documentation and reporting infrastructure

Phase 0 created official-rule documentation, a prioritized clarification register, a draft
validation placeholder, evidence matrix, living final-report outline, compute policy, data
manifest, decision log, closeout structure, and atomic experiment registry. The registry has
one header row and zero records; empirical fields remain empty.

## 14. Complete files-created/changed inventory

Trackable foundation and closeout files are:

`.gitignore`; `.python-version`; `README.md`; `pyproject.toml`; `uv.lock`;
`configs/.gitkeep`; `configs/data_manifest.json`; `configs/experiment_registry.schema.json`;
`configs/validation_protocol.yaml`; `docs/competition_evidence_matrix.md`;
`docs/competition_rules.md`; `docs/compute_reproducibility_policy.md`;
`docs/organizer_clarifications.md`; `docs/validation_protocol.md`;
`docs/decisions/.gitkeep`; `docs/decisions/README.md`;
`docs/decisions/0001-phase0-foundation.md`; `docs/phase_closeouts/.gitkeep`;
`docs/phase_closeouts/README.md`; `docs/phase_closeouts/phase0_closeout.md`;
`experiments/.gitkeep`; `experiments/README.md`; `experiments/registry.csv`;
`notebooks/.gitkeep`; `reports/figures/.gitkeep`; `reports/final_report_outline.md`;
`reports/phase0_data_preflight.json`; `reports/phase0_data_benchmark.json`;
`src/drought_forecasting/__init__.py`; `src/drought_forecasting/data_preflight.py`;
`src/drought_forecasting/data_benchmark.py`;
`src/drought_forecasting/experiment_registry.py`; `tests/.gitkeep`;
`tests/test_data_preflight.py`; `tests/test_data_benchmark.py`;
`tests/test_experiment_registry.py`.

Official notebook/PDF inputs are preserved under `references/official`. Three generated,
ignored Parquet caches exist under `data/processed`; `.venv` and tool/test caches are ignored.

## 15. Tests and checks

Pre-closeout results: registry CLI exit 0 with zero records; `uv lock --check` exit 0;
`uv sync --check` exit 0 with no changes; `uv run pytest` exit 0 with 34 passing tests;
`uv run ruff check .` exit 0; `git diff --check` exit 0; manifest verification five of five;
protected ignore checks passed; representative source/config/docs/report/registry paths were
not ignored; exactly three processed caches existed and were ignored.

## 16. Risks and unresolved questions

Official permission remains unresolved for AI coding assistants and free Colab. The AutoML
boundary, external-data timing semantics, recursive forecasting across masked horizons,
deadline time/timezone, reproducibility-package layout, and detailed trustworthiness and
innovation scoring remain open. These risks do not block a read-only Phase 1 data audit, but
relevant questions must be resolved before affected modelling, external-data, remote-compute,
or final-submission actions.

## 17. Recommended Phase 1 inputs

Use `configs/data_manifest.json`, the verified Parquet caches, Phase 0 preflight/benchmark
reports, `docs/competition_rules.md`, `docs/organizer_clarifications.md`, and the draft
validation constraints. Phase 1 should begin with prediction-time availability, masked-horizon,
and leakage-risk auditing. It must version and approve a validation protocol before any model
training or experiment registry entry.

## 18. Out-of-scope work confirmation

No model was fitted, no validation score calculated, no folds/windows selected, no submission
created, no external data acquired, no leakage conclusion produced, and no Phase 1 analysis
started. Benchmark aggregates were used only for storage equivalence and were not reported as
scientific results.

## 19. Git handoff note

Nothing has been staged, committed, or pushed, and no remote has been added. HEAD remains
unborn, so no Git commit hash is claimed. Repository review and any first commit require
explicit user approval.
