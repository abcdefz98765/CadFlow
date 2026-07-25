# CadFlow Agent Workbench Design Specification

Status: target UX specification.

The filename is retained temporarily for link compatibility. The former fixed
Workflow Cockpit is now a legacy/diagnostic surface.

## 1. Product experience

CadFlow is a design workbench where the user collaborates with an Agent and
sees geometry, evidence, and decisions evolve.

The main page should answer:

- What are we designing?
- What is the Agent doing now?
- What candidate geometry exists?
- What changed after execution or repair?
- What is validated, assumed, unverified, or unsupported?
- What should the user do next?

## 2. Primary navigation

A selected Work has:

- **Design** — conversation, Agent activity, current candidate, preview, and
  recommended action;
- **Parts** — Part Jobs, attempts, interfaces, and accepted results;
- **Assembly** — Assembly Job, accepted inputs, constraints, result, and
  limitations;
- **Deliverables** — accepted-result-derived STEP, assembly, BOM, drawings, and
  reports;
- **History** — immutable Runs, comparisons, and Run Snapshots;
- **Diagnostics** — legacy Workflow graph, raw artifacts, episode events, and
  low-level evidence.

Pages without implemented capability show an honest target-state explanation,
not enabled placeholder actions.

## 3. Design page

Desktop order:

```text
Work header and assurance mode
Current objective and recommended action

Conversation / Agent activity | Geometry preview

Current candidate and validation summary
Meaningful alternatives
Part Jobs and assembly readiness
Advanced evidence
```

Narrow order:

```text
Objective
Recommended action or focused question
Geometry preview
Agent activity
Current candidate
Validation and limitations
Alternatives
Part Jobs
Advanced
```

## 4. Work header

Show:

- Work title;
- Intent, Design, Build & Evaluate, or Accept & Deliver;
- Explore or Engineer assurance mode;
- active Part Job or Assembly Job;
- accepted-result count;
- concise current status.

Do not show raw ids or paths by default.

## 5. Conversation panel

Contains:

- user goal and focused answers;
- concise Agent decisions;
- visible assumptions;
- candidate proposals;
- important recovery explanations.

Activity events such as context retrieval and tool calls appear in a compact
expandable timeline.

The panel is not a raw provider transcript.

## 6. Geometry preview

The preview is the primary visual anchor once a candidate exists.

States:

- no candidate;
- candidate source ready;
- executing;
- geometry available;
- validation failed but preview retained as diagnostic;
- reviewable;
- accepted;
- assembly preview;
- preview unavailable with explicit reason.

Controls:

- orbit, pan, zoom;
- fit view;
- candidate selector when comparison is meaningful;
- show key measurements;
- open accepted result;
- compare previous/next where supported.

## 7. Agent activity

Represent the current action in product language:

```text
Understanding the mounting interfaces
Preparing a bent-sheet bracket candidate
Executing candidate 2
Inspecting a failed boolean cut
Repairing the pocket geometry
Waiting for your servo mounting pattern
```

Show budgets or provider details only in Advanced.

## 8. Candidate cards

Each candidate contract includes:

```json
{
  "candidate_id": "candidate_002",
  "title": "Bent-sheet L bracket",
  "strategy": "sheet_metal_like",
  "execution_path": "sandboxed_model_program",
  "status": "reviewable",
  "summary": "Two-leg bracket with slotted base mounting.",
  "tradeoff": "Lower material use; bend radius constrains the inside corner.",
  "assumptions": [],
  "validated_facts": [],
  "limitations": []
}
```

Candidate status and selection are separate. A candidate can be selected for
inspection without becoming accepted.

## 9. Focused user questions

A question card shows:

- why the information matters;
- two or three structured options where possible;
- a free-text answer when necessary;
- what the Agent will do after the answer;
- whether proceeding with an assumption is allowed.

Do not display unrelated requirement fields.

## 10. Build & Evaluate feedback

Execution shows:

- candidate identity;
- execution path and backend;
- pending/running state;
- concise completed operations;
- measured result;
- current Agent response.

Failure shows:

- what failed;
- whether a diagnostic preview exists;
- whether the Agent will repair automatically;
- whether user input or a capability change is needed;
- retained evidence.

## 11. Validation summary

Group facts as:

- verified;
- assumed;
- unverified;
- unsupported;
- not requested.

Example:

```text
Verified
- One valid solid
- STEP exported
- Overall width 42.0 mm

Assumed
- FDM prototype process

Unverified
- Strength under the requested load
- Servo fit
```

## 12. Part Jobs

Each Part Job shows:

- part id and engineering role;
- interface summary;
- current attempt;
- attempt count;
- accepted result;
- stale state;
- one recommended action.

Actions:

