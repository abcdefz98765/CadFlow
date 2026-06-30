# Missing Information Policy

Classify missing information by design impact.

## Ask The User

Ask when the missing field changes:

- topology or number of parts
- fit with real components
- assembly order or serviceability
- manufacturing method
- functional interfaces
- loads or safety assumptions

Examples:

- A button must contain a specific switch, sensor, PCB, or battery, but no module envelope is known.
- The user asks for an assembly but does not identify whether it should be removable, glued, screwed, or snapped together.
- L2 or higher is requested without material, manufacturing process, or interface tolerances.

## Default And Record

Use defaults when the missing field does not change the main design decision. Always record the assumption.

Examples:

- L0 size defaults from a known part template.
- L0 material is unspecified.
- L0 surface finish is unspecified.
- L0 supported part templates may still generate from defaults when dimensions
  are absent, but `missing_information` must list the absent dimension fields.

## Defer

Defer information that belongs to a higher check level.

Examples:

- Surface roughness belongs in L2+ unless a functional face needs it earlier.
- Certification and hazard review belong in L4.
