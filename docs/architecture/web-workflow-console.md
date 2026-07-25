# Web Workflow Console Architecture

## Authority

This document defines the current technical architecture of the local Web Workflow Console.

It does not redefine CadFlow's product objects or checkpoint responsibilities. Those are owned by:

- `cadflow-canonical-product-architecture.md`

User-facing information hierarchy and interaction rules are owned by:

- `../ux/product-usability-principles.md`
- `../ux/workflow-cockpit-design-spec.md`

## Responsibility

The Web Console is a local workflow cockpit over CadFlow's file-backed services.

It is responsible for:

- selecting a Workspace and Work;
- projecting Current Work from the active lineage;
- showing immutable Run Snapshots;
- rendering workflow checkpoints, Parts, History, reviews, and artifacts;
- collecting controlled user input and confirmation;
- dispatching allowlisted backend actions;
- showing pending, verified success, and failure feedback.

It is not:

- a browser CAD editor or geometry kernel;
- a general filesystem browser;
- an arbitrary Python, shell, or CadQuery execution surface;
- a second source of workflow truth;
- a provider transcript or debug console as the primary experience.

## Runtime layers

    NiceGUI presentation
      -> workflow page view model
      -> Work and stage projections
      -> WorkflowConsoleActions / WorkflowConsoleBackend
      -> StageRunner or bounded Agent Episode
      -> contract and policy validation
      -> deterministic CAD / review / revision pipelines
      -> file-backed artifacts, Work manifest, and lineage

Authority flows downward. Presentation code must not infer or mutate business state independently.

## Sources of truth

- Workspace configuration and the Work index live in the Workspace.
- Mutable product decisions and pointers live in the Work manifest.
- Execution evidence and outputs live in immutable Run artifacts.
- User edits live in validated, versioned override artifacts.
- Reviews are append-only; compatibility materializations may exist only for an established pipeline consumer.
- Browser component state is temporary interaction state only.

The console may build sanitized projections and indexes. It must not create a parallel workflow database or treat the selected browser tab as authoritative state.

## Current Work and Run Snapshot

### Current Work

Current Work is the default actionable view. It aggregates:

- active root and leaf pointers;
- accepted upstream artifacts across the active lineage;
- selected candidate and active overrides;
- Part Jobs and accepted result pointers;
- current checkpoint states;
- recommended next action;
- deliverables and limitations.

Every projected artifact retains source Run and stage provenance.

### Run Snapshot

Run Snapshot renders one immutable execution attempt exactly as recorded.

Normal mutations are disabled. The user may inspect artifacts, return to Current Work, compare attempts, or explicitly create a new rework attempt.

`latest_attempt_run_id` is audit information. It must not silently choose Current Work state.

## View-model boundary

`workflow_page_view_model.py` is the presentation contract for the primary Workflow route.

The view model owns:

- `current_work` versus `run_snapshot` mode;
- active lineage summary;
- graph topology and node semantics;
- selected-stage causal detail;
- artifact view contracts;
- action targets, categories, availability, and expected postconditions;
- action inventory for verification.

The renderer must not recompute business status from filenames, CSS classes, the currently selected Run, or local component state.

The primary Workflow route uses one v2 rendering and action-dispatch path. Legacy renderers may remain only as isolated compatibility helpers and must not be reachable from the main route.

## Action boundary

Every visible action is one of:

- navigation;
- structured input;
- workflow command;
- disabled future action.

An enabled action must declare:

- action key and category;
- target Work, Run, Stage, and part where applicable;
- whether it creates a Run;
- whether it updates Work pointers or active lineage;
- required form or confirmation;
- expected user-visible postcondition;
- localized label, help text, and disabled reason.

The action target comes from the action contract. A page-level `selected_run_id` must not be used as a universal mutation target.

## Runtime action lifecycle

Consequential actions use a shared lifecycle:

    idle
      -> confirming when required
      -> pending
      -> backend execution
      -> refreshed backend projection
      -> postcondition verification
      -> succeeded or failed

Requirements:

- pending feedback appears immediately;
- duplicate clicks are rejected;
- long-running work does not silently freeze the interface;
- success requires postcondition verification, not merely a returned function value;
- success and failure remain visible in a page-level feedback panel;
- failure preserves the current Work and user input;
- the refreshed page shows the changed workflow state and next action.

## Safe backend surface

`WorkflowConsoleBackend` and `WorkflowConsoleActions` are authoritative for local UI operations.

Public operations accept safe ids and allowlisted artifact names. They do not accept arbitrary filesystem paths.

Current action families include:

- requirement clarification and validated overrides;
- candidate selection through Assembly Plan override;
- Part Request, Part Review, and Reviewed Handoff;
- reviewed single-part create;
- Part Result Review and explicit user approval;
- append-only Stage Review;
- Work-level Workflow Review;
- explicit rework;
- controlled artifact reads and product downloads.

The reviewed single-part create path remains:

    reviewed_part_handoff
      -> part_execution_request
      -> bounded create_part_ir episode / AgentAdapter
      -> cad_ir_draft
      -> local CAD IR validation
      -> deterministic run_ir_pipeline or typed safe block

It does not batch-generate parts, generate a complete assembly, solve assembly constraints, or execute provider-generated code.

## Artifact access

Artifact reads and downloads are allowlisted and path-safe.

User-facing artifact contracts include:

- purpose-oriented display name;
- filename as secondary metadata;
- artifact role: accepted input, attempt output, final output, or diagnostic evidence;
- trust status: accepted, reviewable, validated evidence, or untrusted;
- source Work, Run, and Stage;
- original or override source type;
- validation status;
- preview and download capability;
- read-only or controlled-edit state.

JSON, Markdown, and text use controlled viewers. STEP/STL are opened through product preview/download paths. Arbitrary directory browsing is not exposed.

Repeated filenames are grouped by purpose and provenance rather than displayed as indistinguishable rows.

Work Products and Deliverables contain only files reached through explicit
approved `accepted_part_results` pointers. A STEP/STL file in an unapproved Run
is reviewable attempt output, not a Work deliverable. Files from a failed Run
are diagnostic evidence even when retained by legacy data.

## Overrides and reviews

Original Run artifacts remain immutable.

Controlled edits:

- write a versioned override;
- pass artifact-specific validation;
- preserve the original artifact;
- record reason and affected downstream stages;
- mark dependent stages stale when upstream meaning changes.

Stage reviews are append-only under stage-specific review directories. A latest `stage_review.json` materialization may remain for rework compatibility, but it must not erase history.

Approving a part result updates the Work-level `accepted_part_results` pointer only after an explicit user decision. It does not rewrite the child Run or imply complete assembly generation.

## Localization

When the language switch is present, all primary labels, actions, tooltips, dialogs, pending states, success and failure messages, validation feedback, and disabled reasons use the centralized catalog.

Internal enums and artifact contents may remain unchanged, but the primary UI must not fall back to backend action names, `Available`, raw enums, or English-only help text in Chinese mode.

## Security defaults

- Bind local services to `127.0.0.1` by default.
- Prefer explicitly configured Tailnet access for remote use.
- Do not enable public exposure or Funnel by default.
- Do not expose secrets, provider payloads, transcripts, arbitrary paths, or unrestricted execution endpoints.
- STEP remains the primary CAD product; STL preview is a secondary inspection aid.

## Verification

Automated tests protect contracts, targets, status projection, immutable Snapshot behavior, localization coverage, and action postconditions.

A Workflow UI change is not product-usable until the affected journey is also exercised in a real browser. Readiness reporting must distinguish implemented, automated-tested, manually verified, and production-usable.
