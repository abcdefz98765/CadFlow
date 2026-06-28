# Product Decomposition

Product decomposition is requirement-owned because it is part of understanding
what the user wants, not yet part of CAD generation.

The goal is to identify the likely product structure early enough that the
Requirement Skill can ask useful follow-up questions before Planning or Part
Modeling commits to the wrong topology.

## Outputs

- candidate product scope: single part, multi-part assembly, or unknown
- candidate manufactured parts
- candidate reference components
- required user-facing behavior
- likely interfaces between parts and reference components
- missing information that must be clarified before downstream planning

## Guidance

- A product should not become one monolithic part when its function implies
  separable parts, moving interfaces, electronics, wiring, service access, or
  replaceable components.
- Manufactured parts are geometry this project should generate.
- Reference components are purchased or existing items represented as envelopes
  for fit, clearance, and assembly reasoning.
- Decomposition can be tentative in L0, but topology-changing assumptions must
  be recorded and may require user confirmation.

## Example

A pet button should usually be decomposed into:

- manufactured base or enclosure
- manufactured button cap or actuator
- optional switch carrier or sensor mount
- reference tactile switch, keyboard switch, load cell, or other sensor
- wire/cable exit or battery/PCB envelope when relevant
- fastening or retention intent such as screws, snap tabs, or press fit
