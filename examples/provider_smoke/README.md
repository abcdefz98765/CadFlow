# Provider Smoke

Manual-only provider sanity checks for JSON-contract adapters.

Run scripts from the repository root after configuring provider credentials in
the process environment or a simple env file:

```bash
python examples/provider_smoke/parse_requirement_smoke.py --provider deepseek
python examples/provider_smoke/normalized_design_eval.py --provider deepseek --env-file .env
```

The env file parser supports `KEY=VALUE` lines, ignores blank lines and
comments, and does not print loaded values. Existing process environment values
take precedence over env-file values. DeepSeek uses `DEEPSEEK_API_KEY`; the
OpenAI-compatible Responses path uses `OPENAI_API_KEY`. Optional provider
settings include `CADFLOW_DEEPSEEK_MODEL`, `CADFLOW_DEEPSEEK_BASE_URL`,
`CADFLOW_DEEPSEEK_ENDPOINT`, `CADFLOW_OPENAI_MODEL`,
`CADFLOW_OPENAI_BASE_URL`, `CADFLOW_OPENAI_ENDPOINT`,
`CADFLOW_PROVIDER_TIMEOUT_SECONDS`, and `CADFLOW_PROVIDER_MAX_RETRIES`.

All scripts print sanitized status metadata. They must not print API keys,
provider messages, raw provider response bodies, local absolute paths, runtime
logs, or transcripts.

## Basic Provider Smoke

### `parse_requirement_smoke.py`

```bash
python examples/provider_smoke/parse_requirement_smoke.py --provider deepseek
```

- Verifies: the selected JSON-contract provider can return a requirement-shaped
  artifact that CadFlow can validate.
- Does not verify: planning, CAD IR conversion, CadQuery execution, STEP/STL
  export, assemblies, or product quality.
- Real provider: yes, unless adapter construction is monkeypatched in tests.
- Ignored outputs: no durable CAD outputs; it prints a compact sanitized
  summary.
- CAD generation: none. This is contract parsing only.

### `create_workflow_smoke.py`

```bash
python examples/provider_smoke/create_workflow_smoke.py --provider deepseek
```

- Verifies: provider requirement parsing plus the Requirement + Planning create
  workflow boundary.
- Does not verify: normalized design evaluation, assembly planning, full
  assembly CAD generation, or provider-authored CAD IR/code.
- Real provider: yes, unless adapter construction is monkeypatched in tests.
- Ignored outputs: may write workflow artifacts under ignored `outputs/` when
  an output directory is provided.
- CAD generation: only through the existing supported single-part pipeline when
  the requirement is complete and supported.

## Provider Create/Design Evaluation

### `provider_create_eval.py`

```bash
python examples/provider_smoke/provider_create_eval.py --provider deepseek
python examples/provider_smoke/provider_create_eval.py --provider deepseek --provider-contract-mode extract_then_compile
```

- Verifies: a small fixed prompt set across provider create behavior, status
  metadata, expected supported cases, and expected blocked cases.
- Does not verify: production readiness, broad benchmark quality, full assembly
  CAD generation, gear templates, provider-generated CAD IR, or
  provider-generated code.
- Real provider: yes.
- Ignored outputs: yes, writes eval artifacts such as case reports under
  ignored `outputs/`.
- CAD generation: possible for supported single-part cases only. Multi-part or
  unsupported cases should block clearly.

Strict mode checks direct provider contract compliance. `extract_then_compile`
is the product-oriented normalized path: the provider extracts structured
signals, then CadFlow compiles and validates internal contracts locally.

### `normalized_design_eval.py`

```bash
python examples/provider_smoke/normalized_design_eval.py --provider deepseek
```

- Verifies: normalized design-create behavior over a fixed prompt set,
  including design-level artifacts, multi-part intent, assembly-like scope,
  unsupported requests, and safety-critical blocks.
- Does not verify: full assembly CAD, multi-part generation, assembly
  constraints, STEP assembly export, provider-generated CAD IR, or
  provider-generated code.
- Real provider: yes.
- Ignored outputs: yes, writes `eval_cases.json`, `eval_summary.json`, and
  `eval_report.md` under ignored `outputs/`.
- CAD generation: supported single-part cases may generate CAD. Assembly cases
  should stop at planning artifacts.

For normalized design create runs, multi-part or assembly prompts may write
`assembly_plan.json`. That file is a sanitized planning artifact only; it
records normalized parts, interfaces, quality counts, and blocked reasons, then
stops before CAD IR, multi-part CAD, constraints, or STEP assembly generation.

## Staged Assembly-To-Part Workflow

### `reviewed_part_single_create_smoke.py`

```bash
python examples/provider_smoke/reviewed_part_single_create_smoke.py --provider deepseek --env-file .env
```

- Verifies: the staged path from an assembly prompt to `assembly_plan.json`,
  selection of at most one candidate part when appropriate, a
  `part_create_request`, review, handoff, and an optional child single-part
  create attempt.
- Does not verify: automatic generation of all parts, full assembly CAD,
  assembly constraint solving, STEP assembly export, batch generation, new CAD
  templates, provider-backed CAD IR, or provider-generated Python/CadQuery.
- Real provider: yes.
- Ignored outputs: yes, keeps staged artifacts under ignored
  `outputs/provider_smoke/reviewed_part_single_create/` by default.
- CAD generation: assembly CAD must not be generated. A reviewed child
  single-part run may generate CAD only if the selected part can safely enter
  the existing single-part pipeline; otherwise it should block clearly.

The fixed smoke prompt is:

```text
Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.
```

Expected staging is:

```text
assembly prompt
  -> assembly_plan.json
  -> one selected candidate part, such as base or lid
  -> part_create_request.json
  -> part_request_review.json
  -> reviewed_part_handoff.json
  -> optional child single-part create or a clear block
```

Base and lid may be candidate parts for reviewed single-part planning. Screws
and other fasteners are reference-only and must not be selected. This workflow
is a planning/staged handoff example, not full assembly CAD generation.

## Prompt Expectations

| Group | Example prompt | Expected behavior |
| --- | --- | --- |
| Supported single-part-ish examples | `Make an 80x40x5 mm mounting plate with four M4 holes.` | May proceed through normalized single-part CAD generation. |
| Supported single-part-ish examples | `Make a 20 mm diameter spacer washer, 6 mm thick, with an 8 mm center hole.` | May proceed through normalized single-part CAD generation. |
| Assembly planning only examples | `Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.` | Writes `assembly_plan.json`, selects base or lid when classified as a candidate, and may stage one reviewed part. No assembly CAD. |
| Assembly planning only examples | `Design a hinge with two leaves and a pin.` | Writes planning artifacts; pin hardware should be reference-only. No assembly CAD. |
| Expected blocked examples | `Design a gear train with meshing gears.` | Blocks as unsupported part family. No new gear templates. |
| Expected blocked examples | `Design a production aerospace bracket.` | Blocks safety/production-critical scope. No CAD generation. |

These prompts are curated smoke examples, not coverage claims. Complex assembly
examples are planning boundary tests unless and until assembly CAD generation is
implemented explicitly.
