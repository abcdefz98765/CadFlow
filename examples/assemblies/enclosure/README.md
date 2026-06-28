# v0.3 Assembly Demo

This demo shows the intended workflow: generate CadQuery parts first, run assembly self-checks, then hand STEP files to FreeCAD assembly scripts.

## 1. Generate Part STEP Files

Run these commands from the repository root:

```bash
python examples/assemblies/enclosure/parts/enclosure_base/model.py
python examples/assemblies/enclosure/parts/enclosure_lid/model.py
python examples/assemblies/enclosure/parts/spacer/model.py
python examples/assemblies/enclosure/parts/wall_bracket/model.py
```

Expected inputs for the assembly stage:

```text
examples/assemblies/enclosure/parts/enclosure_base/model.step
examples/assemblies/enclosure/parts/enclosure_lid/model.step
examples/assemblies/enclosure/parts/spacer/model.step
examples/assemblies/enclosure/parts/wall_bracket_left/model.step
examples/assemblies/enclosure/parts/wall_bracket_right/model.step
```

## 2. Run Assembly Self-Check

Run this before FreeCAD export:

```bash
python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json
```

Expected output:

```text
examples/assemblies/enclosure/assembly_validation.json
examples/assemblies/enclosure/assembly_validation.md
```

Fix all `error` entries before treating the FreeCAD assembly as valid.

## 3. Run Basic Assembly

Use absolute positions and rotations:

Windows:

```bash
%FREECAD_HOME%\bin\FreeCADCmd.exe -c "import sys; sys.argv=['scripts/freecad_assembly.py','examples\\assemblies\\enclosure\\assembly.json']; exec(open('scripts/freecad_assembly.py', encoding='utf-8').read())"
```

Linux/macOS:

```bash
freecadcmd scripts/freecad_assembly.py examples/assemblies/enclosure/assembly.json
```

Expected output:

```text
examples/assemblies/enclosure/enclosure_assembly.FCStd
examples/assemblies/enclosure/bom.csv
examples/assemblies/enclosure/assembly_report.json
```

## 4. Run Constraint Assembly

Use fixed/coincident constraints as a lightweight placement layer:

Windows:

```bash
%FREECAD_HOME%\bin\FreeCADCmd.exe -c "import sys; sys.argv=['scripts/freecad_constraint_assembly.py','examples\\assemblies\\enclosure\\constraint_assembly.json']; exec(open('scripts/freecad_constraint_assembly.py', encoding='utf-8').read())"
```

Linux/macOS:

```bash
freecadcmd scripts/freecad_constraint_assembly.py examples/assemblies/enclosure/constraint_assembly.json
```

Expected output:

```text
examples/assemblies/enclosure/constraint_assembly/enclosure_constraint_assembly.FCStd
examples/assemblies/enclosure/constraint_assembly/bom.csv
examples/assemblies/enclosure/constraint_assembly/assembly_report.json
```

## 5. Open The Assembly

Open this file in FreeCAD:

```text
examples/assemblies/enclosure/constraint_assembly/enclosure_constraint_assembly.FCStd
```

Inspect the model tree for `enclosure_base`, `enclosure_lid`, `spacer_*`, and `wall_bracket_*`.

## Agent Notes

- Always verify every `parts[].step` path exists before running FreeCAD.
- Run `python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json` before FreeCAD export.
- Keep part origins consistent. For stacked parts, prefer bottom face at `Z=0`.
- Use `validation.required_contacts` for expected support/mating relationships, and include `intent`.
- Use `validation.allowed_bbox_overlaps` only when bbox overlap is expected, such as cavity/container or wall-mount cases, and include `reason`.
- Use `validation.allowed_close_clearances` only for deliberate tolerance gaps, and include `reason`.
- Treat FreeCAD boolean interference as a secondary diagnostic, not the primary repair loop.
