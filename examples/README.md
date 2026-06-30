# Examples

Examples are split by scope.

```text
examples/
  parts/
    mounting_plate/
    circular_button/
  prompt_pipeline/
    run_prompt_examples.py
  assemblies/
    pet_button/
      parts/
        pet_button_base/
        pet_button_cap/
        pet_button_switch_plate/
        pet_button_tactile_switch/
      assembly_plan.json
      assembly_plan.md
      assembly.json
      constraint_assembly.json
      README.md
    enclosure/
      parts/
        enclosure_base/
        enclosure_lid/
        spacer/
        wall_bracket/
      assembly.json
      constraint_assembly.json
      README.md
```

## Standalone Parts

Standalone part examples live in `examples/parts/<part>/`.

```bash
python examples/parts/mounting_plate/model.py
python examples/parts/circular_button/model.py
```

`circular_button` is a pet communication button concept with a large paw-friendly
press surface, tactile-switch pocket, terminal clearance slots, anti-slip pad
recesses, and a wire outlet. For a realistic multi-part design, prefer the
`examples/assemblies/pet_button/` assembly.

## Prompt Pipeline

Prompt pipeline examples live in `examples/prompt_pipeline/`. They are manual
debug runs for the full deterministic path:

```text
prompt -> requirement.json + CAD IR -> model.step/model.stl -> report/trace
```

```bash
python examples/prompt_pipeline/run_prompt_examples.py
python examples/prompt_pipeline/run_prompt_examples.py mounting_plate_by_holes
```

Generated artifacts are written to `outputs/prompt_pipeline/<case_id>/` and are
not tracked. Each run also writes `prompt_summary.json` and `prompt_summary.md`
for quick inspection of requirement status, CAD Brief targets, measured report
targets, agent attempts, and file paths. Benchmarks remain IR-first under
`benchmarks/`.

## Assemblies

Assembly examples live in `examples/assemblies/<assembly>/`.

Each assembly owns:

- `parts/`: component part scripts for that assembly.
- `assembly_plan.json` / `assembly_plan.md`: traceable assembly intent and confirmation gate.
- `assembly.json`: absolute placement assembly config.
- `constraint_assembly.json`: lightweight constraint placement config.
- `README.md`: runbook for the assembly.

```bash
python examples/assemblies/enclosure/parts/enclosure_base/model.py
python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json
```

Pet button assembly:

```bash
python examples/assemblies/pet_button/parts/pet_button_base/model.py
python examples/assemblies/pet_button/parts/pet_button_switch_plate/model.py
python examples/assemblies/pet_button/parts/pet_button_tactile_switch/model.py
python examples/assemblies/pet_button/parts/pet_button_cap/model.py
python -m ai_native_cad.assembly_validator examples/assemblies/pet_button/assembly.json
```
