# CadFlow Agent Workbench Design Specification

Status: target UX specification.

The filename is retained for link compatibility.

The former fixed checkpoint sequence is no longer the primary product journey, but the Workflow graph remains a first-class product view and an important part of how users understand a Work.

CadFlow should evolve the existing NiceGUI shell, Overview, Workflow graph, Parts, History, Run Snapshot, viewer, action feedback, i18n, and responsive components rather than replacing them with a parallel UI system.

## 1. Product experience

CadFlow is a design workbench where the user collaborates with an Agent and sees the Work evolve.

The product should make three things immediately clear:

- what the user asked and what the Agent is designing;
- what the current geometry/result actually is;
- where the Work is in its overall state graph and what happens next.

A user should not need to understand internal Run ids, artifacts, Broker details, hashes, sandbox profiles, or provider transport metadata to follow the normal workflow.

## 2. Primary navigation

A selected Work has:

- **Overview / Design** — what matters now;
- **Workflow** — how the Work got here, its branches/states, and available transitions;

These are the two persistent primary destinations. **Parts** is shown as a
contextual destination when a Work has meaningful decomposition (normally more
than one Part Job). **History** is a subordinate immutable-evidence destination
when Runs exist, not an equal-priority step in the normal design journey. Their
routes and mature inspection components remain available.

Overview is the default landing page. Workflow is not merely Diagnostics; it is the first-class map of the Work.

Advanced/Evidence is progressive disclosure inside these views, not a competing product surface.

Assembly and Deliverables become primary navigation only after those real capabilities exist.

## 3. Overview and Workflow are complementary

### Overview / Design answers

- What did I ask for?
- What is the Agent proposing or doing now?
- What geometry exists?
- What is verified, assumed, or unverified?
- Do I need to answer/review anything?
- What is the single recommended next action?

### Workflow answers

- What has happened in this Work?
- Which Part Jobs and attempts exist?
- What was asked/answered?
- What failed or was repaired?
- Which result is reviewable/accepted/stale?
- Where did a revision branch?
- What is blocked or waiting?
- What can I do next?

Both views derive from the same Work/Run/Part Job state and must never contradict each other.

## 4. Dynamic Workflow graph

Workflow is a live state graph, not a script.

The Agent is not required to execute nodes in a fixed UI-defined sequence. The graph is produced after/because durable product state changes.

Workflow is both the orientation surface and the primary command surface for
the Current Work. Selecting a meaningful node should expose a concise
interaction projection: current state, why it matters, whether attention is
required, one dominant valid action, secondary valid actions, relevant
result/Agent/validation evidence, and any honest unavailable reason. These
actions call existing backend/orchestrator commands; the graph is not the
command engine or state owner.

**Current Attention** is a derived presentation concept, not a global current
node. A single-Part Work may have one attention node; parallel Part Jobs may
simultaneously expose several waiting, reviewable, blocked, or active nodes.
Selection, attention, actions, and layout are not persisted.

Current Attention is rendered as an index, not a second graph or action
console. A single-Part Work uses one compact current-task row; a multi-Part
Work uses a compact per-Part list whose items select the corresponding graph
node. The selected-node inspector remains the precise Workflow command
surface.

The graph should be built from existing:

- Work state;
- Part Jobs;
- Runs/lineage;
- persisted user questions/answers;
- Agent design/result evidence;
- validation/recovery evidence;
- reviewable and accepted-result references;
- later Assembly/Deliverable objects when they exist.

Do not create a second browser/domain state model for the graph.

## 5. Four phases are visual grouping

Keep the canonical phases:

```text
Intent
Design
Build & Evaluate
Accept & Deliver
```

Use them as orientation, lanes, regions, headings, or subtle backgrounds around graph content.

Do not represent the complete Workflow as four phase dots.

Do not turn the phases into a four-step wizard.

A Work may move between phase regions non-linearly.

## 6. Graph topology adapts to the Work

### Simple single-Part Work

A simple graph might look conceptually like:

```text
Request
  -> Part Job
      -> Design
      -> Build / Inspect
      -> Reviewable
      -> Accepted
```

