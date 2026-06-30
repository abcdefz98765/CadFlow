"""Generate the tracked IR examples through the IR-first pipeline."""

from pathlib import Path
import sys

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.cad_ir import ir_from_file
from ai_native_cad.pipeline import run_ir_pipeline


def main() -> None:
    for input_path in sorted(Path(__file__).parent.glob("*/input_ir.json")):
        result = run_ir_pipeline(ir_from_file(input_path), output_dir=input_path.parent / "outputs")
        print(f"{input_path.parent.name}: {result['status']} -> {result['output_dir']}")


if __name__ == "__main__":
    main()
