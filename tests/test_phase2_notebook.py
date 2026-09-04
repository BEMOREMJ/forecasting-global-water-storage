"""Focused Phase 2F checks for the lightweight educational notebook."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/01_baseline_walkthrough.ipynb"
STARTER_BLOB = "4cd7b8ec4a6a819011a9cd807f6cc107925783fb"

def notebook() -> dict:
    value = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert value["nbformat"] == 4 and value["nbformat_minor"] >= 5
    return value

def test_structure_and_required_sections() -> None:
    value = notebook(); assert len(value["cells"]) >= 12
    markdown = "\n".join("".join(c["source"]) for c in value["cells"] if c["cell_type"] == "markdown")
    for phrase in ("Forecasting problem", "Frozen validation", "prediction contract", "Deterministic baselines", "Fold and horizon", "deterministic sampling", "gradient-boosted", "Decision, limitations", "reproduction commands"):
        assert phrase.lower() in markdown.lower()

def test_no_pipeline_or_large_data_operations() -> None:
    code = "\n".join("".join(c["source"]) for c in notebook()["cells"] if c["cell_type"] == "code")
    assert not any(x in code for x in ("import lightgbm", ".fit(", ".predict(", "read_parquet", "data/raw", "data/processed", "artifacts/", "transplant_single_fold", "run_baseline"))
    assert "reports/phase2e_comparison.json" in code and "experiments/registry.csv" in code

def test_paths_and_reproduction_modules_exist() -> None:
    text = "\n".join("".join(c["source"]) for c in notebook()["cells"])
    for path in ("reports/phase2e_comparison.json", "reports/phase2c_horizon_examples_manifest.json", "experiments/registry.csv"):
        assert (ROOT / path).is_file()
    for module in ("deterministic_baselines", "horizon_examples", "lightgbm_benchmark", "phase2_comparison"):
        assert f"drought_forecasting.{module}" in text
        assert (ROOT / f"src/drought_forecasting/{module}.py").is_file()

def test_controlled_code_execution_loads_accepted_results() -> None:
    namespace = {"__name__": "__phase2f_validation__"}; previous = Path.cwd()
    try:
        os.chdir(ROOT / "notebooks")
        for cell in notebook()["cells"]:
            if cell["cell_type"] == "code":
                exec(  # noqa: S102 - executing the trusted local notebook is the test objective
                    compile("".join(cell["source"]), str(NOTEBOOK), "exec"), namespace
                )
    finally: os.chdir(previous)
    assert len(namespace["registry"]) == len(namespace["ranked_comparison"]) == 7
    assert namespace["comparison"]["preferred"]["model"] == "lightgbm_basic"
    assert namespace["comparison"]["runs"][0]["pooled_rmse"] == 0.5929872454156464

def test_living_documents_reference_phase2() -> None:
    expected = {"README.md":("01_baseline_walkthrough.ipynb","phase2e_comparison.json","lightgbm_basic"),"docs/competition_evidence_matrix.md":("prediction contract","2,000,000","seven records"),"reports/final_report_outline.md":("0.592987","0.673722","Phase 3 hypotheses")}
    for path, phrases in expected.items():
        text=(ROOT/path).read_text(encoding="utf-8").lower(); assert all(p.lower() in text for p in phrases)

def test_starter_git_identity_unchanged() -> None:
    result=subprocess.run(["git","hash-object","--","references/official/StarterNotebook.ipynb"],cwd=ROOT,check=True,capture_output=True,text=True)
    assert result.stdout.strip() == STARTER_BLOB
