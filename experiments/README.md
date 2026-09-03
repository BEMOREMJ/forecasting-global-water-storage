# Experiment registry

`registry.csv` is the append-only index for explicitly executed experiments. It starts with
its header and no records. Use JSON text for `features`, `model_parameters`,
`rmse_by_horizon`, `regional_or_subgroup_metrics`, and `artifact_paths`.

Allowed decisions are `keep`, `reject`, `investigate`, and `superseded`. A decision records
workflow disposition, not model quality. Scores and resource measurements must remain blank
unless measured by an actual run. Artifact paths must be repository-relative and must never
point into `data/raw`.

Validate without adding a record:

```powershell
uv run python src/drought_forecasting/experiment_registry.py --validate-only
```

Adding a record requires the explicit `--record-json` option. The utility validates the
complete registry and writes atomically.

