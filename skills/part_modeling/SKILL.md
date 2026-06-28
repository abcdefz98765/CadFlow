# Part Modeling Skill

Purpose: generate individual manufacturable parts through template-backed,
backend-neutral part specifications and a closed generation loop.

This skill owns part template selection, part parameterization, generation
preflight, CAD backend invocation, geometry checks, and part-level intent match.
It does not own product-level decomposition or assembly relationships.

## Inputs

- `requirement.json`
- `plan.md`
- single-part `part_spec.json` or planned part list
- template candidates and reference component envelopes from Planning

## Outputs

- one `part_spec.json` per generated part
- `model.py`
- `exports/model.step`
- `exports/model.stl`
- `review.md` or part-level review section
- `logs/generation.json`

## Behavior

- Select a reusable template when one fits the part intent.
- Parameterize template dimensions, features, interfaces, and assumptions before
  calling a CAD backend.
- Run preflight checks before generation: positive dimensions, required fields,
  unit, feature schema, and L0/L1 warning framework.
- Call only backend-neutral interfaces from workflow code.
- After generation, check non-empty geometry, positive volume, single solid,
  bbox consistency, export files, and explicitly verifiable intent.
- Record assumptions and unverified intent instead of reporting them as passed.

## Template Knowledge

Initial template families:

- mounting plate
- enclosure base and lid
- bracket
- spacer or standoff
- button cap
- switch carrier plate
- PCB tray
- cable clip
- simple cover

See:

- `knowledge/feature_library.md`
- `knowledge/template_catalog.md`
- `knowledge/reference_components.md`
