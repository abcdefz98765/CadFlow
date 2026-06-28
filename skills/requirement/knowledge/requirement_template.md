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
