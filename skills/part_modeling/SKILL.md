# Candidate Build Skill

Compatibility directory: `part_modeling/`.

## Responsibility

Build a validated geometry candidate through controlled backend capabilities and
return products plus measured execution evidence.

## Inputs

- a validated structured feature graph, sandboxed model program candidate, or
  legacy CAD IR;
- execution profile and output policy;
- resource and evaluation budgets.

## Outputs

Build status, normalized source or contract, STEP/STL when requested and
supported, geometry metrics, validation reports, logs, and typed failure
observations. Contract-only execution explicitly does not promise geometry
exports.

## Behavior

- execute only through the Tool Broker;
- enforce preflight, isolation, budgets, and output allowlists;
- inspect non-empty geometry, solid count, volume, bounds, and requested exports;
- preserve failed candidate evidence without publishing it as trusted output;
- return observations so the Agent may revise or stop.

## Boundaries

This skill does not redesign intent, grant unrestricted host authority, silently
replace a candidate, approve a result, or claim checks that did not run.

## Current gap

Current implementation deterministically executes legacy CAD IR and backend
helpers. The sandboxed model-program profile and generalized feature graph are
not yet implemented.

## References

- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
