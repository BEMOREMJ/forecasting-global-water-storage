# Drought Forecasting: Global Water Storage Challenge

This private, non-publishable working repository supports the Zindi **A Step Ahead of
Drought: Forecasting Global Water Storage Challenge**. The task is to predict next-month
Total Water Storage (TWS) globally. Masked test `TWS_t` values create effective forecast
horizons of approximately 1–7 months.

## Status

Phase 1 is closed and leakage-safe `validation-v1` is frozen. Phase 2A--2E established the
prediction contract, six deterministic baselines, horizon-aware training data, one fixed
LightGBM benchmark, and a validated seven-run comparison. `lightgbm_basic` is preferred at
pooled OOF RMSE 0.592987; persistence is the strongest deterministic reference at 0.673722.

The documented final evaluation weights are:

- leaderboard RMSE: 50%;
- AI trustworthiness: 30%;
- innovation and practicality: 20%.

Current official rules prohibit future information and leakage, AutoML, and paid services.
They require open-source tooling and reproducible work. The top 10 must provide their model,
code, and report within 72 hours of the organizer request. Unresolved questions—including
the precise AutoML boundary, AI-assistant use, free Colab use, and detailed external-data
availability—remain subject to organizer clarification.

Official sources:

- [competition page](https://zindi.world/competitions/one-step-ahead-of-drought-forecasting-global-water-storage-challenge)
- `references/official/StarterNotebook.ipynb`
- `references/official/Trustworthiness_Evaluation.pdf`

## Compute and reproducibility policy

Development is local-first and free-first. This laptop is the authoritative repository
environment. Free Google Colab is only a provisional fallback pending organizer
clarification. Every permitted remote run must return its configuration, metrics, and
artifacts to this repository workflow so results remain traceable and reproducible.

## Setup

Install uv, then run:

```powershell
uv python install 3.12
uv sync --dev
uv run python --version
uv run pytest
uv run ruff check .
```

The lockfile records exact resolved versions. Python is constrained to the 3.12 minor series.
The lightweight `notebooks/01_baseline_walkthrough.ipynb` can be opened from the repository root
or notebook directory. Its normal cells load only compact JSON/CSV evidence using installed
pandas; no extra notebook runtime is required for repository validation.

## Directory map

```text
configs/                 Versioned configuration
data/raw/                Ignored competition inputs
data/processed/          Ignored derived datasets
docs/                    Decisions and phase closeouts
experiments/             Experiment registry structure
notebooks/               Project notebooks
src/drought_forecasting/ Python source package
tests/                   Automated tests
reports/                 Reports and figures
references/official/     Official competition materials
submissions/             Generated submission outputs
models/                  Generated trained models
artifacts/               Generated run artifacts
tmp/                     Temporary files
```

Competition data, processed data, models, credentials, temporary artifacts, and generated
submission CSV/Parquet files are Git-ignored. Source, configuration, documentation, reports,
the environment specification, and official reference materials remain versionable.

LightGBM is the only modelling dependency added in Phase 2. CatBoost, neural-network,
geospatial, explainability, AutoML, and tuning packages were not added.

## Phase 2 reproduction and evidence

Compact evidence lives in `reports/phase2b/`, `reports/phase2c_horizon_examples_manifest.json`,
`reports/phase2d/`, and `reports/phase2e_comparison.json`; the seven records are in
`experiments/registry.csv`. Large OOF predictions, fitted models, and the 2,000,000-row training
artifact remain Git-ignored under `artifacts/`. Do not rerun expensive production work merely to
recover reporting telemetry. Phase 3 reporting is summarized in `notebooks/02_core_modeling.ipynb`
and `reports/phase3_closeout.md`; generated Phase 3 candidates remain local and unuploaded.
view results.

```powershell
# One baseline: approximately 81-145 s and 2.2-2.3 GiB peak
.\.venv\Scripts\python.exe -m drought_forecasting.deterministic_baselines --baseline persistence
# Horizon examples: approximately 232 s and 2.1 GiB peak
.\.venv\Scripts\python.exe -m drought_forecasting.horizon_examples --config configs\phase2c_horizon_examples.yaml
# Fixed LightGBM: approximately 125 s and 2.1 GiB peak
.\.venv\Scripts\python.exe -m drought_forecasting.lightgbm_benchmark --config configs\phase2d_lightgbm.yaml
# Lightweight registry/comparison consolidation
.\.venv\Scripts\python.exe -m drought_forecasting.phase2_comparison
```

The official `references/official/StarterNotebook.ipynb` is protected and unchanged.

## Project governance and evidence

- [Competition rules](docs/competition_rules.md)
- [Organizer clarification register](docs/organizer_clarifications.md)
- [Compute and reproducibility policy](docs/compute_reproducibility_policy.md)
- [Frozen validation protocol](docs/validation_protocol.md)
- [Competition evidence matrix](docs/competition_evidence_matrix.md)
- [Experiment registry](experiments/README.md)
- [Living final-report outline](reports/final_report_outline.md)
- [Phase closeouts](docs/phase_closeouts/README.md)
- [Decision records](docs/decisions/README.md)
- [Phase 2 comparison](docs/phase2e_comparison.md)
- [Baseline walkthrough](notebooks/01_baseline_walkthrough.ipynb)

The frozen protocol and comparable-row identity
`2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a` establish the
unchanged seven-run population. No recursion, external data, tuning, leaderboard feedback, or
paid compute was used.
