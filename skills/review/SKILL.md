# Review Skill

Purpose: review generated parts and assemblies according to `check_level`.

L0 is currently supported. L1 should add maker checks such as wall thickness,
clearance, printability, and obvious assembly risks. L2+ remains reserved until
the lower levels are reliable.

Part review is a closed loop, not only an export check:

- preflight: requirement/spec completeness and basic design intent
- geometry: non-empty model, positive volume, single solid, measurable dimensions
- export: requested STEP/STL files exist and are non-empty
- intent match: verified, assumed, and unverified request items are separated

For L0, continue after non-blocking issues when a model can be generated, but
mark the review clearly. Do not report feature-level intent as verified unless
there is an explicit measurement or recognition rule.

The global check-level definitions live in `policies/check_levels.md`.
Workflow handoff boundaries and artifact responsibilities live in
`docs/workflow_contract.md`.
