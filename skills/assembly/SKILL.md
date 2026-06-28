# Assembly Skill

Purpose: define assembly structure, placements, constraints, and validation
rules.

Assembly-owned rules belong here, including mating faces, clearances, fastener
alignment, stack-up, wire exits, and access for sensors or switches.

## Inputs

- `requirement.json`
- part-level `part_spec.json` or equivalent part metadata
- generated part reports with bbox, status, and validation summary

## Outputs

- `assembly_plan.json`
- `assembly_plan.md`
- backend-neutral `assembly.json`
- backend-neutral `constraint_assembly.json`
- `assembly_review.md`

## Confirmation Gate

Pause only for high-risk topology decisions. Examples:

- unknown switch, sensor, or electronics envelope
- unknown wire exit direction or bend/service clearance
- unknown fastening method when it changes part interfaces
- unknown serviceability requirement for removable vs sealed assemblies

For L0 visual work, non-topology assumptions may continue, but must be written
into the plan and review.

## Validation Stages

- `preflight_assembly_intent`
- `validate_part_inputs`
- `validate_placement_relationships`
- `validate_constraints`
- `validate_assembly_exports`

Do not move single-part geometry checks into this skill. Single-part rules stay
in part generation and review; this skill owns how parts relate to one another.

See:

- `knowledge/assembly_rules.md`
- `knowledge/constraints.md`
- `knowledge/clearances.md`
