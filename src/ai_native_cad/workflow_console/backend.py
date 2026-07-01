"""Dependency-free local backend facade for workflow-console operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.pipeline.runner import PROJECT_ROOT
from ai_native_cad.workflow_console.stage_runner import (
    READABLE_ARTIFACTS,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_RUNNING_OR_INCOMPLETE,
    STATUS_SUCCESS,
    STATUS_UNKNOWN,
    SUPPORTED_STAGES,
    StageRunner,
    _safe_run_name,
)
from ai_native_cad.workflow_control import (
    ASK_USER,
    PROCEED_WITH_ASSUMPTIONS,
    RETURN_TO_PLANNING,
    RETURN_TO_REQUIREMENT,
    REVISE_EXISTING_MODEL,
)

DOWNLOADABLE_FILES = ("model.step", "model.stl", "preview.png", "model.py")
EDITABLE_ARTIFACTS = {"requirement.json", "planning_artifact.json", "input_ir.json"}
GATE_DECISION_ACTIONS = {
    "approve",
    "reject",
    "return",
    "override",
    PROCEED_WITH_ASSUMPTIONS,
    ASK_USER,
    RETURN_TO_REQUIREMENT,
    RETURN_TO_PLANNING,
    REVISE_EXISTING_MODEL,
}
GATE_DECISION_STAGES = SUPPORTED_STAGES | {"review", "outputs"}


class WorkflowConsoleBackend:
    """Local single-user backend scaffold backed by existing run artifacts."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        run_roots: tuple[str | Path, ...] | None = None,
        stage_runner: StageRunner | None = None,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.run_roots = tuple(Path(root) for root in (run_roots or ("outputs", "runs")))
        self.stage_runner = stage_runner or StageRunner(self.project_root)

    def list_runs(self) -> list[dict[str, Any]]:
        """List existing run directories under outputs/ and runs/."""
        runs: list[dict[str, Any]] = []
        for root in self._resolved_run_roots():
            if not root.exists():
                continue
            for child in sorted(root.iterdir(), key=lambda path: path.name):
                if child.is_dir() and _has_workflow_artifact(child):
                    runs.append(self.read_run_metadata(child))
        return sorted(runs, key=lambda item: (item.get("updated_at") or "", item["run_id"]), reverse=True)

    def create_workflow_from_prompt(
        self,
        prompt: str,
        run_name: str | None = None,
        output_root: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the existing Text -> CAD workflow and return run metadata."""
        context: dict[str, Any] = {"overrides": overrides or {}}
        if output_root is not None:
            context["output_root"] = output_root
        if run_name is not None:
            root = Path(output_root) if output_root is not None else self.project_root / "outputs"
            if not root.is_absolute():
                root = self.project_root / root
            context["output_dir"] = root / _safe_run_name(run_name)
        result = self.stage_runner.run_text_pipeline(prompt, context=context)
        metadata = self.read_run_metadata(result["output_dir"])
        return {"result": result, "run": metadata}

    def create_run(
        self,
        prompt: str,
        run_name: str | None = None,
        output_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Create a local run directory without executing workflow stages."""
        context: dict[str, Any] = {}
        if run_name is not None:
            context["run_name"] = run_name
        if output_root is not None:
            context["output_root"] = output_root
        result = self.stage_runner.create_run(prompt, context=context)
        return {"result": result, "run": self.read_run_metadata(result["output_dir"])}

    def create_run_by_id(
        self,
        run_id: str,
        prompt: str,
        root: str | Path = "outputs",
    ) -> dict[str, Any]:
        """Create a local run from a path-safe id under a configured run root."""
        self._require_safe_run_id(run_id)
        run_root = self._resolve_run_root(root)
        output_dir = self._require_child_path(run_root, run_id)
        if output_dir.exists():
            raise FileExistsError(f"workflow console run already exists: {run_id}")
        result = self.stage_runner.create_run(prompt, context={"output_dir": output_dir})
        return {"result": result, "run": self.read_run_metadata(result["output_dir"])}

    def run_stage(
        self,
        run_dir: str | Path,
        stage: str,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a supported deterministic stage for an existing local run."""
        if stage not in SUPPORTED_STAGES:
            raise ValueError(f"unsupported workflow console stage: {stage}")
        run_path = self._require_project_path(Path(run_dir))
        result = self.stage_runner.run_stage(stage, run_path, prompt=prompt, context=context)
        return {"result": result, "run": self.read_run_metadata(run_path)}

    def run_stage_by_id(
        self,
        run_id: str,
        stage: str,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run a supported deterministic stage for a path-safe run id."""
        return self.run_stage(self.resolve_run(run_id, root=root), stage, prompt=prompt, context=context)

    def record_gate_decision_by_id(
        self,
        run_id: str,
        stage: str,
        action: str,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Record a user gate decision for a path-safe run id."""
        return self.record_gate_decision(
            self.resolve_run(run_id, root=root),
            stage=stage,
            action=action,
            reason=reason,
            payload=payload,
        )

    def record_gate_decision(
        self,
        run_dir: str | Path,
        stage: str,
        action: str,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a local gate decision to logs/runtime.json."""
        if stage not in GATE_DECISION_STAGES:
            raise ValueError(f"unsupported workflow console gate decision stage: {stage}")
        if action not in GATE_DECISION_ACTIONS:
            raise ValueError(f"unsupported workflow console gate decision action: {action}")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("workflow console gate decision payload must be a dictionary")

        run_path = self._require_project_path(Path(run_dir))
        runtime_path = self._require_child_path(run_path, "logs/runtime.json")
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = _read_json_if_present(runtime_path) or {}
        console = runtime.setdefault("workflow_console", {})
        decisions = console.setdefault("gate_decisions", [])
        decision = {
            "stage": stage,
            "action": action,
            "timestamp": _now_timestamp(),
        }
        if reason is not None:
            decision["reason"] = reason
        if payload:
            decision["payload"] = payload
        decisions.append(decision)
        console["latest_gate_decision"] = decision
        console["gate_decision_count"] = len(decisions)
        _write_json(runtime_path, runtime)
        return {"decision": decision, "run": self.read_run_metadata(run_path)}

    def resolve_run(self, run_id: str, root: str | Path | None = None) -> Path:
        """Resolve a run id under configured run roots without accepting paths."""
        self._require_safe_run_id(run_id)
        search_roots = [self._resolve_run_root(root)] if root is not None else self._resolved_run_roots()
        for run_root in search_roots:
            candidate = self._require_child_path(run_root, run_id)
            if candidate.is_dir() and _has_workflow_artifact(candidate):
                return candidate
        root_labels = ", ".join(str(path) for path in search_roots)
        raise FileNotFoundError(f"workflow console run not found: {run_id} under {root_labels}")

    def read_run_metadata_by_id(self, run_id: str, root: str | Path | None = None) -> dict[str, Any]:
        """Return run metadata for a path-safe run id."""
        return self.read_run_metadata(self.resolve_run(run_id, root=root))

    def read_run_metadata(self, run_dir: str | Path) -> dict[str, Any]:
        """Return artifact metadata, downloadables, and derived status for a run."""
        path = self._require_project_path(Path(run_dir))
        stat = path.stat()
        return {
            "run_id": path.name,
            "run_dir": str(path),
            "root": str(path.parent),
            "updated_at": _timestamp(stat.st_mtime),
            "status": self.read_run_status(path),
            "stage_history": self.read_stage_history(path),
            "gate_history": self.read_gate_history(path),
            "report_summary": self.read_report_summary(path),
            "artifacts": self.list_artifacts(path),
            "downloadables": self.list_downloadables(path),
        }

    def read_stage_history(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """Return path-free workflow console stage history for a run."""
        path = self._require_project_path(Path(run_dir))
        runtime = _read_json_if_present(path / "logs" / "runtime.json") or {}
        stages = ((runtime.get("workflow_console") or {}).get("stages") or [])
        history = []
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            history.append({
                key: value
                for key, value in stage.items()
                if key in {"stage", "status", "timestamp", "flow_decision", "rework_decision"}
            })
        return history

    def read_report_summary(self, run_dir: str | Path) -> dict[str, Any]:
        """Return a compact report/trace summary for the local console UI."""
        path = self._require_project_path(Path(run_dir))
        requirement = _read_json_if_present(path / "requirement.json")
        planning = _read_json_if_present(path / "planning_artifact.json")
        report = _read_json_if_present(path / "report.json")
        trace = _read_json_if_present(path / "agent_trace.json")
        warnings = list((report or {}).get("warnings") or [])
        errors = list((report or {}).get("errors") or [])
        flow_decision = (report or {}).get("flow_decision") or (trace or {}).get("final_flow_decision") or {}
        rework_decision = (report or {}).get("rework_decision") or (trace or {}).get("rework_decision") or {}
        requirement_summary = _compact_requirement_summary(requirement)
        planning_summary = _compact_planning_summary(planning)
        return {
            "report_present": report is not None,
            "trace_present": trace is not None,
            "status": (report or {}).get("status"),
            "success": (report or {}).get("success"),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "warnings": [_compact_issue(item) for item in warnings[:3]],
            "errors": [_compact_issue(item) for item in errors[:3]],
            "flow_action": flow_decision.get("action"),
            "flow_to_stage": flow_decision.get("to_stage") or flow_decision.get("proceed_to"),
            "rework_action": rework_decision.get("action"),
            "rework_to_stage": rework_decision.get("to_stage"),
            "attempts": (trace or {}).get("total_attempts"),
            "final_selected_candidate": (trace or {}).get("final_selected_candidate"),
            "requirement_summary": requirement_summary,
            "planning_summary": planning_summary,
            "requirement_flow_decision": requirement_summary["flow_decision"],
            "planning_flow_gate": planning_summary["flow_gate"],
        }

    def read_gate_history(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """Return path-free workflow console gate decision history for a run."""
        path = self._require_project_path(Path(run_dir))
        runtime = _read_json_if_present(path / "logs" / "runtime.json") or {}
        decisions = ((runtime.get("workflow_console") or {}).get("gate_decisions") or [])
        history = []
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            history.append({
                key: value
                for key, value in decision.items()
                if key in {"stage", "action", "reason", "timestamp"}
            })
        return history

    def list_artifacts_by_id(self, run_id: str, root: str | Path | None = None) -> list[dict[str, Any]]:
        """List known readable artifacts present for a path-safe run id."""
        return self.list_artifacts(self.resolve_run(run_id, root=root))

    def list_artifacts(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """List known readable artifacts present in a run directory."""
        path = self._require_project_path(Path(run_dir))
        artifacts = []
        for name in sorted(READABLE_ARTIFACTS):
            artifact_path = path / name
            if artifact_path.exists():
                artifacts.append(_file_metadata(name, artifact_path))
        return artifacts

    def read_artifact_by_id(self, run_id: str, artifact: str, root: str | Path | None = None) -> dict[str, Any]:
        """Read a whitelisted artifact from a path-safe run id."""
        return self.read_artifact(self.resolve_run(run_id, root=root), artifact)

    def write_artifact_by_id(
        self,
        run_id: str,
        artifact: str,
        content: dict[str, Any],
        root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Write an editable JSON artifact for a path-safe run id."""
        return self.write_artifact(self.resolve_run(run_id, root=root), artifact, content)

    def write_artifact(
        self,
        run_dir: str | Path,
        artifact: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and write an editable workflow JSON artifact."""
        if artifact not in EDITABLE_ARTIFACTS:
            raise ValueError(f"artifact is not editable by the workflow console: {artifact}")
        if not isinstance(content, dict):
            raise ValueError(f"workflow console editable artifact must be a JSON object: {artifact}")
        _validate_editable_artifact(artifact, content)

        run_path = self._require_project_path(Path(run_dir))
        artifact_path = self._require_child_path(run_path, artifact)
        _write_json(artifact_path, content)
        edit = self._record_artifact_edit(run_path, artifact)
        return {
            "artifact": self.read_artifact(run_path, artifact),
            "edit": edit,
            "run": self.read_run_metadata(run_path),
        }

    def read_artifact(self, run_dir: str | Path, artifact: str) -> dict[str, Any]:
        """Read a whitelisted artifact by relative artifact name."""
        if artifact not in READABLE_ARTIFACTS:
            raise ValueError(f"artifact is not readable by the workflow console: {artifact}")
        run_path = self._require_project_path(Path(run_dir))
        artifact_path = self._require_child_path(run_path, artifact)
        if not artifact_path.exists():
            raise FileNotFoundError(str(artifact_path))
        text = artifact_path.read_text(encoding="utf-8")
        return {
            **_file_metadata(artifact, artifact_path),
            "content": json.loads(text) if artifact_path.suffix == ".json" else text,
        }

    def _record_artifact_edit(self, run_path: Path, artifact: str) -> dict[str, Any]:
        runtime_path = self._require_child_path(run_path, "logs/runtime.json")
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = _read_json_if_present(runtime_path) or {}
        console = runtime.setdefault("workflow_console", {})
        edits = console.setdefault("artifact_edits", [])
        edit = {
            "artifact": artifact,
            "timestamp": _now_timestamp(),
        }
        edits.append(edit)
        console["latest_artifact_edit"] = edit
        console["artifact_edit_count"] = len(edits)
        _write_json(runtime_path, runtime)
        return edit

    def list_downloadables_by_id(self, run_id: str, root: str | Path | None = None) -> list[dict[str, Any]]:
        """List downloadable files for a path-safe run id."""
        return self.list_downloadables(self.resolve_run(run_id, root=root))

    def list_downloadables(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """List generated output files that can be served or downloaded."""
        path = self._require_project_path(Path(run_dir))
        return [
            _file_metadata(name, path / name)
            for name in DOWNLOADABLE_FILES
            if (path / name).exists()
        ]

    def read_run_status(self, run_dir: str | Path) -> dict[str, Any]:
        """Derive status from report.json and agent_trace.json when present."""
        path = self._require_project_path(Path(run_dir))
        requirement = _read_json_if_present(path / "requirement.json")
        planning = _read_json_if_present(path / "planning_artifact.json")
        report = _read_json_if_present(path / "report.json")
        trace = _read_json_if_present(path / "agent_trace.json")
        runtime = _read_json_if_present(path / "logs" / "runtime.json")
        runtime_stage = ((runtime or {}).get("workflow_console") or {}).get("latest_stage") or {}
        latest_gate_decision = ((runtime or {}).get("workflow_console") or {}).get("latest_gate_decision")
        latest_artifact_edit = ((runtime or {}).get("workflow_console") or {}).get("latest_artifact_edit")
        flow_decision = (report or {}).get("flow_decision") or (trace or {}).get("final_flow_decision")
        rework_decision = (report or {}).get("rework_decision") or (trace or {}).get("rework_decision")
        status = (report or {}).get("status")
        if status is None and report:
            status = STATUS_SUCCESS if report.get("success") else STATUS_FAILED
        if status is None and trace:
            status = STATUS_BLOCKED if rework_decision and rework_decision.get("action") == "return" else STATUS_RUNNING_OR_INCOMPLETE
        if status is None and runtime_stage:
            status = runtime_stage.get("status")
        return {
            "status": status or STATUS_UNKNOWN,
            "success": (report or {}).get("success"),
            "stage": runtime_stage.get("stage"),
            "blocked_stage": (report or {}).get("blocked_stage") or (trace or {}).get("text_pipeline", {}).get("blocked_stage"),
            "attempts": (trace or {}).get("total_attempts"),
            "final_selected_candidate": (trace or {}).get("final_selected_candidate"),
            "flow_decision": flow_decision,
            "rework_decision": rework_decision,
            "gate_decision": latest_gate_decision,
            "artifact_edit": latest_artifact_edit,
            "runtime": runtime_stage or None,
            "requirement_summary": _compact_requirement_summary(requirement),
            "planning_summary": _compact_planning_summary(planning),
        }

    def _resolved_run_roots(self) -> list[Path]:
        roots = []
        for root in self.run_roots:
            path = root if root.is_absolute() else self.project_root / root
            roots.append(self._require_project_path(path))
        return roots

    def _resolve_run_root(self, root: str | Path) -> Path:
        candidate = Path(root)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        resolved = self._require_project_path(candidate)
        allowed_roots = self._resolved_run_roots()
        if resolved not in allowed_roots:
            raise ValueError(f"workflow console run root is not configured: {root}")
        return resolved

    def _require_safe_run_id(self, run_id: str) -> None:
        if not run_id or run_id in {".", ".."}:
            raise ValueError("workflow console run id must be a non-empty directory name")
        if "/" in run_id or "\\" in run_id or ":" in run_id:
            raise ValueError(f"workflow console run id must not contain path separators: {run_id}")
        path = Path(run_id)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError(f"workflow console run id must be a single relative directory name: {run_id}")

    def _require_project_path(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"workflow console paths must stay inside project root: {self.project_root}") from exc
        return resolved

    def _require_child_path(self, root: Path, relative_path: str) -> Path:
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ValueError(f"invalid artifact path: {relative_path}")
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"artifact path must stay inside run directory: {root}") from exc
        return path


def _has_workflow_artifact(path: Path) -> bool:
    return any((path / name).exists() for name in READABLE_ARTIFACTS | set(DOWNLOADABLE_FILES))


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_editable_artifact(artifact: str, content: dict[str, Any]) -> None:
    if artifact == "requirement.json":
        _require_keys(content, artifact, ("part_type", "dimensions"))
        if not isinstance(content.get("part_type"), str) or not content["part_type"]:
            raise ValueError("requirement.json part_type must be a non-empty string")
        if not isinstance(content.get("dimensions"), dict):
            raise ValueError("requirement.json dimensions must be a dictionary")
        if "features" in content and not isinstance(content["features"], dict):
            raise ValueError("requirement.json features must be a dictionary")
        if "requirement_status" in content and not isinstance(content["requirement_status"], dict):
            raise ValueError("requirement.json requirement_status must be a dictionary")
        return

    if artifact == "planning_artifact.json":
        _require_keys(content, artifact, ("artifact_type", "route", "selected_parts", "flow_gate_status"))
        if content.get("artifact_type") != "planning":
            raise ValueError("planning_artifact.json artifact_type must be 'planning'")
        if not isinstance(content.get("route"), dict):
            raise ValueError("planning_artifact.json route must be a dictionary")
        if not isinstance(content.get("selected_parts"), list):
            raise ValueError("planning_artifact.json selected_parts must be a list")
        if not isinstance(content.get("flow_gate_status"), dict):
            raise ValueError("planning_artifact.json flow_gate_status must be a dictionary")
        return

    validation = validate_ir(content)
    if not validation["valid"]:
        codes = ", ".join(error.get("code", "unknown") for error in validation["errors"])
        raise ValueError(f"input_ir.json failed CAD IR validation: {codes}")


def _require_keys(content: dict[str, Any], artifact: str, keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in content]
    if missing:
        raise ValueError(f"{artifact} is missing required fields: {', '.join(missing)}")


def _compact_issue(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            key: value
            for key, value in item.items()
            if key in {"code", "message", "dimension", "feature", "check"}
        }
    return {"message": str(item)}


def _compact_requirement_summary(requirement: dict[str, Any] | None) -> dict[str, Any]:
    requirement = requirement or {}
    missing = [item for item in requirement.get("missing_information", []) if isinstance(item, dict)]
    follow_ups = [item for item in requirement.get("follow_up_requests", []) if isinstance(item, dict)]
    status = requirement.get("requirement_status") if isinstance(requirement.get("requirement_status"), dict) else {}
    decision = status.get("flow_decision") if isinstance(status.get("flow_decision"), dict) else {}
    return {
        "present": bool(requirement),
        "check_level": requirement.get("check_level"),
        "complete_for_generation": status.get("complete_for_generation"),
        "needs_user_input": status.get("needs_user_input"),
        "assumptions": _compact_text_list(requirement.get("assumptions", [])),
        "missing_information": _compact_field_collection(missing),
        "follow_up_requests": _compact_field_collection(follow_ups),
        "flow_decision": _compact_flow_decision(decision),
    }


def _compact_planning_summary(planning: dict[str, Any] | None) -> dict[str, Any]:
    planning = planning or {}
    gate = planning.get("flow_gate_status") if isinstance(planning.get("flow_gate_status"), dict) else {}
    risks = [item for item in planning.get("risk_notes", []) if isinstance(item, dict)]
    blocking = [item for item in gate.get("blocking_reasons", []) if isinstance(item, dict)]
    decision = gate.get("rework_decision") if isinstance(gate.get("rework_decision"), dict) else {}
    return {
        "present": bool(planning),
        "route": (planning.get("route") or {}).get("selected") if isinstance(planning.get("route"), dict) else None,
        "flow_gate": {
            "status": gate.get("status"),
            "blocking_count": len(blocking),
            "blocking_reasons": [_compact_field_item(item) for item in blocking[:3]],
            "rework_decision": _compact_flow_decision(decision),
        },
        "risk_notes": _compact_field_collection(risks),
    }


def _compact_flow_decision(decision: dict[str, Any] | None) -> dict[str, Any]:
    decision = decision or {}
    reasons = decision.get("reasons", [])
    assumptions = decision.get("assumptions", [])
    return {
        "action": decision.get("action"),
        "from_stage": decision.get("from_stage"),
        "to_stage": decision.get("to_stage") or decision.get("proceed_to"),
        "owner_stage": decision.get("owner_stage"),
        "reason_count": len(reasons) if isinstance(reasons, list) else 0,
        "assumption_count": len(assumptions) if isinstance(assumptions, list) else 0,
    }


def _compact_field_collection(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(items),
        "fields": [
            str(item.get("field"))
            for item in items
            if item.get("field") is not None and _safe_summary_text(item.get("field")) is not None
        ][:8],
        "items": [_compact_field_item(item) for item in items[:3]],
    }


def _compact_field_item(item: dict[str, Any]) -> dict[str, Any]:
    allowed = {"code", "category", "field", "severity", "ask_user", "default_used", "blocks_cad_ir"}
    return {
        key: value
        for key, value in item.items()
        if key in allowed and _safe_summary_text(value) is not None
    }


def _compact_text_list(items: Any) -> dict[str, Any]:
    values = items if isinstance(items, list) else []
    compact = []
    for item in values:
        text = _safe_summary_text(item)
        if text is not None:
            compact.append(text)
        if len(compact) == 3:
            break
    return {"count": len(values), "items": compact}


def _safe_summary_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return str(value) if isinstance(value, (int, float, bool)) else None
    lowered = value.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer ")):
        return None
    if ":\\" in value or "/" in value or "\\\\" in value:
        return None
    return value[:160]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_metadata(name: str, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "updated_at": _timestamp(stat.st_mtime),
    }


def _timestamp(seconds: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _now_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
