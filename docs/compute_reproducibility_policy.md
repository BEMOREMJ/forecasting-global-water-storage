# Compute and reproducibility policy

The laptop and this repository are the authoritative environment. Current hardware is Windows
on AMD64 with 15.88 GiB physical RAM; Python is uv-managed CPython 3.12.14. The Intel GPU is
not a supported dependency and workloads must not rely on it.

## Data and environment

- Raw official artifacts are immutable and identified by `configs/data_manifest.json`.
- Derived Parquet caches are ignored, reproducible, and justified by verified integrity,
  2.48–22.29× storage reductions, and faster Train/Test loading and streaming queries.
- Dependencies are reproduced with `.python-version`, `pyproject.toml`, and `uv.lock`.
- Future runs must record deterministic seeds, complete configuration, data and validation
  versions, Git commit, metrics, resource measurements, and artifact paths.

## Operation-specific memory policy

Always reserve the greater of 4 GiB or 30% of physical RAM. Process datasets sequentially in
isolated, monitored children. Class A streaming integrity requires 512 MiB headroom and a
512 MiB child cap. Class B conversion/verification requires 768 MiB headroom and cap. Class C
requires `max(1 GiB, 2 × estimated dataframe size)`; Class D requires
`max(1.5 GiB, 3 × estimated dataframe size)`. Abort a stage if system availability falls below
reserve. DuckDB uses at most two threads and spills only beneath `tmp/benchmark_spill`.

| Workload | Default location | Rule |
|---|---|---|
| Hashing and streaming integrity | Laptop | Class A gate |
| Parquet conversion/verification | Laptop | Class B gate |
| Single-dataframe Polars load | Laptop | Class C gate |
| Single-dataframe pandas load | Laptop | Class D gate; safe skip allowed |
| Model training or tuning | Undecided | Phase 1 approval and rule review required |
| Free Colab fallback | Provisional | Organizer permission unresolved |
| Paid/card-required service | Prohibited | Do not use |
| AutoML | Prohibited | Do not use |

Free Colab is a provisional, free-first fallback only. Every permitted remote run must return
its configuration, logs, metrics, and artifacts to this authoritative workflow; remote work is
incomplete until that recovery is verified.

