# CadFlow Workflow Cockpit Design Specification

Status: canonical UX specification for the Web Console.

This document defines how CadFlow should present a Work, its workflow stages, user input, agent output, intervention points, and immutable Runs. It is intentionally product-first. Backend architecture may evolve, but the user experience should continue to satisfy this contract.

## 1. Product definition

CadFlow Web Console is a workflow cockpit for AI-assisted CAD creation.

It is not primarily:

- a browser CAD editor;
- a raw artifact browser;
- a run log viewer;
- a provider/debug console;
- a diagram of internal backend routes.

The cockpit helps a user answer:

1. What am I trying to create?
2. Which attempt or active lineage am I looking at?
3. Where is the workflow now?
4. What did I provide at this stage?
5. What did the agent understand, decide, or generate?
6. Is the result trustworthy enough to continue?
7. Where can I intervene?
8. What changed between Runs?
9. What deliverables are available?

## 2. User mental model

The UI must preserve this hierarchy:

```text
Workspace
  -> Work
      -> Current Work lineage
      -> Run 1 (immutable attempt)
      -> Run 2 (immutable rework attempt)
      -> Run 3 (immutable child or retry attempt)
          -> Stage
              -> User input
              -> Agent interpretation / decision
              -> Agent output
              -> Review / intervention
              -> Evidence / artifacts
```

### Workspace

A local container for Works, configuration, examples, and safe storage boundaries.

### Work

A long-lived design objective, such as "Desktop 2DOF Robot Arm". The Work persists while its Runs accumulate.

### Run

An immutable attempt or branch within a Work. A Run records what inputs were used, what stages executed, what outputs were produced, and why it ended.

### Stage

A meaningful user-facing step such as Requirement, Planning, Assembly Plan, CAD IR Draft, or Part Modeling.

### Artifact

Evidence produced or consumed by a stage. Artifacts are source of truth, but the normal UI presents readable summaries before raw content.

## 3. Work mode and Run mode

The UI must not conflate a Work with one Run.

### 3.1 Current Work mode — default and actionable

Current Work mode shows the active aggregated lineage for the Work. It may combine accepted or current artifacts from a root Run and child/rework Runs.

Use this mode for:

- understanding current progress;
- selecting a stage;
- reviewing current input and output;
- approving, editing, rerunning, or requesting rework;
- finding current deliverables.

The header must state:

```text
View: Current Work
Active lineage: Run 3 based on Run 2
```

### 3.2 Run Snapshot mode — immutable audit

Run Snapshot mode shows one immutable attempt exactly as it happened.

Use this mode for:

- auditing a previous attempt;
- understanding why a Run failed or was superseded;
- comparing its inputs and outputs with the current Work;
- starting a new rework Run.

The header must state:

```text
View: Run Snapshot
Run 2 · immutable · superseded by Run 3
```

Actions that would mutate the selected Run are disabled. The primary action may create a new child/rework Run.

### 3.3 Mode switching

The Workflow page must expose a clear context control:

```text
[Current Work] [Run Snapshot: Run 1 v]
```

Switching modes must not silently change the selected Work.

## 4. Primary navigation

A selected Work has four user-facing areas.

### Overview

Answers:

- What is this Work?
- What is the current overall state?
- Which Run or lineage is active?
- What is the recommended next action?
- What deliverables exist?

### Workflow

Answers:

- Which stages exist?
- Which stages are completed, running, blocked, skipped, or unavailable?
- What did the user provide and what did the agent produce at each stage?
- Where can the user intervene?

### Parts

Answers:

- Which candidate and reference parts exist?
- Which part is selected?
- Which part attempts and outputs exist?
- Which part is blocked or ready for review?

### History

Answers:

- Which Runs exist?
- How are they related?
- Why was a Run created?
- What changed from one Run to another?

Raw artifacts and diagnostics are secondary or advanced views, not primary navigation.

## 5. Workflow page structure

The Workflow page uses this hierarchy:

```text
1. Work and mode context
2. Run strip / lineage context
3. Current conclusion and recommended action
4. Dot workflow graph
5. Selected stage detail
6. Evidence and advanced details
```

