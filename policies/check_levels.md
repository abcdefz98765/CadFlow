# Assurance Policy

Assurance controls required context, evaluation, and permitted claims. It does
not constrain which geometry strategy an Agent may explore.

## Explore

Purpose: concepts and rapid iteration.

- visible assumptions are allowed;
- primary geometry and export checks run where supported;
- missing engineering inputs are recorded;
- output is not manufacturing or release evidence.

Legacy mapping: approximately L0 Playground and early L1 Maker.

## Engineer

Purpose: a reviewable engineering candidate.

Required as applicable:

- material and manufacturing process;
- explicit interfaces, datums, and functional tolerances;
- loads or load directions and operating environment;
- acceptance targets and requested measurements;
- assembly clearances and serviceability intent;
- deterministic checks supported for the relevant domain.

Legacy mapping: approximately L2 Engineering and selected L3 Industrial fields.

## Release

Purpose: a domain-specific package for formal human release.

Release is not a generic switch. It requires a declared validation profile,
inspection and manufacturing plan, complete provenance, all configured checks,
and explicit human authorization.

Legacy L3/L4 fields may inform a Release profile, but CadFlow does not currently
provide general industrial or safety-critical release.

## Claim rule

Every conclusion distinguishes measured, assumed, unverified, skipped, blocked,
and failed evidence. STEP creation, an Agent statement, or a numeric score never
implies fit, motion, strength, tolerance, DFM/DFA, GD&T, FEA, safety, or release
validation.
