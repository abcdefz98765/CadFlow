# Fields By Check Level

## L0 Playground

Goal: generate a plausible model with traceable assumptions.

Required:

- object goal
- scope
- primary dimensions or template defaults
- functional features
- unit
- output formats

Optional or defaulted:

- material
- manufacturing process
- assembly method

Deferred:

- tolerances
- roughness/surface finish
- loads
- certification

## L1 Maker

Goal: make something a person can print, assemble, and inspect casually.

Required:

- all L0 fields
- manufacturing process
- assembly clearance where parts interact
- serviceability needs
- reference components for installed modules, sensors, switches, or batteries

Optional:

- material family
- fastener choice
- print orientation

Deferred:

- precision tolerances
- roughness, unless it affects a contact or sliding face
- certification

## L2 Engineering

Goal: model a mechanical part or assembly whose interfaces and constraints are explicit.

Required:

- material or material family
- manufacturing process
- functional tolerances
- interface definitions
- loads or load direction
- operating environment

Optional:

- surface finish by functional face
- inspection method

## L3 Industrial

Goal: prepare for repeatable manufacturing and review.

Required:

- DFM/DFA constraints
- inspection method
- BOM strategy
- supplier or process constraints when known
- versioning policy

## L4 Safety Critical

Goal: reserve workflow for controlled, human-approved safety work.

Required:

- applicable standards
- hazard analysis
- verification plan
- human signoff

The system must not automatically release L4 designs.
