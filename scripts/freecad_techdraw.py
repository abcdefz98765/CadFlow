"""FreeCAD TechDraw — generate three-view drawing, isometric view, and PDF.

This module is designed to run inside FreeCAD's Python environment.
Usage:
    freecadcmd.exe freecad_techdraw_script.py <step_path> <output_dir>
"""

import json
import sys
import time
from pathlib import Path


def generate_techdraw(step_path: str | Path, output_dir: str | Path) -> dict:
    """Generate a tech drawing from a STEP file.

    Creates a FreeCAD TechDraw page with:
    - Front view (XY projection)
    - Top view (XZ projection)
    - Right view (YZ projection)
    - Isometric view
    - Key dimensions (bounding box)
    - PDF export
    """
    start = time.perf_counter()

    import FreeCAD
    import ImportGui
    import Part
    import TechDraw

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

    # ── Load model ──
    doc = FreeCAD.newDocument("TechDraw_" + part_name)
    try:
        ImportGui.insert(str(step_path), doc.Name)
        doc.recompute()
    except Exception as e:
        result["errors"].append(f"STEP import failed: {e}")
        result["status"] = "error"
        return result

    # Find the imported part
    part_obj = None
    for obj in doc.Objects:
        if hasattr(obj, "Shape") and obj.Shape:
            part_obj = obj
            obj.Label = part_name
            break

    if part_obj is None:
        result["errors"].append("No valid shape found in STEP file")
        result["status"] = "error"
        return result

    # ── Create TechDraw page ──
    try:
        page = doc.addObject("TechDraw::DrawPage", "Page")
        page.Template = TechDraw.TemplateHelper.getDefaultTemplate()

        template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = TechDraw.TemplateHelper.getDefaultTemplate()
        page.Template = template

        doc.recompute()

        # Standard views
        views = [
            ("Front", "Front"),    # XY
            ("Top", "Top"),        # XZ
            ("Right", "Right"),    # YZ
            ("Iso", "Front"),      # Isometric
        ]

        view_objects = []

        # ── Front view ──
        front = doc.addObject("TechDraw::DrawViewPart", "ViewFront")
        front.Source = [part_obj]
        front.Direction = FreeCAD.Vector(0, -1, 0)
        front.XDirection = FreeCAD.Vector(1, 0, 0)
        front.X = 70
        front.Y = 120
        front.Scale = 1.0
        page.addView(front)
        view_objects.append(front)

        # ── Top view ──
        top = doc.addObject("TechDraw::DrawViewPart", "ViewTop")
        top.Source = [part_obj]
        top.Direction = FreeCAD.Vector(0, 0, 1)
        top.XDirection = FreeCAD.Vector(1, 0, 0)
        top.X = 70
        top.Y = 60
        top.Scale = 1.0
        page.addView(top)
        view_objects.append(top)

        # ── Right view ──
        right = doc.addObject("TechDraw::DrawViewPart", "ViewRight")
        right.Source = [part_obj]
        right.Direction = FreeCAD.Vector(1, 0, 0)
        right.XDirection = FreeCAD.Vector(0, 0, 1)
        right.X = 180
        right.Y = 120
        right.Scale = 1.0
        page.addView(right)
        view_objects.append(right)

        # ── Isometric view ──
        iso = doc.addObject("TechDraw::DrawViewPart", "ViewIso")
        iso.Source = [part_obj]
        iso.Direction = FreeCAD.Vector(1, -1, 1)
        iso.XDirection = FreeCAD.Vector(1, 1, 0)
        iso.X = 180
        iso.Y = 60
        iso.Scale = 1.0
        page.addView(iso)
        view_objects.append(iso)

        doc.recompute()

        # ── Add bounding box dimensions to front view ──
        bbox = part_obj.Shape.BoundBox
        dims_added = 0

        # Horizontal dimension
        try:
            x_dim = doc.addObject("TechDraw::DrawViewDimension", "DimX")
            x_dim.Type = "Distance"
            x_dim.MeasureType = "Horizontal"
            x_dim.References2D = [(front, "Vertex1"), (front, "Vertex2")]
            x_dim.X = 70
            x_dim.Y = 180
            dims_added += 1
        except Exception:
            result["warnings"].append("Could not add horizontal dimension")

        # Vertical dimension
        try:
            y_dim = doc.addObject("TechDraw::DrawViewDimension", "DimY")
            y_dim.Type = "Distance"
            y_dim.MeasureType = "Vertical"
            y_dim.References2D = [(front, "Vertex1"), (front, "Vertex3")]
            y_dim.X = 20
            y_dim.Y = 120
            dims_added += 1
        except Exception:
            result["warnings"].append("Could not add vertical dimension")

        doc.recompute()

        # ── Export PDF ──
        pdf_path = output_dir / f"{part_name}_drawing.pdf"
        page.exportPageAsPDF(str(pdf_path))
        result["files"]["pdf"] = str(pdf_path)

        # ── Export as SVG too ──
        svg_path = output_dir / f"{part_name}_drawing.svg"
        page.exportPageAsSVG(str(svg_path))
        result["files"]["svg"] = str(svg_path)

        result["views"] = ["Front", "Top", "Right", "Isometric"]
        result["dimensions_added"] = dims_added
        result["geometry"] = {
            "size_x": round(bbox.XMax - bbox.XMin, 2),
            "size_y": round(bbox.YMax - bbox.YMin, 2),
            "size_z": round(bbox.ZMax - bbox.ZMin, 2),
        }

    except Exception as e:
        result["errors"].append(f"TechDraw failed: {e}")
        result["status"] = "error"

    # ── Save FCStd ──
    try:
        fcstd_path = output_dir / f"{part_name}_techdraw.FCStd"
        doc.saveAs(str(fcstd_path))
        result["files"]["fcstd"] = str(fcstd_path)
    except Exception as e:
        result["warnings"].append(f"FCStd save: {e}")

    result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    report_path = output_dir / "techdraw_report.json"
    report_path.write_text(json.dumps(result, indent=2))
    result["files"]["report"] = str(report_path)

    FreeCAD.closeDocument(doc.Name)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: freecadcmd.exe freecad_techdraw_script.py <step_path> <output_dir>")
        sys.exit(1)

    result = generate_techdraw(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    if result["status"] == "error":
        sys.exit(1)
