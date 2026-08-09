# CadFlow Agent Rules

Read this file before changing the repository.

## Mandatory product model

Before changing product behavior, UI, Agents, skills, knowledge, artifacts,
lineage, CAD execution, assembly, or deliverables, read:

- `docs/FINAL-PRD.md`
- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/status/current-product-readiness.md`
- `docs/ux/workflow-cockpit-design-spec.md`

CadFlow is an Agent-first CAD design workbench.

Canonical objects:

- Workspace contains Works and local configuration.
- Work is one mutable user-facing engineering objective.
- Run is one append-only attempt and audit record.
- Part Job owns one intended part, multiple attempt Runs, and one accepted-result pointer.
- Assembly Job is optional and consumes exact accepted part results when assembly capability exists.
- Deliverable Package is optional and is derived only from accepted results when deliverable capability exists.
- Current Work is actionable; Run Snapshot is immutable.
- Active design lineage and accepted results are distinct.

Canonical user phases:

- Intent
- Design
- Build & Evaluate
- Accept & Deliver

These four phases are semantic groupings for the Work. They are not a four-step wizard and they are not the complete Workflow graph.

## Workflow is a live Work state graph

The Workflow is not a script the Agent must follow.

The Workflow is a live projection of durable Work state, lineage, user decisions, Part Jobs, attempts, results, recovery points, and available transitions.

The Agent chooses design actions inside its allowed capability boundary. CadFlow controls durable state changes and side effects. The Workflow visualizes what has actually happened and what can happen next.

Important rules:

- Do not reduce Agent-first Workflow to only four phase dots.
- Use the four phases as grouping/swimlanes/orientation around the graph.
- A simple single-Part Work should produce a simple graph.
- A multi-Part Work may branch into Part Jobs when the runtime actually creates them.
- Attempts, clarification, validation failure, repair, reviewable results, acceptance, and revision may appear when they are meaningful durable states.
- Assembly and Deliverable nodes appear only when those real product objects/capabilities exist.
- Clicking a graph node should inspect the corresponding existing Work/Part/Run/result evidence rather than creating a parallel state model.
- Revisiting an earlier state means starting a new child Run/revision from that point. Historical Run evidence is never rewritten or deleted.
- Overview and Workflow are two projections of the same domain state: Overview answers “what matters now”; Workflow answers “how this Work got here and where it can go”. They must not contradict each other.

Do not build a second workflow engine, graph database, BPMN layer, generic workflow DSL, or graph-specific persistence model merely to draw the Workflow. Prefer a presentation projection over the existing Work manifest, Part Jobs, Runs, lineage, artifact references, Agent events, reviewable results, and accepted pointers.

## Product priority

Prioritize the current user loop:

1. user intent and useful Agent response;
2. clear Work/Part decomposition when needed;
3. visible Agent design and geometry;
4. understandable dynamic Workflow state;
5. build/inspection/recovery feedback;
6. explicit review, acceptance, and revision;
7. only then broaden modeling, multi-Part assembly, and deliverables based on demonstrated need.

Do not add a new `part_type` template as the default response to a general design-capability request.

Do not implement future capability merely because the architecture mentions it. Feature Graph, Assembly, Deliverables, drawings, release assurance, and additional provider/runtime abstractions are demand-driven later capabilities, not prerequisites for the current Work experience.

## Avoid over-engineering

Prefer the smallest design that closes a real user workflow.

Before adding a framework, registry, policy layer, persistence object, security mechanism, or abstraction, identify the concrete current failure or capability requirement it solves.

Do not:

- build generic infrastructure for hypothetical future providers or workflows when the current implementation can remain simple;
- add another state machine when Work/Run/Part Job state already owns the truth;
- add another audit/evidence layer when existing durable evidence is sufficient;
- turn security, attestation, hashes, Broker internals, or sandbox details into the primary product experience;
- add security controls beyond the current threat/capability need without a specific gap, exploit, or required boundary;
- pre-build Assembly, Deliverable, release, multi-user, cloud, permissions, or enterprise workflow systems before their product milestones;
- duplicate mature UI, viewer, action-lifecycle, lineage, or artifact infrastructure.

Security and evidence must remain sufficient to prevent unsafe execution, secret leakage, false publication, or silent history mutation. After those boundaries are satisfied, product usability and design capability take priority over additional defensive layers.

Reuse mature libraries and existing implementation whenever they meet the requirement.

## Agent, skill, context, and tools

For Agent or provider work, also read:

- `docs/architecture/agent-skill-knowledge.md`
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `docs/workflow_contract.md`

Rules:

- Providers are replaceable; product roles and trust boundaries are CadFlow-owned.
- Agents request semantic context, not arbitrary paths.
- Agent-selected actions must remain bounded by declared product capabilities.
- Tool Broker controls model-generated side effects.
- Provider-generated CAD source is an untrusted candidate and runs only through the existing controlled execution boundary.
- Local inspection/validation decides whether a candidate becomes reviewable.
- Only explicit user action changes accepted-result pointers.
- Persist externally returned Agent actions/answers needed for debugging and recovery, but never hidden chain-of-thought or credentials.

An episode is not Agentic merely because it has steps and artifacts. A real Agentic episode lets the provider choose useful actions/strategy and respond to observations.

## CAD execution

Current candidate paths may include:

- structured geometry contracts where implemented;
- sandboxed model programs using an allowlisted CAD API.

Both converge on the existing trust boundary:

```text
candidate
  -> controlled execution
  -> geometry inspection
  -> result validation
  -> reviewable result or typed block
