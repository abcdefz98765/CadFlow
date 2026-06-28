"""Spacer / Standoff — cylindrical spacer with center hole.

CadQuery example: simple cylindrical spacer/standoff.
"""

from pathlib import Path
import sys

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import cylindrical_spacer

PARAMS = {
    "part_type": "spacer",
    "unit": "mm",
    "dimensions": {
        "outer_diameter": 12.0,
        "inner_diameter": 6.5,
        "thickness": 20.0,
    },
    "features": {
        "center_hole": {
            "type": "through_hole",
            "diameter": 6.5,
            "positions": [(0, 0)],
            "depth": 20.0,
            "purpose": "concentric clearance through the spacer",
        },
    },
    "outputs": ["step", "stl"],
    "assumptions": [
        "Inner hole is concentric with outer diameter",
        "Flat ends, no chamfer or fillet",
        "All units in mm",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    return cylindrical_spacer(dims["outer_diameter"], dims["inner_diameter"], dims["thickness"])


def main():
    from ai_native_cad.runner import run_part

    params = dict(PARAMS)
    result = run_part(PARAMS["part_type"], params)

    output_dir = Path(result["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.py").write_text(Path(__file__).read_text())

    print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s -> {output_dir}")


if __name__ == "__main__":
    main()
