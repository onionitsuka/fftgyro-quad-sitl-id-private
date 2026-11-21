import csv
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_equations import DEFAULT_CONFIG, export_equations, load_config, render_equations
from simulate import Loads, validate_edited_terms


def test_distributed_equations_match_model_and_csv_round_trips(tmp_path):
    config, _ = load_config(DEFAULT_CONFIG)
    docs = DEFAULT_CONFIG.parents[2] / "docs"
    assert (docs / "equations.md").read_text(encoding="utf-8") == render_equations(config)
    assert "selected_features[" not in render_equations(config)
    output = tmp_path / "export"
    export_equations(config, output)
    assert (docs / "model-terms.csv").read_text(encoding="utf-8") == (output / "terms.csv").read_text(encoding="utf-8")
    restored, _ = load_config(DEFAULT_CONFIG, output / "terms.csv")
    assert restored["models"] == config["models"]


def test_editing_csv_changes_only_the_selected_load(tmp_path):
    config, original_hash = load_config(DEFAULT_CONFIG)
    export_equations(config, tmp_path / "export")
    table = tmp_path / "export" / "terms.csv"
    with table.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns, rows = reader.fieldnames, list(reader)
    row = next(r for r in rows if (r["route"], r["output"], r["term"]) ==
               ("command_route", "Fx", "intercept"))
    row["coefficient"] = str(float(row["coefficient"]) + 0.01)
    with table.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    edited, edited_hash = load_config(DEFAULT_CONFIG, table)
    validate_edited_terms(edited)
    assert edited_hash != original_hash
    state = (np.zeros(3), np.zeros(3), np.full(4, 400.), np.zeros(4))
    np.testing.assert_allclose(
        Loads(edited, True, "command_route")(*state) - Loads(config, True, "command_route")(*state),
        [0.01, 0, 0, 0, 0, 0], atol=1e-12)
    np.testing.assert_array_equal(Loads(edited, True, "measured")(*state), Loads(config, True, "measured")(*state))
    np.testing.assert_array_equal(Loads(edited, False)(*state), Loads(config, False)(*state))


def test_unknown_term_has_route_and_output_in_error(tmp_path):
    config, _ = load_config(DEFAULT_CONFIG)
    export_equations(config, tmp_path / "export")
    table = tmp_path / "export" / "terms.csv"
    table.write_text(table.read_text(encoding="utf-8").replace("prop_gain", "not_a_feature"), encoding="utf-8")
    edited, _ = load_config(DEFAULT_CONFIG, table)
    with pytest.raises(ValueError, match=r"Invalid term in measured/Fz:.*not_a_feature"):
        validate_edited_terms(edited)
