# Part Modeling Skill

Purpose: realize CAD IR into individual CAD part artifacts through
template-backed, backend-aware generation and a closed execution/validation
loop.

This skill owns template lookup, feature implementation lookup, backend mapping,
generation preflight, CAD backend invocation, geometry checks, and part-level
IR match. It does not own product-level decomposition, design tradeoffs, or
assembly relationships.

## Inputs

- `input_ir.json` / `CADIR`
- selected part-level planning decisions when needed for traceability
- legacy single-part `part_spec.json` or planned part list when using the
  compatibility workflow
- template candidates and reference component envelopes from Planning
- template, feature, reference-component, and backend capability knowledge

## Outputs

- `model.py`
- `model.step`
- `model.stl`
- part-level `report.json`
- part-level `report.md`
- `agent_trace.json`
- `logs/runtime.json`

## Behavior

- Treat CAD IR as the single-part geometry source of truth.
- Select a reusable template when one fits the CAD IR.
- Look up feature implementations and backend patterns needed to realize the
  requested holes, bosses, chamfers, fillets, shells, interfaces, or other
  supported features.
- Parameterize template dimensions, features, and interfaces from CAD IR before
  calling a CAD backend.
- Run preflight checks before generation: positive dimensions, required fields,
  unit, feature schema, and L0/L1 warning framework.
- Call only backend-neutral interfaces from workflow code.
- After generation, check non-empty geometry, positive volume, single solid,
  bbox consistency, export files, and explicitly verifiable IR targets.
- Use structured failure analysis to repair implementation-level IR or mapping
  issues without changing product intent or Planning decisions.
- Record assumptions and unverified intent instead of reporting them as passed.
- If no template or backend capability can realize the CAD IR, report the gap or
  return it to Planning; do not silently redesign the part.

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

- `../../docs/workflow_contract.md`
- `knowledge/feature_library.md`
- `knowledge/template_catalog.md`
- `knowledge/reference_components.md`