### 5.1 Desktop wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Golden Desktop Robot Arm                                      Current Work  │
│ Active lineage: Run 3 · Full mode · one generic concept part generated      │
│ [Current Work] [Run Snapshot v]                              [View History] │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Runs                                                                         │
│ ● Run 1 Initial      ──▶ ● Run 2 Clarified      ──▶ ● Run 3 Full create    │
│   superseded              accepted                  active                   │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Current result                                                               │
│ `upper_link` was normalized to a generic link-like family and generated.     │
│ Recommended next step: review the STEP/STL result.     [Review result]       │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Workflow                                                                     │
│                                                                              │
│  ● Requirement ─ ● Clarification ─ ● Planning ─ ● Assembly Plan             │
│                                                     │                        │
│            Candidate parts: base  lower_link  [upper_link]  ...             │
│            Reference lane:  servo  gripper                                  │
│                                                     │                        │
│  ● Part Request ─ ● Part Review ─ ● Handoff ─ ● CAD IR ─ ● Modeling         │
│                                                              │               │
│                                                   ● Result Review ─ ● Review │
└──────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────┬──────────────────────────────────────────┐
│ Selected stage                    │ Primary action                           │
│ Part Modeling · Completed         │ Review generated part                    │
│ Generated one generic concept     │ [Open 3D result]                         │
├───────────────────────────────────┼──────────────────────────────────────────┤
│ USER INPUT                        │ AGENT OUTPUT                             │
│ Reviewed upper_link handoff       │ link_like_part                           │
│ Source: Run 3 / Reviewed Handoff  │ elongated_plate_with_end_holes           │
│ [View] [Edit override]            │ STEP ✓  STL ✓                            │
├───────────────────────────────────┴──────────────────────────────────────────┤
│ Agent interpretation / transformation                                        │
│ upper_link intent -> generic link-like family                                │
│ Assumptions: FDM concept part; no strength or assembly validation             │
├──────────────────────────────────────────────────────────────────────────────┤
│ Evidence: cad_ir_draft ✓  input_ir ✓  STEP ✓  STL ✓                          │
│ [Advanced details] [Raw artifacts] [Diagnostics]                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Mobile / narrow layout

On narrow screens:

1. Work context remains first.
2. Run strip becomes a horizontal scroll or compact selector.
3. Workflow graph becomes horizontally scrollable; it must not collapse into unlabeled dots.
4. Selected stage detail stacks in this order:
   - conclusion;
   - primary action;
   - user input;
   - agent output;
   - interpretation;
   - evidence;
   - advanced.

## 6. Dot workflow graph

The dot graph is the primary workflow state visualization.

### 6.1 Node anatomy

Every visible stage node requires:

```json
{
  "stage_id": "part_modeling",
  "label": "Part Modeling",
  "status": "completed",
  "short_summary": "Generated STEP and STL for the selected generic part.",
  "clickable": true,
  "attention_required": false,
  "selected": false,
  "source_run_label": "Run 3",
  "source_artifact_count": 4
}
```

A node must never render if `stage_id`, `label`, `status`, or `short_summary` is absent.

When source data cannot be projected, render an explicit node:

```text
Part Modeling
Data unavailable
```

Do not render a blank dot, blank label, or empty tooltip.

### 6.2 Visual anatomy

Each node contains:

- a status dot;
- a short stage label below or beside the dot;
- an optional compact status word;
- a selected outline or background;
- an attention indicator only when action is required.

Do not place long artifact names inside the graph.

### 6.3 State colors

Status color and selection style are separate concepts.

| Status | Meaning | Visual treatment |
|---|---|---|
| `not_started` | no valid stage attempt yet | neutral gray hollow dot |
| `ready` | prerequisites satisfied | blue-gray dot |
| `running` | currently executing | blue dot with subtle pulse |
| `completed` | valid output accepted for lineage | green filled dot |
| `completed_with_assumptions` | completed but assumptions need visibility | green dot with amber marker |
| `needs_review` | user decision required | amber filled dot |
| `user_modified` | validated override is active | purple marker on business status |
| `stale` | upstream changed; output no longer current | amber-gray outlined dot |
| `blocked` | cannot continue without capability or user change | red filled dot |
| `failed` | unexpected execution failure | red dot with failure icon |
| `skipped` | intentionally not applicable | gray-blue slash dot |
| `execution_skipped` | contract or policy intentionally stopped execution | gray-blue outlined dot |
| `reference_only` | context component, not generated | gray outlined square/chip |
| `unavailable` | projection or data unavailable | dark-gray dashed dot |

Selected state uses an outer ring or soft background and must not replace the status color.

### 6.4 Graph topology

The graph is not a single straight line for assembly work.

