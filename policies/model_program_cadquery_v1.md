# CadQuery v1 Model-Program Source Policy

Status: static policy and an attestation-gated internal execution primitive are
implemented. No provider Episode action or reviewable publication path is
registered.

Policy id: `cadquery_v1`.

This id versions the CadFlow source surface. The internal WSL2 profile binds
Python 3.10.12, CadQuery 2.7.0, cadquery-ocp 7.8.1.1.post1, the hashed wheel
lock, worker, launcher, probes, and WSL configuration. That binding grants no
provider, publication, reviewable, acceptance, or deliverable authority.

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
separate Windows sandbox capability must be explicitly enabled and return a
fresh digest-bound attestation proving every required OS-enforced control. If
the distro, configuration, toolchain, file hashes, mounts, environment,
network, subprocess controls, or limits do not match, the Broker returns
`sandbox_unavailable` before request-side candidate evidence is created.

The resulting execution observation remains `candidate` or `diagnostic`
evidence. The registered `model_program` skill can request the tool only as the
declared delegate of `design_part`; `WorkOrchestrator` supplies all lineage and
evidence identities. Registration grants no reviewable-publication,
acceptance, or deliverable authority.

Before a successful archive is returned, the trusted worker re-imports its
exported STEP and requires a valid non-empty solid, unchanged solid count,
bounding-box agreement within 0.01 mm, and volume agreement within fixed
absolute/relative limits. Missing or inconsistent re-import evidence is a
typed invalid-output/protocol failure and cannot become product evidence.

This policy constrains authority, not part type. It must evolve through
versioned API decisions and non-template benchmarks rather than new closed
geometry families.
