# Workflow Decisions

CadFlow should not assume users can provide complete requirements up front.
Incomplete requirements do not always block generation. The correct decision
depends on check level, risk, and whether missing fields affect fit,
manufacturing, assembly, safety, or certification.

## Decision Vocabulary

Workflow gates should support these decisions:

| Decision | Meaning |
| --- | --- |
| `proceed` | Required information is sufficient for the selected check level. |
| `proceed_with_assumptions` | Continue with explicit, recorded assumptions. |
| `ask_user` | Ask focused clarification questions before continuing. |
| `return_to_requirement` | Send the workflow back to requirement interpretation. |
| `return_to_planning` | Send the workflow back to planning or CAD IR handoff. |
| `revise_existing_model` | Route the request into the Model Revision Workflow. |

The existing deterministic baseline may implement only a subset. This document
defines the intended workflow contract for later stages.

## Workflow Modes

### Exploratory Mode

Use for L0 Playground and early L1 Maker work.

The system may generate a first draft with assumptions when risk is low. For
example, if the user says "Make a small enclosure for a button and a battery",
CadFlow may assume:

- FDM printing.
- PLA.
- 2 mm wall thickness.
- Generic button clearance.
- Default enclosure size.

Those assumptions must be written into artifacts, shown to the user, and
available for later revision. The generated result is a draft, not engineering
approval.

### Confirmation Mode

Use when missing information may materially affect fit, manufacturing,
assembly, cost, or user expectation.

CadFlow should ask focused questions or offer a clearly stated assumption before
generation. Example:

```text
I can draft this enclosure assuming a 18650 battery and FDM printing.
Should I proceed with those assumptions?
```

Confirmation mode should minimize broad questionnaires. Ask only the fields that
change the next workflow decision.

### Strict Mode

Use for L2/L3/L4 workflows and any safety, compliance, load-bearing, tolerance,
or certification-sensitive work.

CadFlow must not silently invent engineering-critical details such as:

- Material or material certification.
- Loads, forces, pressure, or duty cycle.
- Safety constraints.
- Fits, tolerances, and clearances.
- Manufacturing process requirements.
- Standards or certification targets.

Missing critical fields should produce `ask_user`, `return_to_requirement`, or a
blocking report instead of `proceed_with_assumptions`.

## Artifact Requirements

When CadFlow proceeds with assumptions, artifacts should capture:

- The assumption text.
- The affected requirement, planning, or IR field.
- The reason the assumption was allowed.
- The check level and workflow mode.
- Whether user confirmation was requested or received.

Reports and the Web Console should make assumptions visible without requiring a
user to inspect raw JSON.
