# Single Create notes

`upper_link` is preserved as source intent while the executable CAD IR uses the
generic `link_like_part / elongated_plate_with_end_holes` contract. When
CadQuery is available, the child run should contain `input_ir.json`,
`model.step`, and `model.stl`.

The result is one `single_generic_concept_part`. It is not a complete robot-arm
assembly, does not use an `upper_link` template, and does not fall back to
`mounting_plate`.