```

Never:

- run provider source with unrestricted host authority;
- expose credentials or unrestricted filesystem/network/process authority to model-generated code;
- publish failed candidates as trusted products;
- claim fit, motion, strength, tolerance, DFM/DFA, GD&T, FEA, or safety checks that did not run.

Do not expand the sandbox/security architecture during a UI/Workflow milestone unless a demonstrated security defect blocks the requested behavior.

## Before changing UI

Read:

- `docs/ux/product-usability-principles.md`
- `docs/ux/workflow-cockpit-design-spec.md`
- `docs/architecture/web-workflow-console.md`

Write down:

- user goal;
- affected Work/Part Job/Run/result;
- current durable state;
- intended state transition;
- visible success/failure;
- how Overview and Workflow will represent the same state.

Default normal-user information order:

1. design objective / user request;
2. current geometry or assembly preview when available;
3. Agent design/output/progress that matters;
4. current Workflow position and one recommended action;
5. validation and important limitations;
6. Parts/results/alternatives;
7. history and Advanced evidence.

Developer/debug details remain inspectable through progressive disclosure.

## Interaction closure

No enabled write or execution action may be silent.

Required lifecycle:

- confirmation when consequential;
- immediate pending feedback;
- duplicate-action protection;
- Agent/backend activity;
- refreshed domain state;
- visible success or failure;
- clear recovery or next action.

A returned function value or present file is not proof of product success.

## Artifact and lineage invariants

- Historical Run evidence is immutable.
- Work pointers may change.
- Part/Assembly attempts remain inspectable.
- Reviewable is distinct from accepted.
- Accepted results may belong to sibling Runs.
- Starting a revision does not remove the prior accepted result.
- Upstream changes mark dependent evidence stale rather than deleting history.
- Deliverables resolve only through accepted results.
- Product state must not be inferred from filenames alone.

## Verification and documentation

Distinguish:

- implemented;
- automated verified;
- manually verified;
- production usable.

Update only documents affected by the change. Do not create a new architecture document when an existing canonical document should be edited.

Before reporting completion, confirm:

- Agent design freedom was not replaced by a closed template;
- Workflow is a projection of real domain state, not fabricated progress;
- no parallel state/workflow infrastructure was introduced unnecessarily;
- failed or unaccepted output cannot become accepted/deliverable;
- history and accepted pointers are preserved;
- security/evidence changes were proportional to a concrete requirement;
- capability claims match verification evidence;
- the implementation stayed inside the current milestone.

## Safety defaults

- Web services default to `127.0.0.1`.
- Public exposure is off by default.
- Model-program network access is off by default.
- Credentials never enter normal Work/Run evidence.