- open design;
- compare attempts;
- accept reviewable result;
- revise accepted result;
- continue next part.

Creating a Part Job is not the same as generating or accepting a part.

## 13. Assembly

Assembly page shows:

- exact accepted part-result inputs;
- reference components;
- placement, mate, joint, fastener, and clearance intent;
- assembly candidate preview;
- validation categories and limitations;
- accepted assembly result.

If accepted parts are missing, show which Part Jobs block assembly and offer the
single best next action.

## 14. Deliverables

Deliverables page groups:

- accepted part models;
- accepted assembly;
- BOM;
- drawings;
- reports.

Each item shows:

- human purpose;
- source accepted result;
- validation state;
- preview/open/download action;
- limitations.

Unaccepted Run products remain under Parts or History, not final Deliverables.

## 15. History and Run Snapshot

History shows:

- Run purpose;
- parent/child relationship;
- target Part Job or Assembly Job;
- candidate and result summary;
- accepted, superseded, failed, or diagnostic state;
- comparison entry point.

Run Snapshot is read-only. Its main action may be "Start Revision", which
creates a new child Run after confirmation.

## 16. Four-phase progress

Use a compact phase indicator:

```text
Intent — Design — Build & Evaluate — Accept & Deliver
```

It communicates orientation, not a mandatory linear gate.

The same Work may:

- return from Build to Design after an observation;
- remain in Design while several Part Jobs progress;
- enter Accept & Deliver for one part while other Part Jobs are incomplete;
- return to Design for a revision.

Do not render every internal checkpoint as a dot graph on the primary page.

## 17. Action hierarchy

At most one dominant action:

- Answer question;
- Run candidate;
- Let Agent repair;
- Review result;
- Accept result;
- Continue next part;
- Build assembly;
- Generate package.

Secondary actions:

- compare candidates;
- inspect measurements;
- change strategy;
- stop episode;
- open history.

Advanced actions:

- raw artifact;
- model source;
- validator payload;
- episode trace.

## 18. Consequential actions

Confirmation is required when:

- changing an accepted upstream decision;
- accepting or replacing a result;
- starting revision or rework;
- changing active design lineage;
- starting a long or costly execution;
- generating or replacing an assembly or deliverable package.

The confirmation explains user consequences, not internal filenames.

## 19. Action feedback

Every enabled mutation or execution follows:

```text
idle
  -> confirming when needed
  -> pending
  -> Agent/backend activity
  -> refreshed domain state
  -> verified success or failure
```

Success requires a visible state change such as:

- candidate preview appeared;
- validation status changed;
- accepted pointer changed;
- Part Job attempt was added;
- assembly became ready;
- deliverable package appeared.

## 20. Empty and unsupported states

Good:

```text
No model candidate exists yet.
The Agent is ready to explore a first geometry strategy.
[Start design]
```

```text
Assembly is waiting for two accepted parts:
- base
- upper_link
[Continue base design]
```

Bad:

- unavailable;
- missing artifact;
- route not supported;
- blank graph.

## 21. Legacy Workflow Cockpit

The current NiceGUI Workflow graph remains temporarily available under
Diagnostics.

It may receive:

- safety fixes;
- migration adapters;
- regression maintenance.

It should not receive new product phases, review cards, or primary navigation
importance.

## 22. View-model target

```json
{
  "work": {},
  "phase": "design",
  "objective": {},
  "recommended_action": {},
  "conversation": [],
  "agent_activity": {},
  "current_candidate": {},
  "preview": {},
  "validation_summary": {},
  "alternatives": [],
  "part_jobs": [],
  "assembly_job": null,
  "deliverables": [],
  "history_summary": {},
  "advanced": {}
}
```

The view model consumes explicit domain state and artifact references. It does
not recursively infer trusted state from filenames.

## 23. Visual acceptance scenarios

Minimum scenarios:

1. New Work before design.
2. Agent asks a focused question.
3. Candidate model program executing.
4. Geometry available with verified and unverified facts.
5. Validation failure followed by Agent repair.
6. Two candidate comparison.
7. Reviewable versus accepted part result.
8. Multiple Part Jobs with mixed states.
9. Assembly waiting for accepted parts.
10. Assembly result with explicit validation scope.
11. Deliverable package with STEP, BOM, and drawing.
12. Immutable Run Snapshot and start-revision action.
13. Desktop, 1024px, and 390–430px layouts.
14. English and Chinese primary paths.

## 24. Definition of done

A target Workbench slice is usable when:

- geometry and Agent progress dominate the first viewport;
- the user understands the current candidate and next action;
- focused questions explain why they matter;
- observation-driven repair is visible;
- trust state is not inferred from file presence;
- acceptance and revision preserve history;
- primary actions have verified postconditions;
- the affected journey passes automated and real-browser checks.
