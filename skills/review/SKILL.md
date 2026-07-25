# Evaluation Skill

Compatibility directory: `review/`.

## Responsibility

Interpret build evidence, run allowlisted checks, compare candidates, and tell
the user what is measured, assumed, unverified, failed, or blocked.

## Actions

- inspect exact candidate and accepted-context evidence;
- request geometry, interference, dimensional, export, or policy checks;
- compare alternatives against current objectives;
- explain limitations and recommend revise, accept, inspect, or stop;
- identify the smallest useful next question or experiment.

## Outputs

Scoped evaluation artifacts, candidate comparison, assurance status,
limitations, and a recommended next action.

## Boundaries

Evaluation does not mutate geometry as a hidden side effect, accept results,
expose secrets or absolute paths, infer success from file presence, or promote a
single part as a complete assembly.

## Assurance

Claims must identify the evidence tier: exploratory, engineering, or release.
Release wording is allowed only when all configured release checks actually
passed.

## Current gap

Current reviews are checkpoint-oriented summaries. Target Evaluation is callable
inside a design episode and can guide Agent-selected revision.

## References

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../policies/check_levels.md`
