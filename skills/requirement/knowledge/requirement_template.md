# Requirement Template

Minimum structure for `requirement.json`:

```json
{
  "part_type": "mounting_plate",
  "unit": "mm",
  "intent": {
    "object_goal": "mounting_plate",
    "scope": "part",
    "use_case": "mounting"
  },
  "dimensions": {},
  "features": {},
  "outputs": ["step", "stl"],
  "check_level": "L0",
  "field_policy": {},
  "missing_information": [],
  "follow_up_questions": [],
  "assumptions": [],
  "requirement_status": {
    "complete_for_generation": true,
    "needs_user_input": false,
    "blocking_fields": []
  }
}
```

## Field Groups

- Intent: what the user is trying to make and whether it is a part, assembly, or assembly-owned part.
- Primary dimensions: dimensions that determine scale, fit, or topology.
- Functional features: holes, pockets, caps, wire exits, fastener interfaces, switch/sensor envelopes, and other design-driving features.
- Manufacturing context: process, material family, printability, machining, or sheet/laser constraints.
- Engineering constraints: tolerances, surface finish by functional face, loads, environment, inspection, and standards.

## Phase 2 Deterministic Parser Coverage

The natural-language parser may fill CAD IR fields only through conservative
rules. It currently extracts:

- mounting plate length/width/thickness and simple hole specs, including four
  corner M-size holes
- spacer or washer outer diameter, inner diameter, and thickness
- simple L-bracket base length, base width, height, thickness, and basic holes
- enclosure base outer length, outer width, outer height, wall thickness, and
  requested STEP/STL outputs

Unsupported or incomplete fields must remain explicit in `missing_information`.
L0 may keep template defaults for exploratory generation, but the parser must
record which dimensions were extracted from text and which were not.

Parser diagnostics must record high-risk ambiguity, such as unsupported inch
units or conflicting dimension statements. These diagnostics should become
missing information instead of silently changing CAD IR values.