```text
Stage spine
Requirement -> Clarification -> Planning -> Assembly Plan

Part branch
Candidate parts + Reference lane

Selected-part pipeline
Part Request -> Part Review -> Reviewed Handoff -> CAD IR Draft
-> Part Modeling -> Part Result Review

Review tail
Workflow Review -> Rework
```

Candidate and reference nodes are visibly distinct from workflow stages.

### 6.5 Default selection

When opening Workflow in Current Work mode, select the first matching node in this priority:

```text
blocked
> needs_review
> running
> stale
> latest completed stage with a meaningful action
> first ready stage
> last completed stage
```

Do not always default to Workflow Review merely because it is chronologically last.

In Run Snapshot mode, default to the Run's terminal or failure stage.

### 6.6 Hover and click

Hover may show:

- stage name;
- status;
- one-sentence summary;
- source Run;
- recommended action.

Click selects the stage and updates the detail panel without changing Work or Run context.

## 7. User input and agent output

Every selected stage must clearly separate three concepts:

```text
USER INPUT
AGENT INTERPRETATION / DECISION
AGENT OUTPUT
```

This separation is mandatory even when the underlying data is stored in multiple artifacts.

### 7.1 User input block

Show:

- human-readable input name;
- input summary;
- source type: user prompt, clarification answer, accepted upstream output, or active override;
- source Run and stage;
- validation state;
- editability;
- whether downstream output is stale because of an edit.

Example:

```text
USER INPUT
Reviewed part handoff for upper_link
Source: Run 3 · Reviewed Handoff
Status: validated original artifact
[View summary] [Create override]
```

### 7.2 Agent interpretation / decision block

Show what the agent changed or decided, not raw chain-of-thought.

Allowed content:

- classification;
- route selection;
- assumptions;
- normalization mapping;
- key dimensions chosen;
- capability limitation;
- validation decision;
- concise reason.

Example:

```text
AGENT INTERPRETATION
Recognized upper_link as a link-like mechanical member.
Normalized it to link_like_part / elongated_plate_with_end_holes.
Reason: elongated arm member with two joint interfaces.
```

Do not expose hidden reasoning, raw provider transcripts, or verbose internal traces.

### 7.3 Agent output block

Show:

- output summary;
- output type;
- status and validation;
- user-facing preview when available;
- produced files;
- limitations;
- source Run and child Run where relevant.

Example:

```text
AGENT OUTPUT
Generic link-like concept part
CAD IR validated
STEP available · STL available
Not a complete robot-arm assembly
[Open result] [Download STEP] [Download STL]
```

### 7.4 Input/output relationship

The detail panel must explain causality:

```text
Because Contract mode intentionally skipped CAD execution,
input_ir.json exists but STEP/STL are not expected.
```

Do not merely show a list of present and absent files.

## 8. User intervention model

The user must be able to recognize where intervention is possible.

### 8.0 Write-action runtime feedback

Every Workflow write follows one visible lifecycle: `idle` → `confirming`
(when required) → `pending` → backend execution → refreshed state and
postcondition verification → `succeeded` or `failed`. The feedback panel is
persistent, uses blue/green/red/amber semantic states, and remains visible
until dismissed or replaced by the next action. A write must never claim
success merely because its backend call returned without an exception.

The primary Workflow renderer localizes action labels and hover contracts in
English and Chinese. Artifact contents and stable enums may remain English;
browser-visible labels must not fall back to backend action names or internal
keys.

### 8.1 Intervention categories

- **Review** — inspect and record acceptance or expected limitation.
- **Override** — edit an allowlisted structured artifact through a validated versioned override.
- **Approve** — accept a result for the active lineage.
- **Rerun** — create a new immutable attempt using the same accepted input.
- **Rework** — create a new child Run with requested changes and a target stage.
- **Change selection** — choose another candidate part where supported.
- **Inspect evidence** — open summaries, previews, or raw allowlisted artifacts.

### 8.2 Action hierarchy

Each selected stage should have:

- at most one primary action;
- zero to three secondary actions;
- disabled actions grouped separately with explicit reasons;
- advanced/debug actions collapsed.

Examples:

```text
Part Modeling completed
Primary: Review generated result
Secondary: Open STEP/STL, Request rework

CAD IR blocked
Primary: Inspect CAD IR draft
Secondary: Create override, Mark expected block

Requirement needs clarification
Primary: Answer clarification
Secondary: Edit requirement summary
```

### 8.3 Post-action navigation

After a successful action:

1. refresh the Work projection;
2. preserve Work context;
3. select the next stage requiring attention;
4. show a concise success message;
5. expose the new Run if one was created.

