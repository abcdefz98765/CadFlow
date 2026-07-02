# Agent Adapter

`AgentAdapter` is the boundary between natural-language reasoning and deterministic CadFlow execution.

It gives the product one stable interface for intent interpretation, requirement
parsing, planning, revision advice, repair advice, and review explanation while
allowing different implementations behind that interface.

```python
class AgentAdapter:
    def interpret_user_intent(self, prompt: str, context: dict) -> dict:
        ...

    def parse_requirement(self, prompt: str, context: dict) -> dict:
        ...

    def propose_design_brief(self, intent: dict, context: dict) -> dict:
        ...

    def generate_candidate_plans(self, design_brief: dict, context: dict) -> list[dict]:
        ...

    def create_plan(self, requirement: dict, context: dict) -> dict:
        ...

    def convert_plan_to_ir(self, selected_plan: dict, context: dict) -> dict:
        ...

    def parse_revision_request(self, prompt: str, model_context: dict, context: dict) -> dict:
        ...

    def create_revision_plan(self, change_intent: dict, model_context: dict, context: dict) -> dict:
        ...

    def explain_comparison(self, comparison: dict, context: dict) -> dict:
        ...

    def suggest_repair(self, failure: dict, ir: dict, context: dict) -> dict:
        ...

    def explain_review(self, report: dict, trace: dict, context: dict) -> dict:
        ...
```

Agent output must be structured JSON and must pass the relevant CadFlow validation before the execution layer consumes it.

The shared validation entry point is `ai_native_cad.agents.validate_adapter_result(...)`.
It validates adapter output by operation and rejects direct code/shell bypass
fields such as `cadquery_code`, `python_code`, `model_code`, and
`shell_command`.

The current codebase may implement only the smaller deterministic subset. The
expanded interface above documents the product direction for iterative CAD
workflows.

## Adapter Modes

### 1. DeterministicAgentAdapter

The deterministic adapter wraps the current rule and template-based behavior.
For v0.5 it is the only implemented provider identity and reports itself as
`local/mock` with networking disabled and no API key requirement.

Use it for:

- Tests.
- CI.
- Local demos.
- Offline execution.
- Fallback when an LLM API is unavailable.

This mode is intentionally predictable and should remain dependency-light.

### 2. JsonContractAgentAdapter

`JsonContractAgentAdapter` is a post-v0.5 scaffold for optional provider-backed
JSON contract generation. It is not the default adapter and does not import a
provider SDK.

For this scaffold it supports the current structured `AgentAdapter` operations:
`parse_requirement(...)`, `create_plan(...)`, `parse_revision_request(...)`,
`create_revision_plan(...)`, `suggest_repair(...)`, and
`explain_review(...)`. Callers must explicitly inject a fake or
provider-specific client at the boundary. The adapter builds a JSON-only
contract request, parses the returned JSON object, and runs the matching local
adapter validation before the result can be persisted or consumed by workflow
code.

It must not record prompts, transcripts, token contents, secrets, API keys, or
local paths in provider identity metadata.

Provider setup remains opt-in and client-injected. `JsonContractProviderConfig`
records only non-secret settings such as provider name, model name,
`enabled`, timeout, retry count, and whether an API key environment variable
name has been configured. The adapter passes timeout/retry options to the
injected client in request metadata, but it does not read secret values, import a
provider SDK, or perform network I/O by itself.

### 3. LLMApiAgentAdapter

The LLM API adapter is the primary future user-facing mode, but it is not
implemented in v0.5. The current phase only establishes the interface, local
mock behavior, validation gates, and runtime tracing needed before a real
provider can be added safely.

It should:

- Convert natural language into structured requirement JSON.
- Convert validated requirements into planning JSON.
- Interpret ambiguous user intent and propose explicit assumptions.
- Generate design briefs and candidate design plans before CAD IR conversion.
- Parse revision requests against model context.
- Propose change intent, revision plans, and constrained patches.
- Explain old/new comparison results in user-facing language.
- Suggest constrained repair changes from failure context.
- Explain reports and traces in user-facing language.
- Use schema validation for every structured output.
- Ask for user confirmation when fields are missing, ambiguous, risky, or safety-relevant.

It must not directly write arbitrary CadQuery code. Geometry execution remains owned by the CadFlow Python API and CAD Agent Loop.

### 4. CliDeveloperAgentAdapter

The CLI developer adapter is optional developer mode.

It may call tools such as OpenCode or Codex CLI for repository development tasks:

- Modifying CadFlow source code.
- Adding templates.
- Writing tests.
- Refactoring internal modules.
- Updating documentation.

It must not be the default model generation runtime.

OpenCode/Codex CLI is a developer assistant for evolving the repository, not the default runtime for end-user CAD generation.

## Contract Rules

- Natural-language understanding belongs in the agent layer.
- Deterministic execution belongs in the CadFlow Python API.
- Agent outputs must become validated JSON contracts before execution.
- The execution layer must not consume unconstrained free-form agent text.
- LLMs may propose design decisions, assumptions, candidate plans, revision
  plans, and patches.
- CadFlow owns validation, normalization, CAD execution, artifact contracts, and
  lineage.
- Default workflows must not execute arbitrary free-form LLM code.
- User confirmations should be captured as structured context and written into run artifacts.
- Adapter activity recorded in `logs/runtime.json` must include only sanitized provider identity and operation metadata, not prompts, secrets, API keys, tokens, or chat transcripts.
- Provider adapters should run the same local adapter-output validation in tests before they are wired into workflow stages.

## Iterative Workflow Responsibilities

For first-time creation, the adapter may help with unclear intent by returning
assumptions, missing fields, risk flags, and a recommended workflow decision such
as `proceed_with_assumptions`, `ask_user`, or `return_to_requirement`.

For revision, the adapter should consume Model Intake output and parent-run
context, then produce structured `change_intent.json` and `revision_plan.json`
content. It may propose a patch, but the patch must be validated against the
target artifact before execution.
