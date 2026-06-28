# Design Analysis

Planning turns structured requirements into an engineering approach before
modeling starts.

## Analyze

- product scope: single part, multi-part assembly, or unclear
- primary function and user-facing behavior
- functional datums and reference faces
- interfaces between generated parts and reference components
- manufacturing bias when known
- dependency order between parts
- risks created by assumptions or missing information

## Output Expectations

`plan.md` should explain why the workflow route was chosen, which parts or
templates should be generated first, which interfaces must be preserved, and
which checks downstream steps should run.

Do not hide unresolved decisions. Either route them back to Requirement or mark
them as L0 assumptions that Review must report.
