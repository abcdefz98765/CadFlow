"""One-command workflow demo for the CadFlow open-source baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_native_cad import run_workflow


def main() -> None:
    result = run_workflow(
        "Generate an 80 mm x 40 mm x 5 mm mounting plate with four M4 clearance holes.",
        output_dir="runs/mounting_plate_demo",
    )

    print(f"status: {result.status}")
    print(f"output_dir: {result.output_dir}")
    print("generated files:")
    for label, path in sorted(result.files.items()):
        print(f"  {label}: {path}")
    print(f"review path: {result.review_path}")


if __name__ == "__main__":
    main()
