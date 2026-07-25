# Design Skill

Compatibility directory: `planning/`.

## Responsibility

Explore an engineering solution, compare meaningful alternatives, decompose
parts and interfaces, and choose a reasoned next candidate.

## Actions

- inspect allowlisted Intent and accepted Work context;
- choose single-part, multi-part, assembly, or reference-only scope;
- propose and compare concepts;
- define functions, datums, interfaces, dependencies, and evaluation targets;
- create or revise Part Job and Assembly Job proposals;
- request Geometry, Evaluation, or focused user input.

## Outputs

Design Briefs, concept alternatives, interface definitions, candidate Part
Jobs, Assembly Job intent, decisions, assumptions, and recommended next action.
Legacy `planning_artifact.json` and `assembly_plan.json` remain readable.

## Boundaries

The skill does not treat current backend templates as the design space, run
uncontrolled code, claim unperformed checks, or accept its own recommendation.
It may choose a geometry strategy but delegates candidate realization through
the Tool Broker.

## Current gap

Current planning is predominantly a fixed checkpoint. Target behavior requires a
provider-controlled episode with candidate comparison and tool observations.

## References

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