Do not leave the user on a stale stage without explanation.

## 9. Run strip and History design

Different Runs under one Work must be visible and understandable.

### 9.1 Run strip on Workflow

Show a compact lineage strip above the graph.

Each Run item displays:

- friendly label: `Run 1`, `Run 2`, etc.;
- purpose: Initial, Clarification, Rework, Retry, Full create;
- status;
- relationship: based on / child of;
- active, superseded, or current badge;
- terminal result;
- timestamp as secondary information.

Example:

```text
Run 1 · Initial       Superseded
Run 2 · Clarified     Accepted input
Run 3 · Full create   Active · STEP/STL generated
```

The strip is not a dense raw run table.

### 9.2 History page

History provides full audit details:

- immutable Run list;
- parent/child relationship;
- trigger and creator;
- execution mode;
- stage reached;
- result scope;
- product availability;
- comparison with previous Run;
- link to open Run Snapshot mode.

### 9.3 Run comparison

MVP comparison may be summary-only:

```text
Run 2 -> Run 3
Changed input: primary_generated_part confirmed as upper_link
Changed output: CAD execution added STEP/STL
Unchanged: assembly_generated=false
```

Raw JSON diff is advanced.

## 10. Page-level information hierarchy

### 10.1 Primary information

Visible without expansion:

- Work title;
- Current Work or Run Snapshot mode;
- active/current Run;
- overall status;
- one recommended action;
- workflow dot graph;
- selected stage conclusion;
- user input and agent output summaries.

### 10.2 Secondary information

Visible in normal detail sections:

- assumptions;
- selected candidate;
- artifact validation state;
- evidence chain;
- limitations;
- source Run and child Run.

### 10.3 Advanced information

Collapsed by default:

- raw JSON;
- diagnostic codes;
- adapter/provider identity;
- runtime trace;
- internal route and gate data;
- absolute or local filesystem details.

## 11. Visual design rules

CadFlow should feel like an engineering cockpit: calm, structured, traceable, and focused.

### 11.1 Layout

- Use one prominent Work header, not several competing banners.
- Use the graph as the central visual anchor.
- Keep selected stage detail in a two-column layout on desktop and stacked layout on mobile.
- Prefer sections and subtle separators over a heavy card around every paragraph.
- Keep advanced content collapsed.

### 11.2 Typography

- Page title: strong and compact.
- Current conclusion: medium-large, one or two sentences.
- Stage labels: short and consistent.
- Metadata: smaller and lower contrast.
- Raw artifact names use monospace only where useful.

### 11.3 Spacing

Use a consistent spacing scale. Avoid both cramped debugging density and excessive empty dashboard spacing.

Recommended relative rhythm:

```text
4 px  inline/icon gap
8 px  compact control gap
12 px row gap
16 px component padding
24 px section gap
32 px major-region gap
```

### 11.4 Color

- Use status colors only for status.
- Use one accent color for primary actions and selected navigation.
- Do not use status red for ordinary destructive-looking decoration.
- Do not use the same blue to mean both selected and running.
- Keep background and border colors neutral.

### 11.5 Icons

Icons support labels; they do not replace stage names or action text.

### 11.6 Density

The graph should be compact enough to see the main path without scrolling vertically through every stage. The detail panel provides depth after selection.

## 12. View-model contracts

### 12.1 Workflow page contract

```json
{
  "work_context": {
    "work_id": "golden_desktop_robot_arm",
    "title": "Golden Desktop Robot Arm",
    "view_mode": "current_work",
    "overall_status": "completed",
    "overall_summary": "One generic concept part was generated.",
    "recommended_action": {}
  },
  "run_context": {
    "active_run_id": "...",
    "runs": [],
    "viewed_run_id": null
  },
  "graph": {
    "sections": [],
    "selected_node_id": "part_modeling"
  },
  "selected_stage": {},
  "empty_state": null,
  "error_state": null
}
```

### 12.2 Selected stage contract

```json
{
  "stage_id": "part_modeling",
  "label": "Part Modeling",
  "status": "completed",
  "summary": "Generated a validated generic concept part.",
  "source_run_label": "Run 3",
  "input_panel": {
    "title": "Reviewed upper_link handoff",
    "summary": "Approved selected part and assembly context.",
    "source": "reviewed_handoff",
    "editable": true,
    "override_active": false
  },
  "agent_interpretation": {
    "summary": "Normalized upper_link to a generic link-like family.",
    "decisions": [],
    "assumptions": [],
    "limitations": []
  },
  "output_panel": {
    "title": "Generic link-like concept part",
    "summary": "CAD IR, STEP, and STL generated.",
    "validation_status": "passed",
    "products": []
  },
  "primary_action": {},
  "secondary_actions": [],
  "disabled_actions": [],
  "evidence": [],
  "advanced": {}
}
```

