# Agent Workbench Web Architecture

## Authority

This document defines the target local Web architecture and migration boundary
for the existing NiceGUI Workflow Console.

Read:

- `cadflow-canonical-product-architecture.md`
- `../ux/product-usability-principles.md`
- `../ux/workflow-cockpit-design-spec.md`
- `../status/current-product-readiness.md`

## Target responsibility

The Web app is an Agent CAD workbench over CadFlow domain services.

It is responsible for:

- selecting a Workspace and Work;
- starting or continuing a Design Episode;
- showing focused conversation and Agent activity;
- showing part and assembly previews;
- presenting candidates, observations, and limitations;
- managing Part Jobs and Assembly Job;
- collecting explicit acceptance and revision decisions;
- opening accepted-result-derived deliverables;
- showing History and immutable Run Snapshots;
- exposing legacy Workflow and raw evidence under Diagnostics.

It is not:

- the source of Work or Run truth;
- a browser-side geometry kernel;
- an unrestricted provider terminal;
- a general filesystem browser;
- an automatic engineering-release authority.

## Target runtime layers

```text
Agent Workbench presentation
  -> Workbench view model
  -> Work / Part Job / Assembly Job domain services
  -> Episode Orchestrator
       -> Context Broker
       -> Tool Broker
       -> provider adapter
  -> candidate execution and validators
  -> artifact and accepted-pointer store
```

Presentation code does not infer business state from filenames, CSS, selected
tabs, or local browser state.

## Domain sources of truth

- Workspace manifest and configuration;
- Work manifest and explicit object references;
- Part Job attempt lists and accepted-result pointers;
- Assembly Job attempts and accepted-result pointer;
- immutable Run artifact index;
- Deliverable Package manifests;
- append-only user decisions.

Recursive artifact discovery is compatibility behavior only.

## Primary view model

The target Workbench view model provides:

- Work and phase context;
- current design objective;
- recommended action;
- focused conversation;
- Agent activity and episode state;
- current candidate and alternatives;
- preview contract;
- validation and limitation summary;
- Part Jobs;
- Assembly Job;
- Deliverable Packages;
- compact history;
- advanced diagnostics.

Every action declares:

- action key and localized meaning;
- target Work, Part Job, Assembly Job, Run, or candidate;
- required confirmation or input;
- whether it invokes an Agent or tool;
- expected visible postcondition;
- recovery behavior.

## Action lifecycle

```text
idle
  -> confirming
  -> pending
  -> episode or domain action
  -> observation / result
  -> refreshed projection
  -> postcondition verification
  -> succeeded or failed
```

Long Agent Episodes may emit compact progress events without exposing raw
provider traffic or private reasoning.

Duplicate execution and acceptance actions are rejected.

## Preview boundary

Preview contracts use controlled product artifacts.

They identify:

- candidate, reviewable, accepted, or diagnostic state;
- source Run and Part/Assembly Job;
- model type and available viewer;
- measurements;
- comparison target where supported;
- limitations.

The browser never receives arbitrary filesystem paths.

## Tool and provider boundary

The Web app may:

- start an episode;
- answer a structured Agent question;
- request stop;
- invoke allowlisted domain actions.

It may not:

- send arbitrary shell or Python to the host;
- grant a provider direct filesystem or process access;
- bypass the Tool Broker;
- mark provider claims as validator facts;
- accept results without a user action.

## Current NiceGUI migration

The existing `ai_native_cad.workflow_console` remains operational during
migration.

Classify current surfaces:

- Workspace and Work selection — preserve and adapt;
- Current Work / Run Snapshot — preserve;
- controlled artifact viewer — preserve under Advanced/Diagnostics;
- action pending and postcondition verification — preserve;
- fixed dot Workflow graph — move to Diagnostics;
- stage-specific review forms — retain only for legacy Runs;
- Parts and History — migrate to first-class domain objects;
- provider configuration — preserve but do not imply Agentic capability.

The primary route must not switch to the target Workbench until:

- the M2 Design Episode has a real handler;
- candidate preview and observation state are available;
- acceptance has an explicit domain target;
- legacy Runs remain reachable.

## Artifact access

Reads and downloads remain allowlisted and path-safe.

User-facing artifacts are organized by:

- purpose;
- trust role;
- source result;
- validation state.

Raw model source is visible only in Advanced and never directly executable from
an arbitrary editor action.

## Localization

Primary English and Chinese experiences include:

- Agent action summaries;
- questions and assumptions;
- candidate and validation state;
- action consequences;
- pending, success, failure, and recovery;
- disabled and unsupported reasons.

Backend keys and raw enums are not primary labels.

## Security

- bind local services to `127.0.0.1` by default;
- prefer explicit Tailnet access for remote use;
- do not enable public exposure by default;
- do not expose secrets, provider payloads, arbitrary paths, or unrestricted
  execution;
- sandbox model-program candidates outside trusted Work product locations;
- publish only locally validated result artifacts.

## Verification

Automated tests protect:

- domain action targets;
- Current Work and Run Snapshot boundaries;
- path-safe artifact access;
- episode and candidate state projection;
- action postconditions;
- acceptance semantics;
- localization contracts.

Real-browser checks prove:

- geometry preview priority;
- focused question and response;
- pending execution and Agent repair;
- validation and limitation clarity;
- reviewable versus accepted result;
- Part Job and Assembly Job progression;
- desktop and narrow layouts.

The current legacy console remains `partial` until migrated; passing its
existing tests does not prove Agent Workbench usability.
