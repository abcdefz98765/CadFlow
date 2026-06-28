# FreeCAD Handoff Rules

## Overview

CadQuery generates the parametric geometry (STEP). FreeCAD is the engineering platform for:
- Opening and inspecting models
- Saving as FCStd (native FreeCAD format)
- Creating technical drawings (TechDraw)
- Performing assembly operations
- Manual modifications

## Handoff Flow

```
CadQuery → model.step → FreeCAD open → inspect → save FCStd
```

## Step Import

1. Open FreeCAD
2. File → Open → select `outputs/<part>/model.step`
3. Verify geometry in 3D view
4. Optionally: File → Save As → `model.FCStd`

## Validation in FreeCAD

When opening a STEP file:
- Check that all faces are present
- Verify hole placements
- Check chamfer/fillet geometry
- Confirm overall dimensions match specification

## Limitations (v0.1)

- No automatic FCStd generation from CLI
- No automatic TechDraw generation
- No automatic assembly
- Manual inspection required

## Future Capabilities (v0.2+)

- Automatic STEP → FCStd conversion
- Automatic three-view drawing generation
- PDF export of technical drawings
- Basic assembly with position constraints
