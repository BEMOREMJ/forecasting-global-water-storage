# Drought Forecasting: Global Water Storage Challenge

This private, non-publishable working repository supports the Zindi **A Step Ahead of
Drought: Forecasting Global Water Storage Challenge**. The task is to predict next-month
Total Water Storage (TWS) globally. Masked test `TWS_t` values create effective forecast
horizons of approximately 1–7 months.

## Status

Phase 1 is closed and leakage-safe `validation-v1` is frozen. Phase 2 modelling may proceed
under the observed-only, recursion-disabled policy; no modelling has started yet.

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

Jupyter, LightGBM, CatBoost, SHAP, GeoPandas, and other modelling or geospatial packages are
planned Phase 1 candidates only after their necessity, rule compliance, and compatibility
are confirmed.

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

The frozen protocol and compact audit manifest establish the Phase 2 evaluation boundary; no
model training or scoring has started.
