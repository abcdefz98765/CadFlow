"""Safe staged action wrappers for the local workflow console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ai_native_cad.pipeline.runner import (
    run_assembly_part_request_pipeline,
    run_part_request_review_pipeline,
    run_part_result_review_pipeline,
    run_reviewed_part_handoff_pipeline,
    run_reviewed_part_single_create_pipeline,
)
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend

ACTION_STAGE_FOLDERS = {
    "part_request": "02_part_request",
    "part_review": "03_review",
    "reviewed_handoff": "04_handoff",
    "reviewed_part_create": "05_single_create",
    "part_result_review": "06_part_result_review",
}

ACTION_ARTIFACTS = {
    "assembly_plan": ("01_design/assembly_plan.json", "assembly_plan.json"),
    "part_request": ("02_part_request/part_create_request.json", "part_create_request.json"),
    "part_review": ("03_review/part_request_review.json", "part_request_review.json"),
    "reviewed_handoff": ("04_handoff/reviewed_part_handoff.json", "reviewed_part_handoff.json"),
    "single_create_lineage": ("05_single_create/lineage.json", "lineage.json"),
}

ACTION_NAMES = {
    "part_request",
    "part_review",
    "reviewed_handoff",
    "reviewed_part_create",
    "part_result_review",
}

BLOCKED_PUBLIC_KEYS = {
    "path",
    "run_dir",
    "root",
    "output_dir",
    "child_output_dir",
    "report_json",
    "report_md",
    "payload",
    "raw_payload",
    "raw_response",
    "raw_provider",
    "provider_messages",
    "provider_response",
    "transcript",
    "request_payload",
    "response_payload",
}


class WorkflowConsoleActions:
    """One-stage reviewed-part workflow actions constrained to configured run roots."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def create_part_request(
        self,
        run_id: str,
        *,
        part_id: str | None = None,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Create one part request from an existing assembly plan artifact."""
        run_path = self.backend.resolve_run(run_id, root=root)
        source = self._find_artifact(run_path, "assembly_plan")
        return self._run_action(
            run_path,
            "part_request",
            run_assembly_part_request_pipeline,
            source,
            output_dir=self._stage_dir(run_path, "part_request"),
            part_id=part_id,
        )

    def review_part_request(self, run_id: str, *, root: str | Path | None = None) -> dict[str, Any]:
        """Review exactly one existing part_create_request.json artifact."""
        run_path = self.backend.resolve_run(run_id, root=root)
        source = self._find_artifact(run_path, "part_request")
        return self._run_action(
            run_path,
            "part_review",
            run_part_request_review_pipeline,
            source,
            output_dir=self._stage_dir(run_path, "part_review"),
        )

    def create_reviewed_handoff(self, run_id: str, *, root: str | Path | None = None) -> dict[str, Any]:
        """Create one reviewed_part_handoff.json from reviewed part request artifacts."""
        run_path = self.backend.resolve_run(run_id, root=root)
        part_request = self._find_artifact(run_path, "part_request")
        part_review = self._find_artifact(run_path, "part_review")
        return self._run_action(
            run_path,
            "reviewed_handoff",
            run_reviewed_part_handoff_pipeline,
            part_request,
            part_review,
            output_dir=self._stage_dir(run_path, "reviewed_handoff"),
        )

    def create_reviewed_part(
        self,
        run_id: str,
        *,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run the existing explicit reviewed single-part create bridge once."""
        run_path = self.backend.resolve_run(run_id, root=root)
        handoff = self._find_artifact(run_path, "reviewed_handoff")
        return self._run_action(
            run_path,
            "reviewed_part_create",
            run_reviewed_part_single_create_pipeline,
            handoff,
            self.backend.stage_runner.agent_adapter,
            output_dir=self._stage_dir(run_path, "reviewed_part_create"),
        )

    def review_part_result(
        self,
        run_id: str,
        *,
        child_run_id: str | None = None,
        root: str | Path | None = None,
        expected_stl: bool = True,
    ) -> dict[str, Any]:
        """Review one child run produced by the reviewed single-part create bridge."""
        run_path = self.backend.resolve_run(run_id, root=root)
        handoff = self._find_artifact(run_path, "reviewed_handoff")
        child_run = self._resolve_child_run(run_path, child_run_id)
        return self._run_action(
            run_path,
            "part_result_review",
            run_part_result_review_pipeline,
            handoff,
            child_run,
            output_dir=self._stage_dir(run_path, "part_result_review"),
            expected_stl=expected_stl,
        )

    def _run_action(
        self,
        run_path: Path,
        action: str,
        operation: Callable[..., dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if action not in ACTION_NAMES:
            raise ValueError(f"unsupported workflow console action: {action}")
        result = operation(*args, **kwargs)
        summary = _sanitize_action_summary(action, result)
        self._record_action(run_path, summary)
        return {
            "action": action,
            "stage_count": 1,
            "summary": summary,
            "run": _public_run_summary(self.backend.read_run_metadata(run_path)),
        }

    def _find_artifact(self, run_path: Path, artifact_key: str) -> Path:
        for relative in ACTION_ARTIFACTS[artifact_key]:
            path = self.backend._require_child_path(run_path, relative)
            if path.exists():
                return path
        names = ", ".join(ACTION_ARTIFACTS[artifact_key])
        raise FileNotFoundError(f"workflow console action artifact not found: {names}")

    def _stage_dir(self, run_path: Path, action: str) -> Path:
        return self.backend._require_child_path(run_path, ACTION_STAGE_FOLDERS[action])

    def _resolve_child_run(self, run_path: Path, child_run_id: str | None) -> Path:
        if child_run_id is not None:
            self.backend._require_safe_run_id(child_run_id)
            child_path = self.backend._require_child_path(run_path, f"05_single_create/{child_run_id}")
            if not child_path.is_dir():
                raise FileNotFoundError(f"workflow console child run not found: {child_run_id}")
            return child_path

        lineage = _read_json_if_present(self._find_artifact(run_path, "single_create_lineage"))
        inferred = lineage.get("child_run_id") if isinstance(lineage, dict) else None
        if not isinstance(inferred, str) or not inferred:
            raise FileNotFoundError("workflow console child run id is missing from lineage.json")
        return self._resolve_child_run(run_path, inferred)

    def _record_action(self, run_path: Path, summary: dict[str, Any]) -> None:
        runtime_path = self.backend._require_child_path(run_path, "logs/runtime.json")
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = _read_json_if_present(runtime_path) or {}
        console = runtime.setdefault("workflow_console", {})
        actions = console.setdefault("actions", [])
        entry = {
            "action": summary.get("action"),
            "status": summary.get("status"),
            "success": summary.get("success"),
            "stage_count": 1,
        }
        actions.append(entry)
        console["latest_action"] = entry
        console["action_count"] = len(actions)
        runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_action_summary(action: str, result: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "action": action,
        "status": _safe_text(result.get("status")),
        "success": result.get("success") if isinstance(result.get("success"), bool) else None,
        "stage_count": 1,
        "diagnostic_codes": [],
        "artifacts": [],
        "files": {},
    }
    diagnostic_codes = _collect_diagnostic_codes(result)
    if diagnostic_codes:
        summary["diagnostic_codes"] = diagnostic_codes
    files = _sanitize_files(result.get("files"))
    if files:
        summary["files"] = files
    artifacts = _collect_artifact_names(result)
    if artifacts:
        summary["artifacts"] = artifacts
    child_result = _sanitize_public_value(result.get("child_result"))
    if isinstance(child_result, dict):
        summary["child_result"] = child_result
    return {key: value for key, value in summary.items() if value not in (None, [], {})}


def _public_run_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _safe_text(metadata.get("run_id")),
        "status": _sanitize_public_value(metadata.get("status")),
        "report_summary": _sanitize_public_value(metadata.get("report_summary")),
        "reviewed_part_summary": _sanitize_public_value(metadata.get("reviewed_part_summary")),
        "artifacts": [
            {"name": item["name"]}
            for item in metadata.get("artifacts", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ],
        "downloadables": [
            {"name": item["name"]}
            for item in metadata.get("downloadables", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ],
    }


def _collect_diagnostic_codes(result: dict[str, Any]) -> list[str]:
    codes = []
    for value in result.values():
        if not isinstance(value, dict):
            continue
        for code in value.get("diagnostic_codes", []):
            safe = _safe_text(code)
            if safe is not None and safe not in codes:
                codes.append(safe)
            if len(codes) == 20:
                return codes
    return codes


def _collect_artifact_names(result: dict[str, Any]) -> list[str]:
    names = []
    for key, value in result.items():
        if key in {"agent_trace", "child_result"}:
            continue
        if isinstance(value, dict):
            artifact_type = value.get("artifact_type")
            if isinstance(artifact_type, str):
                filename = _artifact_filename(artifact_type)
                if filename not in names:
                    names.append(filename)
    return names


def _artifact_filename(artifact_type: str) -> str:
    if artifact_type.endswith(".json"):
        return Path(artifact_type).name
    return f"{artifact_type}.json"


def _sanitize_files(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    files = {}
    for key, item in value.items():
        safe_key = _safe_text(key)
        safe_value = _basename_text(item)
        if safe_key is not None and safe_value is not None:
            files[safe_key] = safe_value
    return files


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, list):
        return [item for item in (_sanitize_public_value(item) for item in value) if item is not None]
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if not isinstance(value, dict):
        return None
    public = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if key in BLOCKED_PUBLIC_KEYS or _contains_secret_marker(lowered):
            continue
        safe_key = _safe_text(key)
        safe_value = _sanitize_public_value(item)
        if safe_key is not None and safe_value is not None:
            public[safe_key] = safe_value
    return public


def _basename_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    safe = _safe_text(value)
    if safe is not None and safe == value:
        return safe
    try:
        return Path(value).name
    except (OSError, ValueError):
        return None


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return str(value) if isinstance(value, (int, float, bool)) else None
    lowered = value.lower()
    if _contains_secret_marker(lowered):
        return None
    if ":\\" in value or "\\\\" in value:
        return None
    if "/" in value or "\\" in value:
        return Path(value).name
    return value[:160]


def _contains_secret_marker(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "api_key",
            "apikey",
            "password",
            "secret",
            "token",
            "bearer ",
            "env",
        )
    )


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"workflow console action artifact must be a JSON object: {path.name}")
    return value
