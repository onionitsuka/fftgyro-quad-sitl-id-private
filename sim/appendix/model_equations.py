"""Export the appendix load equations and apply a local CSV of model terms."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

DEFAULT_CONFIG = Path(__file__).with_name("model.json")
AXES = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")
COLUMNS = ("route", "output", "term", "coefficient")


def load_config(path: Path, terms: Path | None = None) -> tuple[dict, str]:
    """Return the effective configuration and a digest of the model loaded."""
    source = path.read_bytes()
    config = json.loads(source.decode("utf-8-sig"))
    if terms is None:
        return config, hashlib.sha256(source).hexdigest()

    table_bytes = terms.read_bytes()
    table = csv.DictReader(io.StringIO(table_bytes.decode("utf-8-sig"), newline=""))
    if tuple(table.fieldnames or ()) != COLUMNS:
        raise ValueError(f"{terms.name}: expected columns {', '.join(COLUMNS)}")
    groups = {(route, axis): {} for route in config["models"] for axis in AXES}
    for row in table:
        route, axis, term, value = (row[column] for column in COLUMNS)
        location = f"{terms.name}:{table.line_num}"
        if (route, axis) not in groups:
            raise ValueError(f"{location}: unknown route or output: {route}, {axis}")
        if None in row or not term or not re.fullmatch(r"[A-Za-z0-9_*^]+", term):
            raise ValueError(f"{location}: expected a feature name, such as mu_x*mu_z")
        values = groups[route, axis]
        if term in values:
            raise ValueError(f"{location}: duplicate term {term}")
        try:
            coefficient = float(value)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{location}: coefficient must be a number") from error
        if not math.isfinite(coefficient):
            raise ValueError(f"{location}: coefficient must be finite")
        values[term] = coefficient
    for (route, axis), values in groups.items():
        if not values:
            raise ValueError(f"{terms.name}: {route}/{axis} has no terms; retain one zero coefficient if needed")
        model = config["models"][route][axis]
        model.update(feature_names=list(values), coefficient_by_name=values)
    config["term_overrides"] = {
        "base_config_sha256": hashlib.sha256(source).hexdigest(),
        "terms_csv_sha256": hashlib.sha256(table_bytes).hexdigest(),
    }
    digest = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return config, digest


def feature_formula(term: str, axis: str) -> str:
    """Expand the features used by the shipped model in common notation."""
    scale = "S_F" if axis.startswith("F") else "S_M"
    if term == "intercept":
        return "1"
    if term == "prop_gain":
        return f"{axis}_base"
    if term.startswith("rotor_inplane_"):
        component = axis[-1]
        factor = " * mu_h[i]" if term.endswith("quadratic") else ""
        return f"-S_F * mean_i(w[i] * mu_{component}[i]{factor})"
    if match := re.fullmatch(r"rotor([1-4])_torque", term):
        i = match[1]
        return f"s[{i}] * rho * pi * R^5 * Omega[{i}]^2"
    if match := re.fullmatch(r"flow_(\d)(\d)(\d)(?:_([ru]))?", term):
        factors = [f"mu_{key}^{power}" for key, power in zip("xyz", match.groups()[:3]) if power != "0"]
        suffix = {"r": "rbar", "u": "ur"}.get(match[4])
        return " * ".join([scale, *factors, *([suffix] if suffix else [])])
    if match := re.fullmatch(r"body_h(\d)_(sin|cos)", term):
        return f"S_M * mu_h2 * {match[2]}({match[1]} * alpha)"
    if match := re.fullmatch(r"local([1-3])_(.+)", term):
        return f"S_M * (1 - sun_low) * B[{match[1]}](sin(beta)^2) * {match[2]}"
    if term.startswith("speed_dev__"):
        variables = re.findall(r"mu_[xyz]|abs_mu_y|qbar|rbar|ur|local_yaw_linear|local_yaw_axial", term[11:])
        if "_".join(variables) == term[11:]:
            return " * ".join([scale, "delta_s", *variables])
    if term in {"speed_mu_y", "speed_ur", "speed_rbar", "speed_local_yaw_axial"}:
        return f"{scale} * delta_s * {term.removeprefix('speed_')}"
    if term == "1":
        return scale
    # Plain monomials are pressure-scaled. Other evaluator families remain
    # named explicitly so an edited export never shows an invented expansion.
    plain = term.removeprefix("cross__")
    variable = r"(?:abs_)?(?:mu_[xyz]|[pqr]bar|u[pqr]|mu_h2|mu_total2|inflow_delta|ur_absur)"
    factor = rf"(?:1|{variable}(?:\^\d+)?)"
    if re.fullmatch(rf"{factor}(?:\*{factor})*", plain):
        return f"{scale} * {plain}"
    return f"selected_features[{axis}, {term}]"


def render_equations(config: dict) -> str:
    lines = [
        "# 付録Cの荷重モデルの式", "",
        f"モデル ID: `{config['id']}`。",
        "符号は機体FRD（前・右・下）。力は N、モーメントは N·m。", "",
        "既存モデルは推進荷重のみ。同定モデルは推進荷重に各表の行の積の和を加える。"
        "基準式と変数定義は配布版の `docs/model-equations.md` を参照。", "",
        f"- 既定の学習経路: `{config['default_route']}`",
        f"- 風速の適用上限: {config['airspeed_limit_m_s']} m/s",
        f"- Pitch補正からRollへ転用: `{str(config.get('roll_transfer', False)).lower()}`",
    ]
    if config.get("roll_transfer"):
        lines.extend(["", "実行時のMx補正は、±90°変換したMy補正の差の半分。表のMxは保存済みの直接補正。"])
    if "term_overrides" in config:
        lines.extend(["", "編集したCSVの係数を使用。配布時の同定結果から変わります。"])
    lines.extend(["", "## 既存モデルの定数", "", "| 定数 | 値 | 単位 |", "| --- | ---: | --- |"])
    for key, unit in (("kf", "N/(rad/s)^2"), ("kq", "N·m/(rad/s)^2"),
                      ("arm_xy_m", "m"), ("rotor_radius_m", "m"), ("rho", "kg/m³"),
                      ("rotor_inertia_kg_m2", "kg·m²"), ("cg_flu_m", "m (FLU)"),
                      ("propulsion_reference_cg_flu_m", "m (FLU)")):
        lines.append(f"| `{key}` | {config['settings'][key]} | {unit} |")
    lines.extend(["", "## 指令・電圧から回転数", "",
                  "| モーター | RPMの式（`v = V/16`、`d = max(指令, 0)`） | 遅れ [s] | 時定数 上昇 / 下降 [s] |",
                  "| --- | --- | ---: | ---: |"])
    for number, motor in enumerate(config["motor_models"], 1):
        if motor.get("kind") == "kaufmann2023":
            factors = ("1", "v", "sqrt(d)", "d", "v*sqrt(d)")
            rpm = " + ".join(f"({value!r})*{factor}" for value, factor in zip(motor["coefficients"], factors, strict=True))
        else:
            factors = ("d", "sqrt(d)", "d^2")
            inner = " + ".join(f"({value!r})*{factor}" for value, factor in zip(motor["map_coefficients"], factors, strict=True))
            rpm = f"v^{motor.get('voltage_exponent', 1.)} * ({inner})"
        lines.append(f"| {number} | `{rpm}` | {motor['delay_s']} | {motor['tau_up_s']} / {motor['tau_down_s']} |")

    for route, models in config["models"].items():
        lines.extend(["", f"## {route}"])
        for axis in AXES:
            model = models[axis]
            lines.extend(["", f"### {axis}", "", "| 項 | 係数 | 係数を掛ける量 |", "| --- | ---: | --- |"])
            for term, coefficient in model["coefficient_by_name"].items():
                formula = feature_formula(term, axis)
                lines.append(f"| `{term}` | {coefficient!r} | `{formula}` |")
    return "\n".join(lines) + "\n"


def export_equations(config: dict, output: Path) -> None:
    equations = render_equations(config)
    output.mkdir(parents=True, exist_ok=False)
    (output / "equations.md").write_text(equations, encoding="utf-8")
    # BOM lets common spreadsheet apps open the CSV as UTF-8.
    with (output / "terms.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(COLUMNS)
        for route, models in config["models"].items():
            for axis in AXES:
                for term, coefficient in models[axis]["coefficient_by_name"].items():
                    writer.writerow((route, axis, term, coefficient))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--terms", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        config, _ = load_config(args.config, args.terms)
        export_equations(config, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    for name in ("equations.md", "terms.csv"):
        print(args.output / name)


if __name__ == "__main__":
    main()
