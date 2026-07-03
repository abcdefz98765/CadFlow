"""Manual opt-in provider smoke test for the provider create workflow."""

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

from ai_native_cad.agents import make_json_contract_adapter_from_env
from ai_native_cad.pipeline import run_provider_create_pipeline

try:
    from examples.provider_smoke.env_file import load_env_file
except ModuleNotFoundError:
    from env_file import load_env_file


SMOKE_PROMPT = "Make an 80x40x5 mm mounting plate with four M4 holes."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a manual provider create workflow smoke test.")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--env-file", default=None, help="Optional manual KEY=VALUE env file. Process env wins.")
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
    result = run_provider_create_pipeline(SMOKE_PROMPT, adapter, output_dir=args.output_dir)
    metadata = result.get("provider_create", {})
    identity = metadata.get("adapter") if isinstance(metadata.get("adapter"), dict) else {}
    traces = metadata.get("provider_request_traces") if isinstance(metadata.get("provider_request_traces"), list) else []
    knowledge_ids = []
    for trace in traces:
        if isinstance(trace, dict):
            knowledge_ids.extend(str(item) for item in trace.get("knowledge_ids", []) if isinstance(item, str))

    status = {
        "provider": identity.get("provider"),
        "model": identity.get("model"),
        "status": result.get("status"),
        "requirement_status": metadata.get("requirement_status"),
        "planning_status": metadata.get("planning_status"),
        "ir_validation_status": metadata.get("ir_validation_status"),
        "pipeline_status": metadata.get("pipeline_status"),
        "output_dir": result.get("output_dir"),
        "selected_knowledge_ids": sorted(set(knowledge_ids)),
    }
    if result.get("error_category"):
        status["error_category"] = result["error_category"]
    if result.get("error_category") == "auth_failed":
        status["message"] = "Provider credentials are missing or not accepted."
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if result.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
