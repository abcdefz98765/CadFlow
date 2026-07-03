"""Manual opt-in provider smoke test for parse_requirement.

This script is intentionally outside the normal test suite. It requires an
explicit command and prints only sanitized provider request metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_native_cad.agents import JsonContractProviderError, make_json_contract_adapter_from_env

try:
    from examples.provider_smoke.env_file import load_env_file
except ModuleNotFoundError:
    from env_file import load_env_file


SMOKE_PROMPT = "Make an 80x40x5 mm mounting plate with four M4 holes."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a manual provider parse_requirement smoke test.")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--env-file", default=None, help="Optional manual KEY=VALUE env file. Process env wins.")
    args = parser.parse_args(argv)

    try:
        load_env_file(args.env_file)
        adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
        requirement = adapter.parse_requirement(SMOKE_PROMPT, context={"workflow_stage": "requirement"})
    except JsonContractProviderError as exc:
        trace = _trace_or_default(locals().get("adapter"), args.provider)
        _print_status(trace, validation_status="not_run", error_category=exc.category)
        return 2 if exc.category == "auth_failed" else 1
    except Exception as exc:
        trace = _trace_or_default(locals().get("adapter"), args.provider)
        _print_status(trace, validation_status="not_run", error_category=_safe_error_category(exc))
        return 1

    trace = _trace_or_default(adapter, args.provider)
    validation_status = "passed" if isinstance(requirement, dict) else "failed"
    _print_status(trace, validation_status=validation_status)
    return 0


def _trace_or_default(adapter: Any, provider: str) -> dict[str, Any]:
    trace = getattr(adapter, "last_provider_request_trace", None)
    if isinstance(trace, dict):
        return trace
    identity = getattr(adapter, "provider_identity", None)
    if not isinstance(identity, dict):
        identity = {"provider": provider, "adapter": "json_contract"}
    return {
        "operation": "parse_requirement",
        "stage": "requirement",
        "provider_identity": {
            key: value
            for key, value in identity.items()
            if key in {"provider", "model", "adapter"} and isinstance(value, (str, int, float, bool))
        },
        "message_count": 0,
        "knowledge_ids": [],
    }


def _print_status(
    trace: dict[str, Any],
    *,
    validation_status: str,
    error_category: str | None = None,
) -> None:
    identity = trace.get("provider_identity") if isinstance(trace.get("provider_identity"), dict) else {}
    status = {
        "provider": identity.get("provider"),
        "model": identity.get("model"),
        "operation": trace.get("operation"),
        "validation_status": validation_status,
        "selected_knowledge_ids": trace.get("knowledge_ids", []),
        "message_count": trace.get("message_count", 0),
    }
    if error_category == "auth_failed":
        status["status"] = "missing_provider_credentials"
        status["message"] = "Provider credentials are missing or not accepted."
    elif error_category:
        status["status"] = "provider_error"
        status["error_category"] = error_category
    else:
        status["status"] = "ok"
    print(json.dumps(status, indent=2, sort_keys=True))


def _safe_error_category(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "credential" in name or "permission" in name:
        return "auth_failed"
    return "smoke_failed"


if __name__ == "__main__":
    raise SystemExit(main())
