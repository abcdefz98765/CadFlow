# Provider Smoke

Manual-only provider sanity checks for JSON-contract adapters.

Run from the repository root after configuring provider credentials in your
environment:

```bash
python examples/provider_smoke/parse_requirement_smoke.py --provider deepseek
```

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
