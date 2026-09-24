# Forecasting Global Water Storage with Geospatial Machine Learning

This project forecasts monthly global Total Water Storage (TWS): water held in groundwater,
soil, surface water, and snow. It was developed for Zindi's **A Step Ahead of Drought:
Forecasting Global Water Storage Challenge**, where masked observations turned an apparent
one-month-ahead task into a mixed one-to-seven-month forecasting problem. The repository is a
completed portfolio case study in geospatial machine learning, time-series validation, missing
observations, reproducible experimentation, and memory-aware local processing.

## Problem formulation

Each row represents a one-degree spatial grid cell and input month `t`; the target is TWS in the
next calendar month, `t+1`. Training rows provide the current TWS, coordinates, date, drought
indices, soil moisture, and the next-month target. In the test set, 186,913 of 280,961 current-TWS
values are masked.

That masking changes the practical horizon. A prediction after a recent observed TWS value is
effectively horizon 1, while consecutive masked months extend the gap to as much as horizon 7.
The implementation therefore tracks each row's last genuinely observed, same-location TWS value
and its effective horizon. It never fills a masked row with future observations or recursively
generated TWS under the selected validation policy.

TWS is relevant to drought monitoring because it summarizes water stored above and below the
land surface. This model predicts that competition target only; it is not a complete drought-risk
or impact model.

## Dataset

The supplied files contain 2,154,021 training rows and 280,961 test rows. Major fields are:

- spatial coordinates (`lat`, `lon`) and a monthly timestamp;
- current TWS, with explicit test masking;
- Standardized Precipitation-Evapotranspiration Index (SPEI) at 1, 3, 6, and 12 months;
- near-surface soil moisture;
- cyclical month encodings; and
- the next-month TWS target in training data.

