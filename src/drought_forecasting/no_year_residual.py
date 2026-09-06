"""P3-M3B: controlled P3-M1 residual benchmark with only raw year removed."""

from pathlib import Path

from drought_forecasting.residual_benchmark import run


def main() -> int:
    result = run(Path("configs/phase3m3b_no_year_residual.yaml"))
    print(result["metrics"]["pooled"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
