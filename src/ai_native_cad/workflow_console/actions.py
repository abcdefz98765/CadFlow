"""Safe staged action wrappers for the local workflow console."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
from ai_native_cad.workflow_console.workflow_review import (
    build_workflow_review,
    compact_workflow_review_summary,
    write_workflow_review_files,
)

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
    "save_stage_review",
    "run_rework",
    "create_workflow_review",
}

STAGE_REVIEW_STAGES = {
    "requirement",
    "design_brief",
    "assembly_plan",
    "candidate_parts",
    "part_request",
    "part_review",
    "handoff",
    "single_part_result",
}
REWORK_EXECUTION_STATUSES = {
    "completed",
    "needs_revision",
    "blocked",
    "blocked_unsupported_target",
    "blocked_invalid_review",
}
SUPPORTED_REWORK_TARGETS = {"workflow_review"}
KNOWN_REWORK_TARGETS = {"assembly_plan", "part_request", "workflow_review"}
STAGE_REVIEW_STATUSES = {"approved", "needs_revision", "blocked"}
STAGE_REWORK_TARGETS = {
    "requirement",
    "design_brief",
    "assembly_plan",
    "candidate_parts",
    "part_request",
    "part_review",
    "handoff",
    "single_part_result",
    "workflow_review",
}
STAGE_REVIEW_NOTE_LIMIT = 1200
STAGE_REVIEW_CHANGE_LIMIT = 12
STAGE_REVIEW_CHANGE_TEXT_LIMIT = 240

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

    def save_stage_review(
        self,
        run_id: str,
        *,
        stage: str,
        review_status: str,
        user_notes: str | None = None,
        target_rework_stage: str | None = None,
        requested_changes: list[str] | str | None = None,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Save one deterministic local stage review without rerunning workflow stages."""
        run_path = self.backend.resolve_run(run_id, root=root)
        artifact = _build_stage_review_artifact(
            stage=stage,
            review_status=review_status,
            user_notes=user_notes,
            target_rework_stage=target_rework_stage,
            requested_changes=requested_changes,
        )
        artifact_path = self.backend._require_child_path(run_path, "stage_review.json")
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = _compact_stage_review_summary(artifact)
        self._record_action(run_path, {"action": "save_stage_review", "status": review_status, "success": True, "stage_count": 0})
        return {
            "action": "save_stage_review",
            "stage_count": 0,
            "summary": summary,
            "run": _public_run_summary(self.backend.read_run_metadata(run_path)),
        }

    def create_workflow_review(
        self,
        run_id: str,
        *,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Create deterministic human-readable workflow review artifacts."""
        run_path = self.backend.resolve_run(run_id, root=root)
        metadata = self.backend.read_run_metadata(run_path)
        review = build_workflow_review(metadata)
        files = write_workflow_review_files(run_path, review)
        summary = compact_workflow_review_summary(review)
        self._record_action(run_path, {"action": "create_workflow_review", "status": summary.get("overall_status"), "success": True, "stage_count": 0})
        return {
            "action": "create_workflow_review",
            "stage_count": 0,
            "summary": summary,
            "files": files,
            "run": _public_run_summary(self.backend.read_run_metadata(run_path)),
        }

    def run_rework(
        self,
        run_id: str,
        *,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute one explicit rework request from saved stage_review.json."""
        run_path = self.backend.resolve_run(run_id, root=root)
        stage_review_path = self.backend._require_child_path(run_path, "stage_review.json")
        stage_review = _read_json_if_present(stage_review_path)
        if stage_review is None:
            raise FileNotFoundError("workflow console rework requires stage_review.json")
        _validate_stage_review_for_rework(stage_review)
        target = stage_review.get("target_rework_stage")
        if target not in KNOWN_REWORK_TARGETS:
            raise ValueError(f"unsupported workflow console rework target stage: {target}")

        if target not in SUPPORTED_REWORK_TARGETS:
            decision = _build_rework_decision(
                parent_run_id=run_path.name,
                stage_review=stage_review,
                execution_status="blocked_unsupported_target",
                diagnostic_codes=["rework.unsupported_target_stage"],
                created_artifacts=[],
                child_run_id=None,
            )
            self._write_rework_decision(run_path, decision)
            self._record_action(run_path, {"action": "run_rework", "status": decision["execution_status"], "success": False, "stage_count": 0})
            return {
                "action": "run_rework",
                "stage_count": 0,
                "summary": _compact_rework_decision_summary(decision),
                "decision": _sanitize_public_value(decision),
                "run": _public_run_summary(self.backend.read_run_metadata(run_path)),
            }

        child_path = self._next_rework_child_dir(run_path, target)
        child_path.mkdir(parents=True, exist_ok=False)
        child_run_id = child_path.name
        stage_review_snapshot = _sanitize_stage_review_snapshot(stage_review)
        (child_path / "stage_review.json").write_text(
            json.dumps(stage_review_snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (child_path / "parent_run_id.txt").write_text(f"{run_path.name}\n", encoding="utf-8")
        lineage = {
            "schema_version": 1,
            "relationship": "explicit_rework_child",
            "parent_run_id": run_path.name,
            "child_run_id": child_run_id,
            "target_rework_stage": target,
        }
        (child_path / "lineage.json").write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        parent_metadata = self.backend.read_run_metadata(run_path)
        decision = _build_rework_decision(
            parent_run_id=run_path.name,
            stage_review=stage_review,
            execution_status="completed",
            diagnostic_codes=["rework.workflow_review_refreshed"],
            created_artifacts=["workflow_review.json", "workflow_review.md", "lineage.json", "stage_review.json"],
            child_run_id=child_run_id,
        )
        child_metadata = {
            **parent_metadata,
            "run_id": child_run_id,
            "stage_review_summary": _compact_stage_review_summary(stage_review_snapshot),
            "rework_decision_summary": _compact_rework_decision_summary(decision),
            "child_runs": [],
            "artifacts": _merge_artifact_name_rows(
                parent_metadata.get("artifacts"),
                ("stage_review.json", "lineage.json", "rework_decision.json"),
            ),
        }
        review = build_workflow_review(child_metadata)
        files = write_workflow_review_files(child_path, review)
        decision["created_artifacts"] = sorted(set(decision["created_artifacts"] + list(files.values())))
        self._write_rework_decision(run_path, decision)
        self._write_rework_decision(child_path, decision)
        self._record_action(run_path, {"action": "run_rework", "status": decision["execution_status"], "success": True, "stage_count": 1})
        return {
            "action": "run_rework",
            "stage_count": 1,
            "summary": _compact_rework_decision_summary(decision),
            "decision": _sanitize_public_value(decision),
            "files": files,
            "run": _public_run_summary(self.backend.read_run_metadata(run_path)),
        }

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
            "stage_count": summary.get("stage_count", 1),
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
            "stage_count": summary.get("stage_count", 1),
        }
        actions.append(entry)
        console["latest_action"] = entry
        console["action_count"] = len(actions)
        runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_rework_decision(self, run_path: Path, decision: dict[str, Any]) -> None:
        path = self.backend._require_child_path(run_path, "rework_decision.json")
        path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _next_rework_child_dir(self, run_path: Path, target: str) -> Path:
        safe_target = _safe_run_token(target)
        for index in range(1, 10_000):
            child = self.backend._require_child_path(run_path, f"rework_{safe_target}_{index}")
            if not child.exists():
                return child
        raise FileExistsError(f"workflow console rework child id space is exhausted for: {run_path.name}")


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
        "stage_review_summary": _sanitize_public_value(metadata.get("stage_review_summary")),
        "rework_decision_summary": _sanitize_public_value(metadata.get("rework_decision_summary")),
        "workflow_review_summary": _sanitize_public_value(metadata.get("workflow_review_summary")),
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


def _build_stage_review_artifact(
    *,
    stage: str,
    review_status: str,
    user_notes: str | None,
    target_rework_stage: str | None,
    requested_changes: list[str] | str | None,
) -> dict[str, Any]:
    if stage not in STAGE_REVIEW_STAGES:
        raise ValueError(f"unsupported workflow console stage review stage: {stage}")
    if review_status not in STAGE_REVIEW_STATUSES:
        raise ValueError(f"unsupported workflow console stage review status: {review_status}")
    if target_rework_stage is not None and target_rework_stage not in STAGE_REWORK_TARGETS:
        raise ValueError(f"unsupported workflow console rework target stage: {target_rework_stage}")
    if review_status == "needs_revision" and target_rework_stage is None:
        raise ValueError("workflow console stage review target_rework_stage is required for needs_revision")
    if review_status != "needs_revision":
        target_rework_stage = None

    changes = _sanitize_requested_changes(requested_changes)
    artifact = {
        "schema_version": 1,
        "stage": stage,
        "review_status": review_status,
        "user_notes": _sanitize_note(user_notes),
        "target_rework_stage": target_rework_stage,
        "requested_changes": changes,
        "created_by": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_codes": [_stage_review_diagnostic_code(review_status)],
    }
    return {key: value for key, value in artifact.items() if value not in (None, [], "")}


def _compact_stage_review_summary(artifact: dict[str, Any] | None) -> dict[str, Any]:
    artifact = artifact or {}
    changes = artifact.get("requested_changes") if isinstance(artifact.get("requested_changes"), list) else []
    return {
        "present": bool(artifact),
        "schema_version": artifact.get("schema_version") if isinstance(artifact.get("schema_version"), int) else None,
        "stage": _safe_text(artifact.get("stage")),
        "review_status": _safe_text(artifact.get("review_status")),
        "target_rework_stage": _safe_text(artifact.get("target_rework_stage")),
        "requested_changes_count": len(changes),
        "user_notes_preview": _safe_text(artifact.get("user_notes")),
        "diagnostic_codes": [
            code
            for code in (_safe_text(item) for item in artifact.get("diagnostic_codes", []))
            if code is not None
        ][:20],
    }


def _validate_stage_review_for_rework(stage_review: dict[str, Any]) -> None:
    if stage_review.get("review_status") != "needs_revision":
        raise ValueError("workflow console rework requires stage_review review_status=needs_revision")
    target = stage_review.get("target_rework_stage")
    if not isinstance(target, str) or not target:
        raise ValueError("workflow console rework requires target_rework_stage")
    if not isinstance(stage_review.get("stage"), str) or stage_review.get("stage") not in STAGE_REVIEW_STAGES:
        raise ValueError("workflow console rework requires a valid source stage")


def _build_rework_decision(
    *,
    parent_run_id: str,
    stage_review: dict[str, Any],
    execution_status: str,
    diagnostic_codes: list[str],
    created_artifacts: list[str],
    child_run_id: str | None,
) -> dict[str, Any]:
    if execution_status not in REWORK_EXECUTION_STATUSES:
        raise ValueError(f"unsupported workflow console rework execution status: {execution_status}")
    requested_changes = [
        safe
        for safe in (_safe_review_text(str(item), STAGE_REVIEW_CHANGE_TEXT_LIMIT) for item in _as_list(stage_review.get("requested_changes")))
        if safe
    ][:STAGE_REVIEW_CHANGE_LIMIT]
    target = _safe_text(stage_review.get("target_rework_stage"))
    decision = {
        "schema_version": 1,
        "parent_run_id": _safe_text(parent_run_id),
        "source_stage_review": {
            "stage": _safe_text(stage_review.get("stage")),
            "review_status": _safe_text(stage_review.get("review_status")),
            "target_rework_stage": target,
        },
        "execution_status": execution_status,
        "target_rework_stage": target,
        "requested_changes": requested_changes,
        "created_artifacts": sorted(
            {
                safe
                for safe in (_safe_artifact_name(item) for item in created_artifacts)
                if safe is not None
            }
        ),
        "child_run_id": _safe_text(child_run_id) if child_run_id is not None else None,
        "diagnostic_codes": [
            safe
            for safe in (_safe_text(item) for item in diagnostic_codes)
            if safe is not None
        ][:20],
    }
    return decision


def _sanitize_stage_review_snapshot(stage_review: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "schema_version": 1,
            "stage": _safe_text(stage_review.get("stage")),
            "review_status": _safe_text(stage_review.get("review_status")),
            "target_rework_stage": _safe_text(stage_review.get("target_rework_stage")),
            "user_notes": _safe_review_text(str(stage_review.get("user_notes") or ""), STAGE_REVIEW_NOTE_LIMIT),
            "requested_changes": [
                safe
                for safe in (
                    _safe_review_text(str(item), STAGE_REVIEW_CHANGE_TEXT_LIMIT)
                    for item in _as_list(stage_review.get("requested_changes"))
                )
                if safe
            ][:STAGE_REVIEW_CHANGE_LIMIT],
            "diagnostic_codes": [
                safe
                for safe in (_safe_text(item) for item in _as_list(stage_review.get("diagnostic_codes")))
                if safe is not None
            ][:20],
        }.items()
        if value not in (None, [], "")
    }


def _compact_rework_decision_summary(decision: dict[str, Any] | None) -> dict[str, Any]:
    decision = decision or {}
    artifacts = _as_list(decision.get("created_artifacts"))
    changes = _as_list(decision.get("requested_changes"))
    return {
        "present": bool(decision),
        "schema_version": decision.get("schema_version") if isinstance(decision.get("schema_version"), int) else None,
        "execution_status": _safe_text(decision.get("execution_status")),
        "target_rework_stage": _safe_text(decision.get("target_rework_stage")),
        "child_run_id": _safe_text(decision.get("child_run_id")),
        "created_artifact_count": len(artifacts),
        "requested_changes_preview": [
            safe
            for safe in (_safe_text(item) for item in changes[:3])
            if safe is not None
        ],
        "diagnostic_codes": [
            safe
            for safe in (_safe_text(item) for item in _as_list(decision.get("diagnostic_codes")))
            if safe is not None
        ][:20],
    }


def _safe_artifact_name(value: Any) -> str | None:
    safe = _basename_text(value)
    if safe is None or "/" in safe or "\\" in safe or safe in {".", ".."}:
        return None
    return safe


def _merge_artifact_name_rows(existing: Any, names: tuple[str, ...]) -> list[dict[str, str]]:
    merged = []
    seen = set()
    for item in _as_list(existing):
        if not isinstance(item, dict):
            continue
        safe = _safe_artifact_name(item.get("name"))
        if safe is not None and safe not in seen:
            merged.append({"name": safe})
            seen.add(safe)
    for name in names:
        safe = _safe_artifact_name(name)
        if safe is not None and safe not in seen:
            merged.append({"name": safe})
            seen.add(safe)
    return merged


def _safe_run_token(value: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    return safe or "rework"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sanitize_note(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("workflow console stage review notes must be text")
    return _safe_review_text(value.replace("\r\n", "\n").replace("\r", "\n"), STAGE_REVIEW_NOTE_LIMIT)


def _sanitize_requested_changes(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    raw_items = value.splitlines() if isinstance(value, str) else value
    if not isinstance(raw_items, list):
        raise ValueError("workflow console stage review requested_changes must be a list or newline text")
    changes = []
    for item in raw_items:
        if not isinstance(item, str):
            raise ValueError("workflow console stage review requested_changes entries must be text")
        safe = _safe_review_text(item.strip(), STAGE_REVIEW_CHANGE_TEXT_LIMIT)
        if safe:
            changes.append(safe)
        if len(changes) == STAGE_REVIEW_CHANGE_LIMIT:
            break
    return changes


def _safe_review_text(value: str, limit: int) -> str:
    if _contains_secret_marker(value.lower()):
        return ""
    lines = []
    for line in value.splitlines():
        if ":\\" in line or "\\\\" in line:
            continue
        lines.append(line.strip())
    return "\n".join(line for line in lines if line)[:limit]


def _stage_review_diagnostic_code(review_status: str) -> str:
    if review_status == "approved":
        return "stage_review.user_approved"
    if review_status == "blocked":
        return "stage_review.user_blocked"
    return "stage_review.user_requested_rework"


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
