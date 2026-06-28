# Validation Rules

## Required Checks

For every generated model, verify:

### File Existence
- `model.step` exists and size > 0
- `model.stl` exists and size > 0 (if requested)
- `report.json` exists

### Geometry Checks
- Bounding box dimensions match requested parameters (within ±0.1mm)
- Volume > 0 (model is not empty)
- Model is a valid solid

### Export Checks
- STEP file can be opened in FreeCAD
- STL file can be sliced (optional)

## Report Fields

```json
{
  "status": "success|error",
  "part_type": "...",
  "bounding_box": {"x": ..., "y": ..., "z": ...},
  "volume_mm3": ...,
  "elapsed_seconds": ...,
  "files": {"step": "...", "stl": "..."},
  "checks": [...],
  "assumptions": [...]
}
```

## Tolerance Guidelines

- Linear dimensions: ±0.1mm tolerance
- Hole positions: ±0.5mm tolerance
- Volume: must be positive
- File size: must be > 0 bytes
