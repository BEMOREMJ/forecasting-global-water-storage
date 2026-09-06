from pathlib import Path

import yaml


def test_frozen_schema_and_outputs_ignored():
 c=yaml.safe_load(Path("configs/phase3h_production.yaml").read_text());assert len(c["features"])==12 and "input_year" not in c["features"] and c["expected"]["test_rows"]==280961
