# CadQuery v1 Model-Program Source Policy

Status: implemented as a static validation policy; execution unavailable.

Policy id: `cadquery_v1`.

This id versions the CadFlow source surface; it is not a claim that a CadQuery
package/toolchain version has been bound. The exact read-only CadQuery package,
Python, OCCT, and worker-image versions remain pending the enforceable sandbox
worker and must be recorded before execution can become available.

Entrypoint: `build_model(parameters)`.

The return value is intended to be a CadQuery `Workplane` or `Shape`, but only a
future isolated runtime and local geometry validators may establish that fact.
Static validation never declares geometry valid.

## Allowed source surface

- imports from `cadquery` and `math` only;
- CadQuery construction types including `Workplane`, `Plane`, `Vector`,
  `Location`, `Matrix`, `Shape`, and `Compound`;
- an explicit allowlist of sketch, feature, boolean, selector, transform, and
  workplane-chain methods;
- a small pure builtin-call allowlist for numeric conversion, iteration, and
  aggregation;
- helper functions without decorators, private names, or default-value
  evaluation;
- module and function docstrings;
- static top-level constants;
- one undecorated `build_model(parameters)` entrypoint with a return statement;
- source up to 65,536 UTF-8 bytes and 4,000 AST nodes.

The machine-readable allowlists and limits are returned by
`cadquery_model_program_policy_manifest()` and owned by
`ai_native_cad.agents.model_program_policy`.

## Rejected source surface

- any import outside `cadquery` and `math`, relative imports, or star imports;
- `cadquery.exporters`, `cadquery.importers`, `occ_impl`, plugins, or selectors;
- `open`, dynamic import, `eval`, `exec`, compile, reflection, interactive input,
  or breakpoint calls;
- non-allowlisted or dynamic calls, private/dunder attributes, decorators,
  classes, lambdas, async, generators, context managers, exception control,
  global/nonlocal mutation, or deletion;
- executable top-level statements;
- missing, duplicated, or differently shaped entrypoints;
- oversized or syntactically invalid source.

## Authority boundary

The validator uses Python AST parsing only. It does not:

- write or retain source;
- bytecode-compile, import, or execute source;
- import CadQuery on behalf of the source;
- access filesystem, environment, credentials, network, shell, or subprocess;
- create a candidate directory;
- publish geometry, change Work state, or change acceptance.

Passing static policy is necessary but not sufficient for execution. The
separate Windows sandbox capability must prove every required OS-enforced
control. It currently reports `sandbox_unavailable`, so no provider-generated
model program can run.

This policy constrains authority, not part type. It must evolve through
versioned API decisions and non-template benchmarks rather than new closed
geometry families.
