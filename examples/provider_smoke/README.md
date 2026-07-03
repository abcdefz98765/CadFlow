# Provider Smoke

Manual-only provider sanity checks for JSON-contract adapters.

Run from the repository root after configuring provider credentials in your
environment:

```bash
python examples/provider_smoke/parse_requirement_smoke.py --provider deepseek
```

Credentials are read from the process environment by default. Manual scripts
also accept a simple env file:

```bash
python examples/provider_smoke/normalized_design_eval.py --provider deepseek --env-file .env
```

The env file parser supports simple `KEY=VALUE` lines, ignores blank lines and
comments, and does not print loaded values. Existing process environment values
take precedence over env-file values. DeepSeek uses `DEEPSEEK_API_KEY`; the
OpenAI-compatible Responses path uses `OPENAI_API_KEY`. Optional provider
settings include `CADFLOW_DEEPSEEK_MODEL`, `CADFLOW_DEEPSEEK_BASE_URL`,
`CADFLOW_DEEPSEEK_ENDPOINT`, `CADFLOW_OPENAI_MODEL`,
`CADFLOW_OPENAI_BASE_URL`, `CADFLOW_OPENAI_ENDPOINT`,
`CADFLOW_PROVIDER_TIMEOUT_SECONDS`, and `CADFLOW_PROVIDER_MAX_RETRIES`.

Provider-backed Requirement + Planning create workflow:

```bash
python examples/provider_smoke/create_workflow_smoke.py --provider deepseek
```

Provider-backed normalized create is the recommended product-oriented path when
using a real provider from Python:

```python
from ai_native_cad.pipeline import run_provider_normalized_create_pipeline

run_provider_normalized_create_pipeline(prompt, adapter)
```

It runs:

```text
prompt
  -> provider extraction
  -> local requirement/planning compiler
  -> deterministic CAD IR conversion
  -> run_ir_pipeline
```

The provider extracts structured intent, fields, and constraints. CadFlow then
compiles and validates internal contracts locally. Provider-generated CAD IR,
CadQuery/Python code, and arbitrary provider fields are not accepted as
generation authority.

Manual provider create quality evaluation over a small fixed prompt set:

```bash
python examples/provider_smoke/provider_create_eval.py --provider deepseek
```

The default mode is strict: provider outputs must satisfy the CadFlow contracts
directly. Strict is provider contract compliance mode; it is useful for
provider/schema testing and is not the recommended default user path.

To explicitly evaluate the normalized local compiler path where provider output
is treated as extracted fields, pass:

```bash
python examples/provider_smoke/provider_create_eval.py --provider deepseek --provider-contract-mode extract_then_compile
```

`extract_then_compile` is the product-oriented normalized workflow mode:
provider extracts structured intent/fields/constraints, and CadFlow compiles
and validates internal requirement/planning contracts locally. 8/10 pipeline
success + 2 expected blocked means all supported eval cases passed and
unsupported/unsafe cases blocked correctly. It should not be read as production
readiness.

The script prints sanitized request status metadata only. It does not print API
keys, provider messages, raw prompts, provider response bodies, local paths, or
runtime logs.

Manual complex design / assembly boundary evaluation:

```bash
python examples/provider_smoke/normalized_design_eval.py --provider deepseek
```

This runs a fixed small prompt set through
`run_provider_normalized_design_create_pipeline(...)` and writes
`eval_cases.json`, `eval_summary.json`, and `eval_report.md`. The eval is
manual-only and is meant to inspect design-level artifacts, multi-part intent,
assembly-like scope, unsupported requests, and safety-critical blocks. It does
not add assembly CAD generation, gear templates, provider-generated CAD IR, or
provider-generated code.

For normalized design create runs, multi-part or assembly prompts may now write
`assembly_plan.json`. That file is a sanitized planning artifact only; it
records the assembly boundary and blocked reasons, then stops before CAD IR,
multi-part CAD, constraints, or STEP assembly generation.
