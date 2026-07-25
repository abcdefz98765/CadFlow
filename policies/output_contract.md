# Output and Publication Policy

## Trust rule

Files are not product state. Every output has an artifact identity, trust role,
source Run, candidate or accepted-result reference, schema/version metadata,
and controlled viewer or download policy.

Trust roles are:

- candidate;
- observation;
- reviewable result;
- accepted result;
- deliverable;
- diagnostic.

## Candidate publication

A candidate becomes reviewable only after its source or contract validates,
controlled execution completes, requested geometry/output checks run, and the
result manifest is written successfully.

Failed or blocked candidates retain source, observations, reports, and logs but
must not expose partial geometry as a trusted product.

## Product precedence

STEP is the current primary exchange geometry. STL is a derived mesh. Native or
source models, assembly files, BOMs, and drawings are included only where the
selected backend and validation profile support them.

Output presence alone does not prove intent match or engineering readiness.

## Deliverable Package

A Deliverable Package resolves exact accepted Part and Assembly result
identities. It may contain:

- source or native model;
- STEP and requested derived formats;
- accepted assembly;
- BOM;
- drawings;
- evaluation and limitation reports;
- manifest and provenance.

It never searches for a vaguely named latest file and never packages an
unaccepted candidate.

## Execution containment

Model-program candidates execute only in isolated candidate storage through the
Tool Broker. Writes outside the allowlist, network access, shell, subprocess,
credentials, and dynamic dependency installation are prohibited by default.

## Legacy compatibility

Current deterministic Runs may still contain:

```text
input_ir.json
model.py
model.step
model.stl
report.json
report.md
preview.png
agent_trace.json
logs/runtime.json
```

Legacy readers remain supported during migration, but new product state should
use manifests and explicit artifact references rather than recursive filename
discovery.
