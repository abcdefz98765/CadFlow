# Revision Workflow Architecture

## Authority and scope

This document defines structured revision of an existing CadFlow result.

It preserves the canonical Workspace / Work / Run / Part Job model in:

- `cadflow-canonical-product-architecture.md`

Revision Agent behavior and private knowledge are defined by:

- `agent-skill-knowledge.md`
- `../../skills/revision/SKILL.md`

## Core rule

A revision creates a child Run. It never overwrites the parent.

    accepted parent result
      + explicit natural-language change request
      -> revision request
      -> structured change intent
      -> revision plan
      -> structured patch when supported
      -> local validation
      -> deterministic child execution
      -> parent/child comparison
      -> user review and optional acceptance

## Preferred source order

### CadFlow-native parent

Highest priority. A parent with validated CAD IR can be revised through structured field changes and deterministic regeneration.

### CadFlow-compatible IR and implementation artifacts

May be accepted after validation and import into a controlled parent Run.

### External STEP

Reference and limited derived-edit source only. CadFlow must not promise robust parametric feature-history recovery.

### STL, OBJ, or mesh

Visual or measurement reference only unless a future explicit reconstruction capability is implemented and validated.

## Revision artifacts

A revision child Run may contain:

    revision_request.json
    change_intent.json
    revision_plan.json
    patch.json
    parent input snapshot or reference
    child input_ir.json when validation succeeds
    child model products in Full mode
    comparison.json
    revision_report.md
    lineage.json
    report.json / report.md
    agent_trace.json
    logs/runtime.json

Blocked revisions preserve intent, plan, patch attempt, comparison, lineage, and report evidence. They do not write misleading child CAD products.

## Change intent

`change_intent.json` records what the user requested independently of what the system ultimately changes.

It should identify:

- target parent Run and part;
- requested outcome;
- candidate structured changes;
- uncertainty and missing decisions;
- supported, unsupported, or user-input-required status.

## Revision plan

`revision_plan.json` records:

- strategy and target artifact;
- ordered operations;
- expected validations;
- unsupported portions;
- status: ready, blocked, or user input required.

The plan must not treat free-form regeneration without trace as a valid structured revision.

## Patch contract

For CadFlow-native CAD IR, prefer explicit operations:

    {
      "op": "replace",
      "path": "dimensions.thickness",
      "before": 5,
      "value": 6,
      "reason": "User requested a thicker part"
    }

Rules:

- use allowlisted CAD field paths;
- record before/after where possible;
- separate user-requested changes from validator/system repair changes;
- preserve unrelated fields;
- reject or ask when the change cannot be represented safely;
- validate the patched CAD IR before deterministic execution.

## Execution and comparison

A validated patch produces a new child Run through the existing deterministic pipeline.

`comparison.json` and `revision_report.md` should distinguish:

- requested changes;
- actual structured changes;
- validation or system repair changes;
- product availability;
- limitations and unverified intent;
- parent and child lineage.

Creating a successful child Run does not automatically replace the Work's accepted result. User approval remains explicit.

## Agent boundary

The Revision Agent may:

- parse user change intent;
- request allowlisted parent context;
- propose a structured plan and patch;
- react to validator feedback;
- ask the user or stop safely.

It may not:

- overwrite parent artifacts;
- execute provider-generated Python, shell, or CadQuery;
- invent unsupported external-file feature recovery;
- silently change unrelated geometry;
- update accepted-result pointers;
- bypass patch and CAD IR validation.

## Current capability

Current deterministic revision support is intentionally narrow and CadFlow-native. It can represent selected field-level CAD IR changes and create a child Run when the patch validates.

Not yet product-usable:

- arbitrary geometry editing;
- robust external STEP feature recovery;
- STL/mesh reverse engineering;
- complete provider-backed revision episodes;
- full browser revision experience across all artifacts.

The runtime and UI must expose these limitations rather than implying general CAD editing.

## Tests

Protect:

- parent immutability;
- explicit child lineage;
- allowlisted structured paths;
- before/after patch evidence;
- blocked unsupported changes;
- invalid patch never reaching CAD execution;
- requested versus repair change separation;
- child creation not automatically updating accepted result;
- external STEP/mesh limitations;
- path and secret sanitization.

## Invariants

1. Revision begins from an explicit parent.
2. Parent Run evidence is immutable.
3. Change intent, plan, patch, execution, comparison, and approval are separate decisions.
4. Structured native CAD IR revision is preferred.
5. Unsupported edits block safely.
6. New child products require local validation and deterministic execution.
7. Acceptance remains a user decision at Work level.