The structural schema is documented in [the data dictionary](docs/data_dictionary.md). Raw data,
processed caches, predictions, submissions, and fitted models are excluded from Git. Competition
data must be obtained from the
[official competition page](https://zindi.world/competitions/one-step-ahead-of-drought-forecasting-global-water-storage-challenge)
if it remains available, and placed locally under `data/raw/`.

## Validation strategy

A random split would allow later months from the same locations to influence training and would
overstate generalization. The frozen `validation-v1` protocol instead uses two rolling-origin
folds with target-disjoint evaluation windows:

1. Fit only on targets available on or before the fold origin.
2. Transplant the complete test-set masking path to a historical period.
3. Reconstruct effective horizons 1-7 from genuinely observed TWS anchors.
4. Fit learned preprocessing inside each fold.
5. Pool squared errors across all 551,965 out-of-fold rows before taking RMSE.

The design also checks row identities, temporal cutoffs, target overlap, coverage, same-location
anchors, and mask fidelity. Metrics are reported by fold, horizon, observed versus masked state,
latitude band, and SPEI range. See the [validation protocol](docs/validation_protocol.md) and
[leakage threat register](docs/leakage_threat_register.md).

## Modelling approach

The experiment sequence moved from deterministic references to fixed learned candidates:

- global, location, seasonal, trend-seasonal, and persistence baselines;
- a fixed LightGBM benchmark using spatial, calendar, drought, soil-moisture, anchor, and horizon
  features;
- residual LightGBM models that predicted change from the last observed TWS;
- guarded horizon specialists and a cross-fitted ensemble, retained only as diagnostics when
  protection gates failed;
- seasonal-anchor, neighbouring-cell, and recency-weighted challengers; and
- one fixed CatBoost challenger with location treated categorically.

The original `lightgbm_basic` comparison remains available in
[`reports/phase2e_comparison.json`](reports/phase2e_comparison.json) and the reporting-only
[`notebooks/01_baseline_walkthrough.ipynb`](notebooks/01_baseline_walkthrough.ipynb).

The selected model, **P3-M3B**, is a 200-round LightGBM residual model. It predicts the change
from the last observed same-location TWS using 12 features: that anchor, effective horizon,
latitude, longitude, calendar month and its sine/cosine encoding, four SPEI windows, and soil
moisture. Raw year was deliberately removed after temporal drift analysis. The model used a
deterministic two-million-row training population, two CPU threads, and no tuning sweep,
recursion, or external data.

CatBoost 1.2.8 was evaluated once on the same residual formulation plus categorical location. It
used the full two-million-row population but missed the pre-registered promotion threshold and
degraded on both long horizons and the recent-period diagnostic, so it was rejected.

## Results

Lower RMSE is better. Local out-of-fold (OOF) results and public-leaderboard results use different
rows and must not be treated as the same evaluation.

| Model or diagnostic | Local pooled OOF RMSE | Public RMSE | Decision |
|---|---:|---:|---|
| Persistence | 0.673722 | 0.886420231 | Rejected diagnostic |
| Fixed LightGBM benchmark | 0.592987 | 0.778144248 | Superseded |
| P3-M3B no-year residual LightGBM | **0.583923** | **0.766408529** | **Selected reference** |
| P3-E1 guarded cross-fitted ensemble | 0.571686 | 0.878413825 | Rejected: horizon-6 gate failed |
| Phase 5 CatBoost challenger | 0.609268 | Not uploaded | Rejected: promotion gates failed |

P3-M3B's public score was 0.182486 worse than its local OOF score. That gap is reported plainly:
hidden test labels prevent a complete diagnosis, and leaderboard feedback was not used to revise
the frozen validation protocol or repair rejected models.

## Diagnostics and lessons

- Forecast error generally increased with effective horizon. For P3-M3B, horizon-1 RMSE was
  0.521314 and horizon-7 RMSE was 0.687764.
- P3-M3B scored 0.521314 on observed-input rows and 0.612931 on masked-input rows.
- The CatBoost challenger scored 0.552915 on observed rows, 0.635663 on masked rows, and
  0.668989/0.700675 at horizons 6/7.
- On the latest-12-input-month diagnostic, CatBoost scored 0.602518 versus 0.562832 for P3-M3B.
- More model complexity did not guarantee better temporal transfer: categorical location,
  neighbouring-cell features, specialist models, and an ensemble all failed at least one frozen
  promotion gate.
- Pre-registration and explicit rejection gates made it possible to retain useful negative
  evidence without promoting a model from one attractive aggregate metric.

These are modelling observations from the recorded validation design, not proven hydrological
conclusions.

## Repository structure

```text
configs/                 Frozen experiment and validation configurations
docs/                    Data, validation, leakage, and decision documentation
experiments/             Append-only experiment registry
notebooks/               Lightweight reporting notebooks
reports/                 Compact metrics, phase closeouts, and final closeout
src/drought_forecasting/ Reproducible Python implementation
tests/                   Unit and structural validation tests
references/official/     Attributed organizer materials
```

## Reproducing the project

### Install the environment

Python is constrained to 3.12 and dependencies are locked with `uv`.

```powershell
uv python install 3.12
uv sync --dev
uv run python --version
```

### Supply the excluded data

Download `Train.csv`, `Test.csv`, and `SampleSubmission.csv` from the official competition source
and place them under `data/raw/`. Their expected names, sizes, and SHA-256 identities are recorded
in `configs/data_manifest.json`. Do not commit these files.

### Run lightweight verification

```powershell
$env:PYTHONPATH = 'src'
uv run python -m drought_forecasting.experiment_registry --validate-only
uv run pytest tests/test_experiment_registry.py tests/test_phase2_notebook.py tests/test_phase5_catboost.py
uv run ruff check .
```

The bounded data preflight reads only a sample and updates its compact report:

```powershell
uv run python -m drought_forecasting.data_preflight --sample-rows 10000
```

### Analysis and modelling

The normal portfolio review path is the tracked configuration, code, notebooks, and compact
reports. Full feature materialization, OOF generation, model fitting, and submission creation are
intentionally omitted from the quick start because they consume substantially more time and
memory. Historical commands and artifact identities are preserved in
[the Phase 3 reproduction record](docs/phase3_reproduction.md).

## Technology

Python 3.12, Polars, pandas, DuckDB, PyArrow, LightGBM, CatBoost, NumPy, PyYAML, `uv`, pytest,
Ruff, and Git.

## Project status

The competition closed on 13 September 2026. This repository was closed out on **24 September
2026** and is archived as a completed portfolio case study; no further model development,
submissions, or leaderboard experiments are planned. Results reflect the recorded competition
period. See the [project closeout](reports/project_closeout.md).

## Limitations

- Public-leaderboard performance differed materially from local rolling-origin validation.
- Hidden test labels prevent complete post-competition error and drift diagnosis.
- Two validation folds provide limited temporal diversity.
- Constrained local hardware limited experiment scale and encouraged fixed, memory-aware runs.
- The selected model is a competition prototype, not a deployed drought-warning system.
- Forecasting TWS alone does not constitute a complete drought-impact assessment.

## Licensing and third-party materials

No repository-wide software license has been applied because the repository mixes original code
with organizer-provided reference material. The competition page identifies challenge data as
CC-BY-SA 4.0 and permits sharing; provenance for the two retained organizer files is recorded in
[`references/official/README.md`](references/official/README.md). No raw data is distributed here.

## Author

- **Mark Jacob Nyumba**
- Data Scientist / AI & Machine Learning Engineer
- [GitHub](https://github.com/BEMOREMJ)
