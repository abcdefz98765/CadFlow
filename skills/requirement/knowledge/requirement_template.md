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
  "follow_up_requests": [],
  "cad_brief": {
    "part_type": "mounting_plate",
    "intent": {},
    "coordinate_convention": {},
    "dimension_fields": [],
    "feature_fields": [],
    "validation_targets": [],
    "assumption_policy": {},
    "clarification_summary": {}
  },
  "assumptions": [],
  "requirement_status": {
    "complete_for_generation": true,
    "needs_user_input": false,
    "blocking_fields": [],
    "missing_count": 0,
    "follow_up_count": 0,
    "blocking_count": 0,
    "missing_fields": [],
    "non_blocking_fields": []
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

`follow_up_questions` remains a compatibility list of question strings.
`follow_up_requests` is the machine-readable form and must include field,
category, code, question, severity, reason, and source.

`cad_brief` is a lightweight requirement/planning summary. It must be derived
from requirement fields and CAD IR fields, and it must not replace CAD IR or
drive backend-specific code generation. Conservative validation targets may
include bounding dimensions and requested hole count or diameter when those
values are already represented in the parsed requirement.