### 12.3 Run item contract

```json
{
  "run_id": "...",
  "display_label": "Run 3",
  "purpose": "Full create",
  "status": "completed",
  "relationship": "child_of_run_2",
  "is_active": true,
  "is_immutable": true,
  "terminal_stage": "workflow_review",
  "result_summary": "STEP/STL generated for upper_link."
}
```

## 13. Loading, empty, and error states

### Loading

Show skeletons or a concise progress indicator while preserving the page structure. Do not show blank graph dots while loading.

### Empty Work

```text
No workflow has started yet.
Add a requirement to begin.
[Add requirement]
```

### No stage data

```text
Part Modeling
Stage data unavailable
CadFlow could not project this stage from the Work lineage.
[View diagnostic details]
```

### Failed execution

Explain:

- what failed;
- whether earlier artifacts remain valid;
- whether the user can retry or rework;
- whether any model files were produced.

### Contract mode

```text
Validated, execution skipped
CAD IR and input_ir.json were created.
STEP/STL generation was intentionally skipped in Contract mode.
```

This is not blocked and not failed.

## 14. Golden Desktop Robot Arm acceptance flow

The Full example is the canonical visual acceptance flow.

### Step 1 — create example

Workspace shows a clear Examples section. Creating the Full example gives progress feedback and creates a new immutable Work attempt rather than overwriting history.

### Step 2 — land on Workflow

After completion:

- selected Work is Golden Desktop Robot Arm;
- view mode is Current Work;
- active Run is visible;
- Part Modeling or Result Review is selected based on attention priority.

### Step 3 — inspect graph

The graph shows nonblank nodes for:

- Requirement;
- Clarification;
- Planning;
- Assembly Plan;
- Part Request;
- Part Review;
- Reviewed Handoff;
- CAD IR Draft;
- Part Modeling;
- Part Result Review;
- Workflow Review;
- Rework.

Full mode expected status:

- all stages through Workflow Review are completed;
- Rework is not started;
- upper_link is selected;
- reference components are visibly reference-only.

### Step 4 — inspect Requirement

The user can distinguish:

- original prompt;
- clarification answers;
- agent-understood assembly goal;
- assumptions and missing information;
- active requirement version.

### Step 5 — inspect Assembly Plan

The user sees:

- 6 candidate parts;
- 2 reference components;
- selected upper_link;
- full assembly CAD is not claimed;
- action to change selection only where supported.

### Step 6 — inspect Part Modeling

The detail shows:

```text
USER INPUT
Reviewed upper_link handoff

AGENT INTERPRETATION
upper_link -> link_like_part -> elongated_plate_with_end_holes

AGENT OUTPUT
single_generic_concept_part
STEP present
STL present
assembly_generated=false
```

### Step 7 — inspect Runs

The user can tell:

- which Run is active;
- which earlier Runs exist;
- whether a Run was superseded;
- which Run produced STEP/STL;
- how to open an immutable Run Snapshot.

### Contract example acceptance

Contract mode shows:

- CAD IR completed;
- input_ir created;
- Part Modeling `execution_skipped`;
- Part Result Review skipped;
- Workflow Review completed;
- no blocked or failed claim;
- STEP/STL explicitly not expected.

## 15. Screenshot review checklist

Before merging a substantial UI change, capture at least:

1. Workspace with Examples and Work list.
2. Full example Workflow graph.
3. Contract example Workflow graph.
4. Requirement selected-stage detail.
5. Assembly Plan selected-stage detail.
6. Part Modeling selected-stage detail.
7. Work with at least two Runs visible.
8. Run Snapshot mode.
9. Blocked or unavailable stage state.
10. Narrow/mobile layout if the change affects layout.

Review each screenshot for:

- Is Work/Run context unmistakable?
- Are all graph dots labeled?
- Is status understandable without hover?
- Can user input and agent output be visually separated?
- Is the primary action obvious?
- Are raw artifacts secondary?
- Is selected state distinct from business status?
- Is there duplicated explanation?
- Are empty states explicit rather than blank?
- Does the page look like an engineering cockpit rather than a debug dashboard?

## 16. Implementation sequence

