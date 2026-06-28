"""FreeCAD Handoff — STEP import, FCStd save, screenshot, and report.

This module is designed to run with FreeCAD's bundled Python interpreter.
Usage:
    freecadcmd.exe handoff_script.py <step_path> <output_dir>
"""

import json
import sys
import time
from pathlib import Path

from .freecad_paths import add_freecad_to_path, find_freecad_paths


def run_handoff(step_path: str | Path, output_dir: str | Path) -> dict:
    """Import a STEP file into FreeCAD, save as FCStd, capture screenshot.

    Args:
        step_path: Path to the input STEP file.
        output_dir: Directory for output files (FCStd, preview, report).

    Returns:
        A dict with handoff results and file paths.
    """
    start = time.perf_counter()

    # Ensure FreeCAD is importable
    fc_paths = find_freecad_paths()
    if fc_paths is None:
        raise RuntimeError(
            "FreeCAD not found. Install FreeCAD 1.0+ from https://www.freecad.org\n"
            "Or use the standalone script: freecadcmd.exe freecad_handoff_script.py"
        )
    add_freecad_to_path(fc_paths)

    import FreeCAD
    import ImportGui
    import Part

    step_path = Path(step_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "success",
        "step_input": str(step_path),
        "output_dir": str(output_dir),
        "files": {},
        "errors": [],
        "warnings": [],
    }

    # ── Open document ──
    doc = FreeCAD.newDocument("Handoff")
    part_name = output_dir.name

    try:
        # Import STEP
        ImportGui.insert(str(step_path), doc.Name)
        doc.recompute()

        # Rename the imported shape
        for obj in doc.Objects:
            if obj.Name != "Origin":
                obj.Label = part_name
                break

        result["objects"] = [obj.Label for obj in doc.Objects if obj.Label != "Origin"]

    except Exception as e:
        result["errors"].append(f"STEP import failed: {e}")
        result["status"] = "error"
        return result

    # ── Save FCStd ──
    fcstd_path = output_dir / f"{part_name}.FCStd"
    try:
        doc.saveAs(str(fcstd_path))
        result["files"]["fcstd"] = str(fcstd_path)
    except Exception as e:
        result["errors"].append(f"FCStd save failed: {e}")

    # ── Screenshot (GUI mode only) ──
    preview_path = output_dir / "freecad_preview.png"
    if FreeCAD.GuiUp:
        try:
            from PySide import QtGui

            FreeCAD.Gui.SendMsgToActiveView("ViewFit")
            FreeCAD.Gui.updateGui()
            mw = FreeCAD.Gui.getMainWindow()
            mdi = mw.findChild(QtGui.QMdiArea)
            if mdi:
                view = mdi.activeSubWindow()
                if view:
                    pixmap = view.grab()
                    pixmap.save(str(preview_path))
                    result["files"]["preview"] = str(preview_path)
                else:
                    result["warnings"].append("No active view for screenshot")
            else:
                result["warnings"].append("No MDI area found")
        except Exception as e:
            result["warnings"].append(f"Screenshot failed: {e}")
    else:
        result["warnings"].append("Screenshot skipped (headless mode, use freecad.exe for GUI)")

    # ── Geometry report ──
    try:
        for obj in doc.Objects:
            if hasattr(obj, "Shape") and obj.Shape:
                shape = obj.Shape
                bbox = shape.BoundBox
                result["geometry"] = {
                    "bounding_box": {
                        "x_min": round(bbox.XMin, 2),
                        "y_min": round(bbox.YMin, 2),
                        "z_min": round(bbox.ZMin, 2),
                        "x_max": round(bbox.XMax, 2),
                        "y_max": round(bbox.YMax, 2),
                        "z_max": round(bbox.ZMax, 2),
                    },
                    "volume_mm3": round(shape.Volume, 2),
                    "area_mm2": round(shape.Area, 2),
                    "solids": len(shape.Solids),
                    "faces": len(shape.Faces),
                    "edges": len(shape.Edges),
                }
                break
    except Exception as e:
        result["warnings"].append(f"Geometry report failed: {e}")

    # ── Save report ──
    result["elapsed_seconds"] = round(time.perf_counter() - start, 2)

    report_path = output_dir / "freecad_report.json"
    report_path.write_text(json.dumps(result, indent=2))
    result["files"]["report"] = str(report_path)

    # Close doc
    FreeCAD.closeDocument(doc.Name)

    return result


def handoff_cli():
    """CLI entry point for standalone execution with FreeCAD."""
    if len(sys.argv) < 3:
        print("Usage: freecadcmd.exe handoff_script.py <step_path> <output_dir>")
        sys.exit(1)

    step_path = sys.argv[1]
    output_dir = sys.argv[2]

    result = run_handoff(step_path, output_dir)
    print(json.dumps(result, indent=2))
    if result["status"] == "error":
        sys.exit(1)
