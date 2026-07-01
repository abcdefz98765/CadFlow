# Agent Adapter

`AgentAdapter` is the boundary between natural-language reasoning and deterministic CadFlow execution.

It gives the product one stable interface for requirement parsing, planning, repair advice, and review explanation while allowing different implementations behind that interface.

```python
class AgentAdapter:
    def parse_requirement(self, prompt: str, context: dict) -> dict:
        ...

    def create_plan(self, requirement: dict, context: dict) -> dict:
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

### 2. LLMApiAgentAdapter

The LLM API adapter is the primary future user-facing mode, but it is not
implemented in v0.5. The current phase only establishes the interface, local
mock behavior, validation gates, and runtime tracing needed before a real
provider can be added safely.

It should:

- Convert natural language into structured requirement JSON.
- Convert validated requirements into planning JSON.
- Suggest constrained repair changes from failure context.
- Explain reports and traces in user-facing language.
- Use schema validation for every structured output.
- Ask for user confirmation when fields are missing, ambiguous, risky, or safety-relevant.

It must not directly write arbitrary CadQuery code. Geometry execution remains owned by the CadFlow Python API and CAD Agent Loop.

### 3. CliDeveloperAgentAdapter

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
- User confirmations should be captured as structured context and written into run artifacts.
- Adapter activity recorded in `logs/runtime.json` must include only sanitized provider identity and operation metadata, not prompts, secrets, API keys, tokens, or chat transcripts.
- Provider adapters should run the same local adapter-output validation in tests before they are wired into workflow stages.