Clarification, failure, repair, or revision appears only if it actually happens.

### Multi-Part Work

When the Agent/runtime genuinely creates several Part Jobs, the graph may branch:

```text
Request / Design
      |
      +-- Part A -> attempts/results
      +-- Part B -> attempts/results
      +-- Part C -> attempts/results
```

Assembly may appear only when an Assembly Job exists and its prerequisites are real.

Do not draw future Parts/Assembly merely because a target architecture mentions them.

## 7. What deserves a graph node

Graph nodes represent meaningful durable product states or decisions.

Useful examples:

- user request;
- focused clarification;
- user answer;
- design/decomposition decision;
- Part Job;
- attempt/revision branch;
- meaningful build/validation state;
- failure/recovery point;
- reviewable result;
- accepted result;
- later Assembly or Deliverable result.

Do not create nodes for every provider call, context lookup, log line, token event, or low-level tool invocation.

Those belong in Agent Output or Advanced.

## 8. Edges show state transition

Edges should communicate meaningful transitions such as:

- created;
- decomposed;
- asked / answered;
- generated;
- validated / failed;
- repaired;
- reviewable;
- accepted;
- revised;
- stale/superseded;
- assembled.

Keep the vocabulary small and product-language-first.

Do not build a generic workflow DSL just to configure edges.

## 9. Dot/shape semantics

Reuse the established dot graph visual vocabulary where possible.

Shape or decoration may distinguish broad semantic kinds such as:

- ordinary state;
- user decision;
- Part/Assembly object;
- blocked/failure;
- reviewable;
- accepted.

Color indicates status. Selection is separate from status.

Do not create a large taxonomy of node classes unless real Works require it.

## 10. Node interaction

Clicking a node selects an existing product object/state for inspection.

The detail surface should reuse existing content:

- Your Request;
- Agent Design;
- Agent Output/activity;
- clarification and answer;
- Part Job/attempt;
- geometry preview;
- validation;
- reviewable/accepted result;
- recovery detail;
- read-only Run Snapshot.

Selecting a node is presentation state only.

## 11. Revision / “go back” semantics

Users may want to return to an earlier design/result and change it.

Do not destructively roll back history.

The UX should express this as:

```text
Select earlier state
-> Start revision from here
-> create child/new attempt Run
-> keep prior branch visible
```

The graph should make the new branch understandable.

Existing accepted results remain until explicitly replaced by acceptance of another result.

Use wording such as **Start new version from this result**. Do not promise
arbitrary-node replay: only reviewable/accepted results and other states backed
by an existing safe domain command may branch. Unsupported historical nodes
remain inspection-only with a clear explanation.

## 12. Overview / Design composition

The existing Work Overview remains the default landing surface.

Recommended information order:

1. Work title and concise current state;
2. Your Request;
3. Agent Design;
4. current recommendation/question;
5. geometry preview when available;
6. Agent Activity / What happened;
7. current result and validation/limitations;
8. Part Job summary;
9. compact Workflow status / entry into full Workflow;
10. Advanced evidence.

Do not make internal artifact names the information architecture.

Overview normally has one dominant Work-level action. Agent Activity explains
progress and Part cards navigate to their current graph state; neither repeats
that dominant command. Empty Agent Design, geometry, and Agent Output states
stay compact until durable evidence exists.

## 13. Agent Design, Activity, and Output

Keep these distinct.

### Agent Design

What the Agent currently proposes to build, based only on persisted concise design evidence.

### Agent Activity

What is currently happening in product language.

### Agent Output

What the external Agent explicitly returned to CadFlow, sanitized and readable for debugging/recovery.

Do not expose private chain-of-thought or credentials.

Agent Output/technical evidence may be expandable and should not dominate the normal page.

## 14. Geometry preview

Once geometry exists, it is a primary visual anchor.

Reuse the existing viewer and presentation path.

Useful adjacent facts:

- overall dimensions/bounding box;
- solid count;
- relevant measured properties;
- reviewable/accepted status.

Do not display raw file paths by default.

## 15. Focused clarification

When the Agent asks a material question, the question belongs inside the current Work story.

Show:

- question;
- why it matters when available;
- answer input;
- submitted answer afterward;
- what happened after resume.

The question/answer remains inspectable after the Work moves forward.

## 16. Build, validation, and repair

A user should be able to tell:

- what candidate/build was attempted;
- whether geometry was produced;
- what validation found;
- whether the Agent repaired automatically;
- whether user action is required.

Validation facts are grouped honestly as:

- verified;
- assumed;
- unverified;
- unsupported;
- not requested.

## 17. Recovery

Blocked is not an endpoint label; it is an explanation and next step.

A recovery surface should answer:

- What happened?
- Why did it stop this time?
- What had already succeeded?
- What was the last meaningful Agent action/observation?
- Who can resolve it?
- What is the recommended action?

Past clarification/recovery history should not disappear when another stop occurs.

Unknown/new typed stop reasons should still expose the real trusted reason/evidence rather than collapsing to generic safety text.

## 18. Part Jobs

Part Jobs should be understandable both in Parts and Workflow.

Each Part Job shows:

- name/role;
- interfaces/purpose where useful;
- current attempt and attempt count;
- current state;
- reviewable result;
- accepted result;
- stale/block state;
- recommended action.

Part creation, candidate generation, and acceptance are different events.

## 19. History and Run Snapshot

History is immutable evidence, not a second workflow.

Run Snapshot is read-only.

A historical node/Run may offer `Start Revision`, which creates a new attempt and returns the user to Current Work.

## 20. Examples and developer fixtures

Normal users should see Product Examples with clear teaching intent.

Developer/UX/recovery fixtures remain available behind developer/Advanced visibility and state what they test.

Fixtures must not pollute the normal Works catalog or redefine product behavior.

## 21. Settings

Settings should answer whether CadFlow can actually use the configured Provider and local CAD runtime.

Credential source may be shown without value.

Transport/security implementation details stay secondary.

## 22. Progressive disclosure

Primary UI contains information required to:

- understand state;
- decide;
- verify the current result.

Advanced contains:

- Run/Episode ids;
- raw/sanitized structured evidence;
- provider/model details;
- artifact paths;
- source/validator/Broker evidence;
- runtime/sandbox/attestation/hashes.

Debug evidence remains accessible without turning the product into a monitoring console.

## 23. Interaction lifecycle

Every enabled write/execution action has visible closure:

```text
idle
-> confirmation when consequential
-> pending/running
-> refreshed domain state
-> visible success/failure
-> next/recovery action
```

Success is a real state change, not merely a returned function value.

## 24. Responsive behavior

Reuse the existing responsive system.

At desktop, the normal Current Work Workflow uses a graph-and-inspector
master-detail layout so node selection updates nearby detail without a long
scroll. Phase labels remain compact orientation above the topology and do not
reserve four equal empty lanes.

At 1024px and mobile, prioritize:

- current graph/state orientation;
- selected node detail;
- geometry;
- primary action.

At narrower widths graph and inspector stack. The topology may scroll within
its own surface rather than forcing page-level horizontal overflow or
compressing every label beyond readability.

## 25. Avoid over-designing Workflow

The Workflow goal is clarity, not a general workflow platform.

Do not introduce without a demonstrated need:

- graph database;
- BPMN engine;
- generic workflow DSL;
- plugin-defined node taxonomies;
- separate graph persistence;
- speculative Assembly/Deliverable states;
- a second action/state framework.

Prefer a small projection builder over the existing domain model and reuse the current graph renderer/components.

Implement current single-Part behavior cleanly first, but shape the projection so real multi-Part branches can appear naturally when the runtime creates them.

## 26. Definition of done for a Workflow slice

A Workflow slice is usable when:

- the user can understand the Work topology in a few seconds;
- the active state is obvious;
- Part Jobs/attempts/results are represented from real state;
- clarification/failure/revision branches remain understandable;
- clicking a dot opens useful detail;
- starting from an earlier state creates a new branch rather than rewriting history;
- Overview and Workflow agree;
- internal Agent turns are not mistaken for product stages;
- the graph remains simpler than the underlying audit evidence;
- desktop, 1024px, and mobile are manually verified.
