"""FreeCAD Handoff — standalone script to run with FreeCAD's Python.

Usage:
    freecadcmd.exe freecad_handoff_script.py <step_path> <output_dir>

This script is self-contained (no package imports) so it can run directly
with FreeCAD's bundled Python interpreter.
"""

import json
import sys
import time
from pathlib import Path


def handoff(step_path: str, output_dir: str) -> dict:
    start = time.perf_counter()

    import FreeCAD
    import ImportGui
    import Mesh

    step_path = Path(step_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    part_name = output_dir.name

    result = {
        "status": "success",
        "step_input": str(step_path),
        "output_dir": str(output_dir),
        "files": {},
        "errors": [],
        "warnings": [],
    }

    doc = FreeCAD.newDocument("Handoff")

    # Step 1: Import STEP
    try:
        ImportGui.insert(str(step_path), doc.Name)
        doc.recompute()
        for obj in doc.Objects:
            obj.Label = part_name
        result["objects"] = [o.Label for o in doc.Objects]
    except Exception as e:
        result["errors"].append(f"STEP import: {e}")
        result["status"] = "error"
        return result

    # Step 2: Export as FCStd
    try:
        fcstd_path = output_dir / f"{part_name}.FCStd"
        doc.saveAs(str(fcstd_path))
        result["files"]["fcstd"] = str(fcstd_path)
    except Exception as e:
        result["errors"].append(f"FCStd save: {e}")

    # Step 3: Export STL (from FreeCAD)
    try:
        for obj in doc.Objects:
            if hasattr(obj, "Shape") and obj.Shape:
                stl_path = output_dir / "model_freecad.stl"
                Mesh.export([obj], str(stl_path))
                result["files"]["stl_from_freecad"] = str(stl_path)
                break
    except Exception as e:
        result["warnings"].append(f"STL export: {e}")

    # Step 4: Geometry report
    try:
        for obj in doc.Objects:
            if hasattr(obj, "Shape") and obj.Shape:
                shape = obj.Shape
                bbox = shape.BoundBox
                result["geometry"] = {
                    "bounding_box": {
                        "x": [round(bbox.XMin, 2), round(bbox.XMax, 2)],
                        "y": [round(bbox.YMin, 2), round(bbox.YMax, 2)],
                        "z": [round(bbox.ZMin, 2), round(bbox.ZMax, 2)],
                        "size_x": round(bbox.XMax - bbox.XMin, 2),
                        "size_y": round(bbox.YMax - bbox.YMin, 2),
                        "size_z": round(bbox.ZMax - bbox.ZMin, 2),
                    },
                    "volume_mm3": round(shape.Volume, 2),
                    "area_mm2": round(shape.Area, 2),
                    "solids": len(shape.Solids),
                    "faces": len(shape.Faces),
                    "edges": len(shape.Edges),
                }
                break
    except Exception as e:
        result["warnings"].append(f"Geometry report: {e}")

    result["elapsed_seconds"] = round(time.perf_counter() - start, 2)

    # Save report
    report_path = output_dir / "freecad_report.json"
    report_path.write_text(json.dumps(result, indent=2))
    result["files"]["report"] = str(report_path)

    FreeCAD.closeDocument(doc.Name)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: freecadcmd.exe freecad_handoff_script.py <step_path> <output_dir>")
        sys.exit(1)

    result = handoff(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    if result["status"] == "error":
        sys.exit(1)
