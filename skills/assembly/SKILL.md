# Assembly Skill

## Responsibility

Create and revise an Assembly Job from exact accepted Part Job results.

## Actions

- resolve accepted part inputs and interface definitions;
- propose placements, mates, constraints, and assembly sequence;
- evaluate interference, degrees of freedom, clearance, access, and alignment
  where deterministic tools exist;
- revise the assembly or request changes to a Part Job;
- prepare a reviewable assembly result.

## Outputs

Assembly intent, exact input manifest, placement/constraint graph, candidate
assembly products, evaluation evidence, limitations, and revision requests.

## Boundaries

The skill does not consume ambiguous "latest" files, mutate accepted parts,
generate missing parts as a hidden side effect, accept its own assembly, or
claim fit, motion, tolerance, strength, or serviceability checks that did not
run.

## Current gap

Current code has planning and validation fragments but no first-class Assembly
Job lifecycle, accepted assembly pointer, or production assembly deliverable.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/workflow_contract.md`
