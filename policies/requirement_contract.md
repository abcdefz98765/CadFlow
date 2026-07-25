# Intent Contract Policy

Compatibility artifact: `requirement.json`.

## Purpose

Capture enough structured engineering intent for an Agent to begin useful
design exploration while keeping facts, assumptions, uncertainty, and
acceptance targets distinct.

## Minimum target content

- objective and scope;
- known dimensions and units;
- functions and interfaces;
- manufacturing and material intent when known;
- evaluation and deliverable expectations;
- accepted user facts;
- Agent assumptions;
- missing decisions and focused questions;
- assurance mode;
- source and revision provenance.

The original prompt remains immutable evidence. An Intent artifact may summarize
and normalize it but must not silently contradict it.

## Clarification policy

Ask when the answer materially changes topology, number of parts, real-component
fit, interfaces, intended motion, manufacturing route, safety, or acceptance
criteria. Otherwise choose a reversible exploratory assumption, expose it, and
continue.

## Downstream policy

Design and Geometry skills consume the active Intent plus accepted Work context;
they do not repeatedly re-parse raw history as an alternative source of truth.
Changing upstream meaning creates a new version and marks dependent candidates
stale.

## Legacy compatibility

Current code requires fields such as `part_type`, `dimensions`, `features`,
`outputs`, `check_level`, and `cad_brief`. Compatibility adapters may continue
to populate them for the legacy CAD IR. They are not the target limit of Intent
or the Agent's design space.
