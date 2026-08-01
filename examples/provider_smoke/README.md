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

## Local Tool Broker Gate Acceptance

```bash
python examples/provider_smoke/tool_broker_gate_eval.py
```

- Verifies: Broker-owned structured-contract validation and the current
  platform's fail-closed model-program capability gate.
- Does not verify: an enforceable sandbox, provider-source execution, geometry,
  publication, or production Agentic design.
- Real provider: no; this is a local authority-boundary acceptance.
- Durable outputs: none. A temporary parent directory is used, and the asserted
  candidate directory must never be created.
- Expected Windows result: validation passes, model-program capability is
  unavailable, the code is `sandbox_unavailable`, and
  `side_effect_started=false`.

## WorkOrchestrator Design Episode Acceptance

```bash
python examples/provider_smoke/work_design_episode_eval.py
```

- Verifies: a scripted provider-selected `design_part` Episode routes through
  `WorkOrchestrator`, appends evidence under the owned Part Job attempt Run,
  registers controlled candidate/observation references, and replays the same
  request idempotently.
- Does not verify: a real external provider, CAD execution, STEP output,
  reviewable publication, acceptance, or non-template design quality.
- Durable outputs: none; the acceptance uses a temporary Workspace.
- Required invariants: original Run prompt bytes, Part Job history, active
  lineage, accepted pointers, and deliverable state remain unchanged; no
  `model.py`, STEP, STL, or preview is created.

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
  `part_create_request`, review, handoff, one child single-part create attempt,
  and local `part_result_review.json` when child artifacts exist.
- Does not verify: automatic generation of all parts, full assembly CAD,
  assembly constraint solving, STEP assembly export, batch generation, new CAD
  templates, provider-backed CAD IR, provider-generated Python/CadQuery, or
  geometric fit between generated parts.
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
multi-part prompt
  -> normalized provider design create
  -> assembly_plan.json
  -> one selected candidate part, such as base or lid
  -> part_create_request.json
  -> part_request_review.json
  -> reviewed_part_handoff.json
  -> one child single-part run
  -> model.step / model.stl
  -> part_result_review.json
```

Base and lid may be candidate parts for reviewed single-part planning. Screws
and other fasteners are reference-only and must not be selected. This workflow
is a reviewed single-part checkpoint for one selected part, not full assembly
CAD generation.

Latest manual command:

```bash
python examples/provider_smoke/reviewed_part_single_create_smoke.py --provider deepseek --env-file .env
python examples/provider_smoke/reviewed_part_single_create_smoke.py --provider deepseek --env-file .env --part-id base
python examples/provider_smoke/reviewed_part_single_create_smoke.py --provider deepseek --env-file .env --part-id lid
```

Current candidate outcome boundary for the fixed two-part electronics enclosure
smoke:

- `--part-id base` succeeds and generates one child single-part STEP/STL.
- `--part-id lid` is selected and reviewed, then safely blocks at
  `unsupported_part_type.lid`.
- Screws and fasteners remain `reference_only` and are not selected for CAD
  generation.
- No batch generation occurs.
- No full assembly generation occurs.
- No assembly constraints are solved.

CadFlow can now attempt different candidate parts from the same assembly plan
one at a time. The current supported boundary is exposed through sanitized
diagnostics instead of hidden fallback behavior.

This does not mean all parts in an assembly can be generated automatically. It
does not mean lid/cover geometry is supported yet, and it does not mean full
assembly export or fit validation exists. The next capability gap is not
assembly routing; it is single-part support and mapping for additional candidate
families such as lid/cover.

Potential next step: evaluate whether `lid` should map to an existing simple
plate/cover family or become a new supported single-part family. This should be
done as a separate capability decision, not as a smoke-test workaround.

Sanitized example summary:

```json
{
  "assembly_plan_created": true,
  "selected_part_id": "base",
  "part_request_status": "ready_for_review",
  "review_status": "approved",
  "handoff_status": "ready_for_single_part_planning",
  "bridge_status": "success",
  "child_run_created": true,
  "child_run_name": "single_part_base",
  "step_created": true,
  "stl_created": true,
  "part_result_review_created": true,
  "part_result_review_status": "accepted_for_preview",
  "part_result_diagnostic_codes": [
    "part_result.interface_constraints_preserved_in_metadata",
    "part_result.lineage_preserved",
    "part_result.review_created",
    "part_result.single_part_scope_preserved",
    "part_result.step_created",
    "part_result.stl_created"
  ],
  "part_result_step_check": true,
  "part_result_stl_check": true,
  "part_result_single_part_scope_check": true,
  "part_result_lineage_check": true,
  "part_result_interface_metadata_check": true,
  "no_batch_generation": true,
  "no_assembly_generation": true,
  "no_assembly_constraints_solved": true
}
```

The summary intentionally excludes raw provider messages, secrets, environment
values, local absolute paths, and generated output paths.

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
