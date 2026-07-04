# Single-Part Family Boundaries

This note records the design boundary for future single-part family expansion in
the reviewed-part workflow. It is intentionally not an implementation plan for
new CAD templates.

## Current Boundary

The reviewed-part single-create smoke for the two-part electronics enclosure
currently establishes this boundary:

- `base`: selected, reviewed, handed off, and generated as one child
  single-part STEP/STL run.
- `lid`: selected, reviewed, and handed off, then safely blocked as
  `unsupported_part_type.lid`.
- `screws` and fasteners: classified as `reference_only` and not selected as
  main CAD generation targets.

This is expected and safe. CadFlow can now route a selected candidate part from
an assembly plan into a one-part workflow, while unsupported candidate families
remain visible through sanitized diagnostics instead of silent fallback.

## Lid And Cover Interpretation

`lid` is not a single unambiguous CAD family. It can mean several different
things:

- `flat_cover_plate`: a simple rectangular cover plate with thickness and screw
  holes.
- `enclosure_lid`: a cover for an enclosure, potentially with a lip, flange, or
  rim.
- `cap_or_shallow_tray`: a shallow 3D cover form that may need wall, pocket,
  rim, or clearance semantics.
- `mounting_plate_variant`: a possible geometric shortcut, but risky if it
  hides enclosure semantics behind a plate-shaped template.

The safest first support boundary is either `flat_cover_plate` or a deliberately
limited `simple_enclosure_lid`. The name should preserve the product meaning so
future assembly and interface checks are not confused by a generic plate
mapping.

## Minimal Future Support Boundary

A first lid/cover family should be narrow and deterministic:

- Rectangular lid or cover only.
- Known length, width, and thickness.
- Optional four screw holes.
- Optional chamfer or fillet where existing validation can represent it.
- Interface constraints preserved in metadata and prompts.
- No geometric fit validation with the base yet.
- No automatic hole alignment solving yet.
- No snap-fit, latch, seal, gasket, hinge, or living-hinge support.

Missing required dimensions should block with `needs_revision` rather than
guessing. Unsupported lid semantics should remain blocked with explicit
diagnostic codes.

## Non-Goals

Initial lid/cover support would not imply:

- Full enclosure assembly support.
- Automatic base/lid fit validation.
- Assembly constraint solving.
- STEP assembly export.
- Automatic all-part generation.
- Snap-fit or latch design.
- Gasket or seal design.
- Production-ready enclosure engineering.

## Recommended Next Implementation Gate

Before implementing lid support, add an eval case or smoke expectation that
checks:

- `lid` is selected from `assembly_plan.json`.
- The lid part request includes dimensions and screw-hole interface
  constraints.
- The lid maps to a narrow supported family such as `flat_cover_plate` or
  `simple_enclosure_lid`.
- Missing dimensions block with `needs_revision` rather than guessing.
- The generated result remains a single part.

This should be treated as a separate capability decision, not as a smoke-test
workaround.
