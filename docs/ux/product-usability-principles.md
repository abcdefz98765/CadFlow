# Agent Workbench Usability Principles

## Purpose

CadFlow should help a user design and verify geometry, not teach the user its
internal workflow implementation.

The primary experience is:

```text
goal + Agent collaboration + geometry + evidence + decision
```

Artifacts, checkpoints, Runs, and diagnostics support that experience.

## Primary usability test

Without opening Diagnostics, a user should be able to answer:

1. What is the Agent designing?
2. What model, part, or assembly exists now?
3. What did the Agent assume or change?
4. What has been measured or validated?
5. What remains unsupported or unresolved?
6. Does the user need to decide anything?
7. What is the recommended next action?
8. What visible result will prove that action succeeded?

## Information order

Default order:

1. design objective;
2. current model or assembly preview;
3. Agent progress and concise decisions;
4. focused user question or recommended action;
5. validation summary and important limitations;
6. candidate alternatives;
7. Part Jobs, accepted results, and assembly readiness;
8. history, raw artifacts, and diagnostics.

Do not put lineage ids, artifact filenames, raw JSON, provider identity, or
backend action keys ahead of the design result.

## Four phases

### Intent

Show:

- the goal in the user's language;
- requested deliverables;
- important known constraints;
- focused questions only when required;
- visible assumptions for low-risk exploration.

Do not present a long requirement form by default.

### Design

Show:

- what strategy the Agent is pursuing;
- current candidate and meaningful alternatives;
- parameters, interfaces, and trade-offs that matter;
- model preview as soon as geometry exists;
- Agent activity in concise action language.

Do not expand every context request or provider call into a workflow stage.

### Build & Evaluate

Show:

- pending execution immediately;
- candidate being executed;
- geometry preview and measured facts;
- validation failure in user language;
- whether the Agent is repairing, changing strategy, asking, or stopping.

Do not claim success because a function returned or a file exists.

### Accept & Deliver

Show:

- result scope;
- verified and unverified properties;
- comparison with the currently accepted result;
- explicit Accept, Revise, Continue Part, Assemble, or Package actions as
  applicable;
- exact deliverable availability.

Acceptance is consequential and explicit.

## Conversation and activity

The workbench is conversational but not a raw transcript.

Primary conversation includes:

- user requests and focused answers;
- concise Agent decisions;
- important assumptions;
- candidate summaries;
- recovery questions.

Secondary activity includes:

- tool calls;
- context requests;
- execution events;
- validator codes;
- provider metadata.

Private chain-of-thought is never required or displayed.

## Geometry first

When a geometry result exists, preview it prominently.

The user should be able to:

- rotate and inspect;
- identify the active candidate;
- view key dimensions or measurements;
- compare before/after or candidate A/B when useful;
- understand whether the preview is part, assembly, reference, or diagnostic.

A placeholder image must not appear to be a real render.

## Candidate design

Alternatives are useful only when they differ materially.

Each candidate shows:

- concept;
- why it exists;
- important trade-off;
- current execution/validation state;
- whether it is selected, reviewable, or accepted.

Avoid generating three cosmetically different candidates merely to populate a
comparison UI.

## Agent action language

Good:

- Inspecting the failed fillet and preparing a simpler edge treatment.
- Comparing a bent-sheet bracket with a machined block strategy.
- The servo interface is underspecified; asking for the mounting pattern.

Poor:

- `repair_contract`
- `stage_8 completed`
- `route selected`
- `adapter returned`

## User decisions

Require user input when:

- a missing decision changes topology or interfaces;
- material, load, tolerance, safety, or acceptance scope is consequential;
- materially different strategies need user preference;
- an accepted result or active Work pointer will change;
- assembly or deliverable generation has important consequences.

Do not require manual approval for every internal artifact in Explore mode.

## Action lifecycle

Every write or execution action uses:

```text
idle
  -> confirming when consequential
  -> pending
  -> Agent or backend activity
  -> refreshed domain state
  -> verified success or failure
```

Requirements:

- immediate pending feedback;
- duplicate-action protection;
- progress without exposing raw logs;
- success only after visible postcondition verification;
- persistent failure with recovery;
- preserved user input.

## Trust language

Use explicit terms:

- candidate;
- execution passed;
- geometry validated;
- reviewable;
- accepted;
- deliverable;
- unverified;
- unsupported.

Do not collapse them into `completed`.

## Parts and assembly

The Part Job surface shows:

- role and interface;
- attempt count;
- current candidate;
- accepted result;
- stale dependencies;
- recommended action.

The Assembly Job surface shows:

- exact accepted part inputs;
- reference components;
- placements and constraints;
- validation scope;
- assembly result and limitations.

A single part must never look like a complete assembly.

## Deliverables

Present deliverables by human purpose:

- Upper-link STEP;
- Accepted assembly STEP;
- Assembly BOM;
- Upper-link drawing PDF;
- Validation summary.

Filename and provenance are secondary.

Only accepted-result-derived files appear as final deliverables.

## Current Work and Run Snapshot

Current Work is actionable.

Run Snapshot is immutable and audit-oriented.

The user may inspect, compare, or start an explicit revision from a Snapshot.
Normal mutation controls remain unavailable.

## Localization

When a language switch exists, the following switch consistently:

- Agent action summaries;
- questions and assumptions;
- action labels and consequences;
- pending, success, failure, and recovery;
- validation and limitation explanations;
- disabled reasons;
- empty and unsupported states.

Internal enums and model source may remain stable, but they must not become
untranslated primary explanations.

## Diagnostics

Advanced/Diagnostics may contain:

- full lineage;
- raw contracts;
- model-program source;
- validator payloads;
- episode events;
- execution logs;
- provider identity;
- audit metadata.

Never expose arbitrary filesystem browsing, secrets, or unrestricted execution.

## Legacy Workflow Cockpit

During migration the existing Workflow Cockpit remains a compatibility and
diagnostic surface.

Do not invest in additional stage cards, graph states, or review forms unless
required for:

- preserving safe operation;
- supporting migration;
- fixing a release-blocking bug;
- exposing a real new Agent-first capability.

## Definition of done

A workbench change is complete only when:

- the design result is visible;
- Agent activity is understandable;
- the recommended action is clear;
- pending, success, failure, and recovery are exercised;
- trust state and limitations are honest;
- relevant geometry or deliverables can be inspected;
- Current Work and Run Snapshot semantics remain correct;
- automated and real-browser verification are reported separately.
