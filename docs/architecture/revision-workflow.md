# Revision Architecture

## Purpose

Revision lets an Agent change a previously reviewable or accepted design without
destroying the parent evidence. It applies to parts, assemblies, and
deliverable-producing design state.

Core rule:

```text
explicit parent result
  + explicit change objective
  -> revision episode
  -> one or more candidate patches
  -> controlled build and evaluation
  -> child Run
  -> comparison
  -> optional user acceptance
```

A revision always creates a child Run. It never overwrites the parent and never
updates an accepted-result pointer automatically.

## Revisable sources

In preferred order:

1. CadFlow structured feature or assembly graph;
2. CadFlow sandboxed model program and its normalized parameters;
3. legacy validated CAD IR;
4. supported imported parametric representation;
5. STEP as reference geometry or an explicitly supported derived-edit source;
6. mesh as visual or measurement reference.

STEP or mesh presence does not imply robust feature-history recovery.

## Candidate patch types

A revision proposal may target:

- requirement or design assumptions;
- feature parameters, topology, or ordering;
- a model program source patch;
- part interfaces and datums;
- assembly placement or constraints;
- material, process, tolerance, or output intent;
- deliverable configuration.

Patches must identify the parent, target representation, requested outcome,
expected checks, known uncertainty, and whether unrelated accepted decisions are
preserved.

## Model-program revisions

Agent-generated source is allowed only as an untrusted candidate:

```text
source patch
  -> static and policy checks
  -> isolated execution through Tool Broker
  -> resource limits
  -> geometry and result checks
  -> reviewable child result or typed safe block
```

The Revision Agent never receives arbitrary filesystem, network, shell,
subprocess, credential, or dependency-install authority.

## Evidence

A child Run records, as applicable:

- revision objective and selected parent;
- candidate plan and patches;
- provider actions and tool observations;
- before/after semantic comparison;
- source, contract, build, and geometry validation;
- generated products;
- limitations and unverified intent;
- parent/child lineage;
- user acceptance decision.

Failed revisions preserve their diagnostic evidence without publishing trusted
products.

## Agent behavior

The Revision Agent may:

- inspect allowlisted parent context;
- choose a revision strategy;
- propose and compare multiple patches;
- build candidates through controlled tools;
- respond to validation observations;
- ask one focused question;
- stop with a typed reason.

It must not:

- overwrite parent artifacts;
- silently change unrelated accepted decisions;
- execute outside the Tool Broker;
- invent unsupported external-file feature recovery;
- claim checks that did not run;
- accept its own result.

## Current implementation gap

Current deterministic revision is intentionally narrow: it primarily supports
selected field-level patches to the legacy CAD IR and child-Run comparison.
General feature-graph, model-program, assembly, and deliverable revisions remain
roadmap work.

## Verification

Protect:

- parent immutability and explicit lineage;
- requested versus system-repair changes;
- source/contract validation before execution;
- sandbox enforcement for model programs;
- resource limits and typed failures;
- before/after comparison;
- failed candidate containment;
- child creation not changing accepted pointers;
- honest STEP/mesh limitations.
