# IR Pipeline Examples

These examples use the IR-first workflow:

```text
input_ir.json -> CadQuery model.py -> model.step/model.stl -> validation -> report
```

Regenerate all examples:

```bash
python examples/ir_pipeline/generate_examples.py
```

Generated artifacts are written to `outputs/<part_name>/`.
