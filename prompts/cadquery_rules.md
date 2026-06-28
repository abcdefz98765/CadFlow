# CadQuery Coding Rules

## Best Practices

### Workplanes
- Default to "XY" plane for base features
- Use face selectors (">Z", "<Z", ">X", etc.) for face operations
- Chain `.workplane()` after `.faces()` for face operations

### Feature Creation
- Use `cq.Workplane("XY").box(l, w, h)` for rectangular solids
- Use `.circle(r).extrude(h)` for cylindrical features
- Use `.hole(d, depth)` for through/blind holes
- Use `.pushPoints([...])` for multi-position operations

### Boolean Operations
- Prefer `.cut()` for subtractive features
- Use `.union()` for additive features
- Avoid complex boolean chains

### Fillets and Chamfers
- Apply chamfers with `.chamfer(size)`
- Apply fillets with `.fillet(radius)`
- Apply to edges, not faces
- Handle fillet failures gracefully (they can fail on complex geometry)

### Common Patterns

**Rectangular plate with holes:**
```python
plate = cq.Workplane("XY").box(length, width, thickness)
plate = (
    plate.faces(">Z").workplane()
    .pushPoints([(x1,y1), (x2,y2), ...])
    .hole(d, depth)
)
```

**Cylindrical spacer:**
```python
outer = cq.Workplane("XY").circle(outer_r).extrude(thickness)
inner = cq.Workplane("XY").circle(inner_r).extrude(thickness)
spacer = outer.cut(inner)
```

## Anti-Patterns

- Do NOT hardcode magic numbers inside modeling logic
- Do NOT use global variables for geometry
- Do NOT export STL without STEP
- Do NOT create non-manifold geometry