Implement UI changes in this order:

1. Finalize the page/view-model contract.
2. Validate Work and Run semantics.
3. Render a static wireframe with representative data.
4. Implement graph topology and node states.
5. Implement Current Work / Run Snapshot context.
6. Implement selected stage input/interpretation/output panels.
7. Implement intervention actions and post-action navigation.
8. Implement empty/loading/error states.
9. Apply visual system and responsive behavior.
10. Run Golden acceptance and screenshot review.

Do not start with CSS polish before the contract and interaction flow are correct.

## 17. Non-goals for the UI pass

A UI implementation based on this specification must not silently add:

- new CAD families;
- part-specific templates;
- complete assembly generation;
- strength claims;
- motion simulation;
- servo fit validation;
- arbitrary file editing;
- executable provider code paths;
- hidden mutation of immutable Runs.

## 18. UI change request template for Codex

Use this structure for future implementation requests:

```text
User task:
What is the user trying to accomplish?

Page and context:
Workspace / Overview / Workflow / Parts / History
Current Work or Run Snapshot

Current problem:
What is confusing or impossible today?

Expected interaction:
What should be selected by default?
What happens on click?
What is the primary action?
Where does the user land after the action?

View-model changes:
Required fields, states, and fallback behavior.

Wireframe:
ASCII or screenshot annotation.

State coverage:
loading / empty / running / completed / needs_review / blocked / failed /
skipped / execution_skipped / stale / unavailable

Visual requirements:
Hierarchy, density, status color, selected state, responsive behavior.

Golden acceptance:
Exact expected behavior for Full and Contract examples.

Non-goals:
What backend or CAD behavior must not change?

Verification:
Tests plus required screenshots.
```

This template is intentionally stricter than a request such as "make the graph clearer." It gives implementation a stable product target and prevents local patches from becoming the UI design process.

## 19. Implemented Work / Run contract milestone

The Workflow page now consumes one mode-safe page view model. **Work Workflow
is an active-lineage aggregated view. Run Snapshot is immutable and read-only.
Actions declare their scope and target Run.** Legacy Works retain a conservative
root-run projection marked `lineage_inferred=true`; a newer attempt is never
silently treated as accepted solely because it is newer.

## 20. Workflow cockpit visual and interaction layer

The implemented Workflow page is arranged as a cockpit, in this order:

1. a Current Work hero or an unambiguous Historical Run Snapshot read-only banner;
2. a horizontally scrollable Run lineage strip beginning with Current Work;
3. current conclusion and the single recommended primary action;
4. a wide dot-and-connector workflow canvas;
5. the selected-stage conclusion and causal detail order: **User Input → Agent Interpretation / Decision → Agent Output**;
6. compact evidence and collapsed advanced detail.

The graph uses a centralized semantic token set. Node **shape** identifies stage,
candidate, reference, review, or rework; **color** identifies business status;
an outer outline identifies selection; and a separate attention label identifies
review, stale, blocked, or running work. Nodes retain labels and compact status
text at every width. The graph and Run strip scroll horizontally on narrow
screens rather than wrapping and losing their topology. Candidate parts are
rounded chips; reference-only components are square/dashed chips.

Contract mode renders `execution_skipped` / `contract_complete` as a valid
outcome: CAD IR is validated, `input_ir.json` is present, and STEP/STL are not
expected. It must never look blocked or like missing export files. Full mode
states that the result is one generic concept part and that no assembly was
generated.

Screenshot acceptance is performed against executable Golden Full, Contract,
and historical snapshot Workflows at 1440, 1024, and 390–430 px. If the browser
environment cannot reach the local console, record that technical limitation,
the launch command, and the manual checklist rather than claiming visual
acceptance.

## 21. Candidate selection and review closure

`Use This Part Next` is a structured Current Work action, not a selectable
graph chip. It displays a confirmation containing the old/new candidate, stale
downstream stages, preserved historical Runs, and the fact that it does not
start CAD generation. Confirmation writes a validated, versioned Assembly Plan
override and Work-level selection metadata; it never edits the original Run
artifact, clears an accepted result, or changes active lineage. Reference-only,
unsupported, already-selected, and Run Snapshot candidates remain disabled with
an explanatory hover.

Every selected stage exposes an append-only Stage Review form and Quick
Approve. Needs Revision requires requested changes; Blocked requires a reason.
The latest compatible `stage_review.json` is materialized for existing rework
while each original review remains under `reviews/<stage>/review_NNN.json`.
