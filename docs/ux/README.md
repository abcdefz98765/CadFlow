# CadFlow UX Design Pack

The target experience is an Agent CAD workbench. The former fixed Workflow
Cockpit is a compatibility/diagnostic surface during migration.

Read in this order:

1. `../architecture/cadflow-canonical-product-architecture.md`
2. `product-usability-principles.md`
3. `workflow-cockpit-design-spec.md`
4. `../architecture/web-workflow-console.md`
5. `../status/current-product-readiness.md`

The design must prioritize:

- user objective;
- geometry or assembly preview;
- understandable Agent activity;
- focused decisions;
- validation and limitations;
- Part Jobs and accepted results;
- one recommended action.

Raw artifacts, fixed checkpoint graphs, provider details, lineage ids, and
diagnostics are secondary.

A UI change is not product-usable only because automated tests pass. Exercise
the affected Agent, geometry, action, failure, and recovery journey in a real
browser and report verification honestly.
