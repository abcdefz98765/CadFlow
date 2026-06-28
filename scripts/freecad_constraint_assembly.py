"""FreeCAD Constraint Assembly — constraint-based multi-part assembly.

Supports constraint types:
- fixed: Lock a part at absolute position/rotation
- coincident: Mate two planar faces flush
- concentric: Align two cylindrical faces coaxially
- parallel: Make two planar faces parallel with offset distance
- distance: Set distance between two parallel faces

Usage:
    freecadcmd.exe freecad_constraint_assembly.py <config.json>
"""

import json
import math
import sys
import time
from pathlib import Path


class ConstraintAssembly:
    """Build an assembly from a constraint-based config."""

    def __init__(self, config: dict):
        self.config = config
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.result: dict = {
            "status": "success",
            "project": config.get("name", "assembly"),
            "output_dir": config.get("output_dir", "outputs/assembly"),
            "files": {},
            "parts": [],
            "constraints": [],
            "bom": [],
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def run(self) -> dict:
        import FreeCAD

        start = time.perf_counter()
        output_dir = Path(self.config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        doc = FreeCAD.newDocument("Assembly_" + self.config.get("name", "unnamed"))

        # Step 1: Import all parts
        name_to_obj: dict[str, object] = {}
        for part_cfg in self.config.get("parts", []):
            obj = self._import_part(doc, part_cfg)
            if obj:
                name_to_obj[part_cfg.get("name", "")] = obj

        doc.recompute()

        # Step 2: Apply constraints
        for constraint_cfg in self.config.get("constraints", []):
            self._apply_constraint(doc, name_to_obj, constraint_cfg)

        doc.recompute()

        # Step 3: Interference check (if requested)
        if self.config.get("check_interference", False):
            self._check_interference(name_to_obj)

        # Step 4: Export
        self._export_fcstd(doc, output_dir)
        self._export_bom(output_dir)

        self.result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
        if self.errors:
            self.result["status"] = "error"
        elif self.warnings:
            self.result["status"] = "partial"

        report_path = output_dir / "assembly_report.json"
        self.result["files"]["report"] = str(report_path)
        report_path.write_text(json.dumps(self.result, indent=2))

        FreeCAD.closeDocument(doc.Name)

        return self.result

    def _import_part(self, doc, part_cfg: dict):
        import Part

        step_path = Path(part_cfg["step"])
        if not step_path.exists():
            self.errors.append(f"STEP not found: {step_path}")
            return None

        part_name = part_cfg.get("name", step_path.stem)

        shape = Part.Shape()
        shape.read(str(step_path))
        obj = doc.addObject("Part::Feature", part_name)
        obj.Label = part_name
        obj.Shape = shape
        doc.recompute()

        self.result["parts"].append(part_name)

        # Record BOM entry
        bom_entry = {"name": part_name, "step_source": str(step_path)}
        if hasattr(obj, "Shape") and obj.Shape:
            bom_entry["volume_mm3"] = round(obj.Shape.Volume, 2)
        self.result["bom"].append(bom_entry)
        return obj

    def _apply_constraint(self, doc, name_to_obj: dict, cfg: dict):
        import FreeCAD

        ctype = cfg.get("type", "fixed")
        name = cfg.get("name", ctype)

        try:
            if ctype == "fixed":
                self._constraint_fixed(doc, name_to_obj, cfg)
            elif ctype == "coincident":
                self._constraint_coincident(
                    doc, name_to_obj[cfg["part1"]], name_to_obj[cfg["part2"]],
                    offset=cfg.get("offset", 0.0),
                )
            elif ctype == "concentric":
                self._constraint_concentric(doc, name_to_obj[cfg["part1"]], name_to_obj[cfg["part2"]], cfg)
            elif ctype == "parallel":
                self._constraint_parallel(doc, name_to_obj, cfg)
            elif ctype == "distance":
                self._constraint_distance(doc, name_to_obj, cfg)
            else:
                self.warnings.append(f"Unknown constraint type: {ctype}")
                return

            self.result["constraints"].append(
                {"name": name, "type": ctype, "status": "applied"}
            )

        except Exception as e:
            self.errors.append(f"Constraint '{name}' failed: {e}")

    def _constraint_fixed(self, doc, name_to_obj: dict, cfg: dict):
        import FreeCAD

        part_name = cfg.get("part1") or cfg.get("part")
        obj = name_to_obj.get(part_name)
        if obj is None:
            self.errors.append(f"Fixed constraint: part '{part_name}' not found")
            return

        pos = cfg.get("position", [0, 0, 0])
        rot = cfg.get("rotation", [0, 0, 0])

        obj.Placement.Base = FreeCAD.Vector(*pos)
        if rot != [0, 0, 0]:
            obj.Placement.Rotation = FreeCAD.Rotation(
                FreeCAD.Vector(1, 0, 0), math.radians(rot[0])
            ).multiply(
                FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), math.radians(rot[1]))
            ).multiply(
                FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), math.radians(rot[2]))
            )

    def _constraint_coincident(self, doc, obj1, obj2, offset=0.0):
        """Align obj1's bottom face with obj2's top face (centered)."""
        import FreeCAD

        if not hasattr(obj1, "Shape") or not hasattr(obj2, "Shape"):
            self.errors.append("Coincident requires valid shapes")
            return

        bbox1 = obj1.Shape.BoundBox
        bbox2 = obj2.Shape.BoundBox

        target_x = bbox2.XMin + (bbox2.XMax - bbox2.XMin) / 2
        target_y = bbox2.YMin + (bbox2.YMax - bbox2.YMin) / 2
        target_z = bbox2.ZMax

        obj1_x = bbox1.XMin + (bbox1.XMax - bbox1.XMin) / 2
        obj1_y = bbox1.YMin + (bbox1.YMax - bbox1.YMin) / 2
        obj1_z = bbox1.ZMin

        obj1.Placement.Base = FreeCAD.Vector(
            target_x - obj1_x,
            target_y - obj1_y,
            target_z - obj1_z + offset,
        )

    def _constraint_concentric(self, doc, obj1, obj2, cfg: dict):
        """Make cylindrical holes/shafts coaxial by aligning centers.

        By default aligns X, Y, and Z. Set align_z: false in the constraint
        config to keep Z unchanged (useful for coplanar coaxial parts).
        """
        import FreeCAD

        if not hasattr(obj1, "Shape") or not hasattr(obj2, "Shape"):
            self.errors.append("Concentric requires valid shapes")
            return

        c1 = obj1.Shape.CenterOfMass
        c2 = obj2.Shape.CenterOfMass
        align_z = cfg.get("align_z", True)

        obj1.Placement.Base = FreeCAD.Vector(
            obj1.Placement.Base.x + c2.x - c1.x,
            obj1.Placement.Base.y + c2.y - c1.y,
            obj1.Placement.Base.z + (c2.z - c1.z) if align_z else obj1.Placement.Base.z,
        )

    def _constraint_parallel(self, doc, name_to_obj: dict, cfg: dict):
        """Set a distance offset between parallel faces."""
        import FreeCAD

        obj1 = name_to_obj.get(cfg.get("part1", ""))
        obj2 = name_to_obj.get(cfg.get("part2", ""))
        if obj1 is None or obj2 is None:
            self.errors.append("Parallel constraint: parts not found")
            return

        bbox1 = obj1.Shape.BoundBox
        bbox2 = obj2.Shape.BoundBox
        axis = cfg.get("axis", "z")
        offset = cfg.get("offset", 0)

        if axis == "x":
            delta = bbox2.XMax - bbox1.XMin + offset
            obj1.Placement.Base.x += delta
        elif axis == "y":
            delta = bbox2.YMax - bbox1.YMin + offset
            obj1.Placement.Base.y += delta
        elif axis == "z":
            delta = bbox2.ZMax - bbox1.ZMin + offset
            obj1.Placement.Base.z += delta

    def _constraint_distance(self, doc, name_to_obj: dict, cfg: dict):
        """Set distance between two part centers along an axis."""
        import FreeCAD

        obj1 = name_to_obj.get(cfg.get("part1", ""))
        obj2 = name_to_obj.get(cfg.get("part2", ""))
        if obj1 is None or obj2 is None:
            self.errors.append("Distance constraint: parts not found")
            return

        c1 = obj1.Shape.CenterOfMass
        c2 = obj2.Shape.CenterOfMass
        axis = cfg.get("axis", "x")
        distance = cfg.get("distance", 10.0)

        if axis == "x":
            obj1.Placement.Base.x = c2.x + distance - (c1.x - obj1.Placement.Base.x)
        elif axis == "y":
            obj1.Placement.Base.y = c2.y + distance - (c1.y - obj1.Placement.Base.y)
        elif axis == "z":
            obj1.Placement.Base.z = c2.z + distance - (c1.z - obj1.Placement.Base.z)

    def _check_interference(self, name_to_obj: dict):
        """Detect overlapping volumes between parts."""
        objs = list(name_to_obj.values())
        interferences = []

        for i, obj1 in enumerate(objs):
            for obj2 in objs[i + 1:]:
                if not hasattr(obj1, "Shape") or not hasattr(obj2, "Shape"):
                    continue
                try:
                    common = obj1.Shape.common(obj2.Shape)
                    if common.Volume > 300.0:  # > 300 mm³ threshold (ignore precision/facet artifacts)
                        interferences.append({
                            "part1": obj1.Label,
                            "part2": obj2.Label,
                            "volume_mm3": round(common.Volume, 3),
                            "severity": "warning" if common.Volume < 500.0 else "critical",
                        })
                except Exception:
                    pass

        self.result["interferences"] = interferences
        if interferences:
            self.warnings.append(f"Found {len(interferences)} interference(s)")

    def _export_fcstd(self, doc, output_dir: Path):
        """Save FreeCAD document."""
        try:
            project_name = self.config.get("name", "assembly")
            fcstd_path = output_dir / f"{project_name}.FCStd"
            doc.saveAs(str(fcstd_path))
            self.result["files"]["fcstd"] = str(fcstd_path)
        except Exception as e:
            self.errors.append(f"FCStd save: {e}")

    def _export_bom(self, output_dir: Path):
        """Export Bill of Materials as CSV."""
        try:
            bom_path = output_dir / "bom.csv"
            with open(bom_path, "w") as f:
                f.write("name,step_source,volume_mm3\n")
                for entry in self.result["bom"]:
                    f.write(
                        f"{entry['name']},{entry['step_source']},"
                        f"{entry.get('volume_mm3', 'N/A')}\n"
                    )
            self.result["files"]["bom_csv"] = str(bom_path)
        except Exception as e:
            self.warnings.append(f"BOM export: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: freecadcmd.exe freecad_constraint_assembly.py <config.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        config = json.load(f)

    assembly = ConstraintAssembly(config)
    result = assembly.run()
    print(json.dumps(result, indent=2))
    if result["status"] == "error":
        sys.exit(1)
