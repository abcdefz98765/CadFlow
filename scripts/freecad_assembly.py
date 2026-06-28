"""FreeCAD Assembly — import multiple STEP files, apply constraints, generate BOM.

This module is designed to run inside FreeCAD's Python environment.
Usage:
    freecadcmd.exe freecad_assembly_script.py <config.json>
"""

import json
import sys
import time
from pathlib import Path


def run_assembly(config: dict) -> dict:
    """Import parts from a config and assemble them.

    Config format:
    {
        "name": "my_assembly",
        "output_dir": "outputs/my_assembly",
        "parts": [
            {
                "step": "outputs/mounting_plate/model.step",
                "name": "base_plate",
                "position": [0, 0, 0],
                "rotation": [0, 0, 0]
            },
            ...
        ]
    }
    """
    start = time.perf_counter()

    import FreeCAD
    import Part

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    project_name = config.get("name", output_dir.name)

    result = {
        "status": "success",
        "project": project_name,
        "output_dir": str(output_dir),
        "files": {},
        "parts": [],
        "bom": [],
        "errors": [],
        "warnings": [],
    }

    doc = FreeCAD.newDocument("Assembly_" + project_name)

    # ── Import each part ──
    for i, part_cfg in enumerate(config.get("parts", [])):
        step_path = Path(part_cfg["step"])
        if not step_path.exists():
            result["errors"].append(f"STEP not found: {step_path}")
            continue

        part_name = part_cfg.get("name", step_path.stem)

        try:
            shape = Part.Shape()
            shape.read(str(step_path))
            obj = doc.addObject("Part::Feature", part_name)
            obj.Label = part_name
            obj.Shape = shape
            doc.recompute()

            # Apply position
            pos = part_cfg.get("position", [0, 0, 0])
            rot = part_cfg.get("rotation", [0, 0, 0])

            if pos != [0, 0, 0]:
                obj.Placement.Base = FreeCAD.Vector(*pos)

            if rot != [0, 0, 0]:
                import math
                obj.Placement.Rotation = FreeCAD.Rotation(
                    FreeCAD.Vector(1, 0, 0), math.radians(rot[0])
                ).multiply(
                    FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), math.radians(rot[1]))
                ).multiply(
                    FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), math.radians(rot[2]))
                )

            # Record part info for BOM
            bom_entry = {
                "name": part_name,
                "step_source": str(step_path),
                "position": pos,
                "rotation": rot,
            }

            if hasattr(obj, "Shape") and obj.Shape:
                bom_entry["volume_mm3"] = round(obj.Shape.Volume, 2)
                bom_entry["area_mm2"] = round(obj.Shape.Area, 2)

            result["parts"].append(part_name)
            result["bom"].append(bom_entry)

        except Exception as e:
            result["errors"].append(f"Import failed for {part_name}: {e}")

    doc.recompute()

    # ── Export assembly FCStd ──
    try:
        fcstd_path = output_dir / f"{project_name}.FCStd"
        doc.saveAs(str(fcstd_path))
        result["files"]["fcstd"] = str(fcstd_path)
    except Exception as e:
        result["errors"].append(f"FCStd save: {e}")

    # ── Export BOM ──
    try:
        bom_csv_path = output_dir / "bom.csv"
        with open(bom_csv_path, "w") as f:
            f.write("name,step_source,position_x,position_y,position_z,volume_mm3\n")
            for entry in result["bom"]:
                pos = entry["position"]
                f.write(
                    f"{entry['name']},{entry['step_source']},"
                    f"{pos[0]},{pos[1]},{pos[2]},"
                    f"{entry.get('volume_mm3', 'N/A')}\n"
                )
        result["files"]["bom_csv"] = str(bom_csv_path)
    except Exception as e:
        result["warnings"].append(f"BOM export: {e}")

    result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    if result["errors"]:
        result["status"] = "error"
    elif result["warnings"]:
        result["status"] = "partial"

    # ── Save report ──
    report_path = output_dir / "assembly_report.json"
    result["files"]["report"] = str(report_path)
    report_path.write_text(json.dumps(result, indent=2))

    FreeCAD.closeDocument(doc.Name)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: freecadcmd.exe freecad_assembly_script.py <config.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        config = json.load(f)

    result = run_assembly(config)
    print(json.dumps(result, indent=2))
    if result["status"] == "error":
        sys.exit(1)
