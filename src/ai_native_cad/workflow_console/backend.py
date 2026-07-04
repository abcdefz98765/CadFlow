"""Dependency-free local backend facade for workflow-console operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.agents import DeterministicAgentAdapter, JsonContractProviderError
from ai_native_cad.agents import make_json_contract_adapter_from_env
from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.pipeline.runner import PROJECT_ROOT, run_agent_revision_pipeline
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
from ai_native_cad.workflow_console.workflow_review import compact_workflow_review_summary
from ai_native_cad.workflow_control import (
    ASK_USER,
    PROCEED_WITH_ASSUMPTIONS,
    RETURN_TO_PLANNING,
    RETURN_TO_REQUIREMENT,
    REVISE_EXISTING_MODEL,
)

DOWNLOADABLE_FILES = ("model.step", "model.stl", "preview.png", "model.py")
EDITABLE_ARTIFACTS = {"requirement.json", "planning_artifact.json", "input_ir.json"}
STAGED_READABLE_ARTIFACTS = {
    "assembly_plan.json": ("01_design/assembly_plan.json",),
    "part_create_request.json": ("02_part_request/part_create_request.json",),
    "part_request_review.json": ("03_review/part_request_review.json",),
    "reviewed_part_handoff.json": ("04_handoff/reviewed_part_handoff.json",),
    "part_execution_request.json": ("05_single_create/part_execution_request.json",),
    "lineage.json": ("05_single_create/lineage.json",),
    "part_result_review.json": ("06_part_result_review/part_result_review.json",),
}
STAGED_ARTIFACT_DIRS = {
    "01_design",
    "02_part_request",
    "03_review",
    "04_handoff",
    "05_single_create",
    "06_part_result_review",
}
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
        provider_adapter_factory: Any | None = None,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.run_roots = tuple(Path(root) for root in (run_roots or ("outputs", "runs")))
        self.stage_runner = stage_runner or StageRunner(self.project_root)
        self._provider_adapter_factory = provider_adapter_factory or make_json_contract_adapter_from_env

    def read_provider_config(self) -> dict[str, Any]:
        """Return the active console adapter identity without secrets."""
        return {
            "provider_identity": _compact_adapter_identity(
                dict(getattr(self.stage_runner.agent_adapter, "provider_identity", {}) or {})
            ),
        }

    def configure_provider(
        self,
        provider: str,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Switch the in-process console adapter without accepting secrets."""
        _validate_provider_config_inputs(provider, model, timeout_seconds, max_retries)
        normalized = provider.lower().strip()
        if normalized in {"local", "local/mock", "mock", "deterministic"}:
            self.stage_runner.agent_adapter = DeterministicAgentAdapter()
        elif normalized in {"deepseek", "openai", "oai"}:
            self.stage_runner.agent_adapter = self._provider_adapter_factory(
                normalized,
                model=model,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        else:
            raise ValueError(f"unsupported workflow console provider: {provider}")
        return self.read_provider_config()

    def test_provider_connection(self) -> dict[str, Any]:
        """Run a minimal provider check without writing workflow artifacts."""
        adapter = self.stage_runner.agent_adapter
        identity = _compact_adapter_identity(dict(getattr(adapter, "provider_identity", {}) or {}))
        provider = identity.get("provider") or "local/mock"
        if provider == "local/mock":
            return {
                "status": "ok",
                "provider_identity": identity,
                "operation": "local_provider_check",
            }
        try:
            requirement = adapter.parse_requirement(
                "Make a spacer washer with OD 12 mm, ID 6 mm, thickness 4 mm.",
                context={
                    "workflow_stage": "provider_check",
                    "target_contract": "requirement_connectivity_check",
                },
            )
        except JsonContractProviderError as exc:
            return {
                "status": "failed",
                "provider_identity": identity,
                "operation": "parse_requirement",
                "error": exc.to_dict(),
            }
        except Exception:
            return {
                "status": "failed",
                "provider_identity": identity,
                "operation": "parse_requirement",
                "error": {"type": "provider_connection_error", "category": "client_error", "retryable": False},
            }
        return {
            "status": "ok",
            "provider_identity": identity,
            "operation": "parse_requirement",
            "contract": {
                "part_type": requirement.get("part_type"),
                "dimension_keys": sorted(requirement.get("dimensions", {}).keys())
                if isinstance(requirement.get("dimensions"), dict)
                else [],
            },
        }

    def list_runs(self) -> list[dict[str, Any]]:
        """List existing run directories under outputs/ and runs/."""
        runs: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for root in self._resolved_run_roots():
            if not root.exists():
                continue
            candidates = [root, *sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda path: str(path))]
            for child in candidates:
                if child.name in STAGED_ARTIFACT_DIRS:
                    continue
                resolved = child.resolve()
                if resolved in seen:
                    continue
                if child.is_dir() and _has_workflow_artifact(child):
                    seen.add(resolved)
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

    def run_revision_by_id(
        self,
        parent_run_id: str,
        child_run_id: str | None,
        revision_prompt: str,
        root: str | Path = "outputs",
        child_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run a deterministic CadFlow-native revision from safe parent/child run ids."""
        if not isinstance(revision_prompt, str) or not revision_prompt.strip():
            raise ValueError("workflow console revision prompt must be a non-empty string")
        parent_path = self.resolve_run(parent_run_id, root=root)
        output_root = self._resolve_run_root(child_root if child_root is not None else root)
        if child_run_id is None:
            child_run_id = self._next_revision_child_run_id(parent_path.name, output_root)
        self._require_safe_run_id(child_run_id)
        child_path = self._require_child_path(output_root, child_run_id)
        if child_path.exists():
            raise FileExistsError(f"workflow console revision child already exists: {child_run_id}")
        if child_path == parent_path:
            raise ValueError("workflow console revision child must not overwrite the parent run")
        result = run_agent_revision_pipeline(
            parent_path,
            revision_prompt,
            self.stage_runner.agent_adapter,
            output_dir=child_path,
        )
        return {"result": result, "run": self.read_run_metadata(child_path)}

    def _next_revision_child_run_id(self, parent_run_id: str, output_root: Path) -> str:
        self._require_safe_run_id(parent_run_id)
        for index in range(1, 10_000):
            candidate = f"{parent_run_id}_revision_{index}"
            self._require_safe_run_id(candidate)
            if not self._require_child_path(output_root, candidate).exists():
                return candidate
        raise FileExistsError(f"workflow console revision child id space is exhausted for: {parent_run_id}")

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
            for nested in sorted(run_root.rglob(run_id), key=lambda path: str(path)):
                if nested.name == run_id and nested.is_dir() and _has_workflow_artifact(nested):
                    return self._require_project_path(nested)
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
            "reviewed_part_summary": self.read_reviewed_part_summary(path),
            "stage_review_summary": self.read_stage_review_summary(path),
            "workflow_review_summary": self.read_workflow_review_summary(path),
            "child_runs": self.list_child_runs(path),
            "artifacts": self.list_artifacts(path),
            "downloadables": self.list_downloadables(path),
        }

    def read_stage_review_summary(self, run_dir: str | Path) -> dict[str, Any]:
        """Return a compact sanitized summary of the latest local stage review."""
        path = self._require_project_path(Path(run_dir))
        review = _read_json_if_present(path / "stage_review.json")
        return _compact_stage_review_summary(review)

    def read_workflow_review_summary(self, run_dir: str | Path) -> dict[str, Any]:
        """Return a compact sanitized summary of the deterministic workflow review."""
        path = self._require_project_path(Path(run_dir))
        review = _read_json_if_present(path / "workflow_review.json")
        summary = compact_workflow_review_summary(review)
        summary["artifact_availability"] = {
            "workflow_review_json": (path / "workflow_review.json").exists(),
            "workflow_review_md": (path / "workflow_review.md").exists(),
        }
        return summary

    def read_reviewed_part_summary(self, run_dir: str | Path) -> dict[str, Any]:
        """Return compact reviewed-part workflow summaries for console inspection."""
        path = self._require_project_path(Path(run_dir))
        assembly_plan = _read_first_json(path, ("assembly_plan.json", "01_design/assembly_plan.json"))
        part_request = _read_first_json(path, ("part_create_request.json", "02_part_request/part_create_request.json"))
        part_review = _read_first_json(path, ("part_request_review.json", "03_review/part_request_review.json"))
        handoff = _read_first_json(path, ("reviewed_part_handoff.json", "04_handoff/reviewed_part_handoff.json"))
        lineage = _read_first_json(path, ("lineage.json", "05_single_create/lineage.json"))
        part_result_review = _read_first_json(
            path,
            ("part_result_review.json", "06_part_result_review/part_result_review.json"),
        )
        return {
            "assembly_plan": _compact_assembly_plan_summary(assembly_plan),
            "part_request": _compact_part_request_summary(part_request),
            "part_request_review": _compact_part_request_review_summary(part_review),
            "reviewed_part_handoff": _compact_reviewed_part_handoff_summary(handoff),
            "part_result_review": _compact_part_result_review_summary(part_result_review),
            "lineage": _compact_reviewed_part_lineage_summary(lineage),
        }

    def list_child_runs(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """List child run directories with artifact-backed output."""
        path = self._require_project_path(Path(run_dir))
        children: list[dict[str, Any]] = []
        if not path.exists():
            return children
        for child in sorted(path.rglob("*"), key=lambda item: str(item)):
            if not child.is_dir() or child == path or not _has_workflow_artifact(child):
                continue
            has_downloadable = any((child / name).exists() for name in DOWNLOADABLE_FILES)
            if not has_downloadable and not child.name.startswith("single_part_"):
                continue
            status = self.read_run_status(child)
            children.append({
                "run_id": child.name,
                "status": status.get("status"),
                "stage": status.get("stage"),
                "artifacts": [item["name"] for item in self.list_artifacts(child)],
                "downloadables": [item["name"] for item in self.list_downloadables(child)],
            })
        return children

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
            adapter_activity = _compact_adapter_activity(stage.get("adapter_activity"))
            if adapter_activity is not None:
                history[-1]["adapter_activity"] = adapter_activity
        return history

    def read_report_summary(self, run_dir: str | Path) -> dict[str, Any]:
        """Return a compact report/trace summary for the local console UI."""
        path = self._require_project_path(Path(run_dir))
        requirement = _read_json_if_present(path / "requirement.json")
        planning = _read_json_if_present(path / "planning_artifact.json")
        report = _read_json_if_present(path / "report.json")
        trace = _read_json_if_present(path / "agent_trace.json")
        comparison = _read_json_if_present(path / "comparison.json")
        lineage = _read_json_if_present(path / "lineage.json")
        revision_plan = _read_json_if_present(path / "revision_plan.json")
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
            "revision_summary": _compact_revision_summary(comparison, lineage, revision_plan),
            "negotiation": _compact_negotiation_summary(requirement, planning, report, trace),
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
            item = {
                key: value
                for key, value in decision.items()
                if key in {"stage", "action", "reason", "timestamp"}
            }
            payload_summary = _compact_payload_summary(decision.get("payload"))
            if payload_summary["items"]:
                item["payload_summary"] = payload_summary
            history.append(item)
        return history

    def list_artifacts_by_id(self, run_id: str, root: str | Path | None = None) -> list[dict[str, Any]]:
        """List known readable artifacts present for a path-safe run id."""
        return self.list_artifacts(self.resolve_run(run_id, root=root))

    def list_artifacts(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """List known readable artifacts present in a run directory."""
        path = self._require_project_path(Path(run_dir))
        artifacts = []
        for name in sorted(READABLE_ARTIFACTS):
            artifact_path = _first_existing_artifact_path(path, name)
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
        artifact_path = _first_existing_artifact_path(run_path, artifact)
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
        gate_decision = _compact_gate_decision(latest_gate_decision)
        adapter_activity = _compact_adapter_activity(runtime_stage.get("adapter_activity"))
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
            "gate_decision": gate_decision,
            "artifact_edit": latest_artifact_edit,
            "adapter_activity": adapter_activity,
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
    if any((path / name).exists() for name in READABLE_ARTIFACTS | set(DOWNLOADABLE_FILES)):
        return True
    return any(
        (path / name).exists()
        for name in (
            "01_design/assembly_plan.json",
            "02_part_request/part_create_request.json",
            "03_review/part_request_review.json",
            "04_handoff/reviewed_part_handoff.json",
            "05_single_create/lineage.json",
            "06_part_result_review/part_result_review.json",
        )
    )


def _first_existing_artifact_path(root: Path, artifact: str) -> Path:
    direct = root / artifact
    if direct.exists():
        return direct
    for relative in STAGED_READABLE_ARTIFACTS.get(artifact, ()):
        candidate = root / relative
        if candidate.exists():
            return candidate
    return direct


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_first_json(root: Path, relative_paths: tuple[str, ...]) -> dict[str, Any] | None:
    for relative_path in relative_paths:
        value = _read_json_if_present(root / relative_path)
        if value is not None:
            return value
    return None


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
        compact = {}
        for key, value in item.items():
            if key not in {"code", "message", "dimension", "feature", "check"}:
                continue
            safe_value = _safe_summary_text(value)
            if safe_value is not None:
                compact[key] = safe_value
        return compact
    safe_message = _safe_summary_text(item)
    return {"message": safe_message} if safe_message is not None else {}


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


def _compact_revision_summary(
    comparison: dict[str, Any] | None,
    lineage: dict[str, Any] | None,
    revision_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison = comparison or {}
    lineage = lineage or {}
    revision_plan = revision_plan or {}
    summary = comparison.get("summary") if isinstance(comparison.get("summary"), dict) else {}
    status_value = comparison.get("status")
    child_status = status_value.get("child") if isinstance(status_value, dict) else status_value
    return {
        "present": bool(comparison or lineage or revision_plan),
        "relationship": lineage.get("relationship"),
        "parent_run_id": lineage.get("parent_run_id") or comparison.get("parent_run_id"),
        "child_run_id": lineage.get("child_run_id") or comparison.get("child_run_id"),
        "revision_index": lineage.get("revision_index"),
        "plan_status": revision_plan.get("status"),
        "status": child_status,
        "blocked_reason": comparison.get("blocked_reason") or lineage.get("blocked_reason"),
        "requested_change_count": summary.get("requested_change_count", 0),
        "actual_ir_change_count": summary.get("actual_ir_change_count", 0),
        "validation_change_count": summary.get("validation_change_count", 0),
        "system_repair_change_count": summary.get("system_repair_change_count", 0),
    }


def _compact_negotiation_summary(
    requirement: dict[str, Any] | None,
    planning: dict[str, Any] | None,
    report: dict[str, Any] | None,
    trace: dict[str, Any] | None,
) -> dict[str, Any]:
    requirement = requirement or {}
    planning = planning or {}
    report = report or {}
    trace = trace or {}
    gate = planning.get("flow_gate_status") if isinstance(planning.get("flow_gate_status"), dict) else {}
    requirement_status = (
        requirement.get("requirement_status") if isinstance(requirement.get("requirement_status"), dict) else {}
    )
    flow_decision = (
        report.get("flow_decision")
        or trace.get("final_flow_decision")
        or requirement_status.get("flow_decision")
        or gate.get("rework_decision")
        or {}
    )
    missing = _first_list(
        requirement.get("missing_information"),
        requirement.get("missing_fields"),
        requirement_status.get("missing_information"),
        gate.get("missing_information"),
        report.get("missing_information"),
    )
    clarification = _first_list(
        requirement.get("clarification_questions"),
        requirement.get("follow_up_questions"),
        requirement_status.get("clarification_questions"),
        report.get("clarification_questions"),
    )
    assumptions = _first_list(
        requirement.get("assumptions"),
        requirement_status.get("assumptions"),
        planning.get("assumptions"),
        gate.get("assumptions"),
        flow_decision.get("assumptions") if isinstance(flow_decision, dict) else None,
        report.get("assumptions"),
    )
    return {
        "assumptions": _compact_text_items(assumptions),
        "missing_information": _compact_text_items(missing),
        "clarification_questions": _compact_text_items(clarification),
        "blocked_reason": _safe_summary_text(
            report.get("blocked_reason")
            or requirement_status.get("blocked_reason")
            or gate.get("blocked_reason")
            or trace.get("blocked_reason")
        ),
        "user_review_status": _safe_summary_text(
            report.get("user_review_status")
            or requirement_status.get("user_review_status")
            or gate.get("user_review_status")
        ),
    }


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _compact_text_items(items: list[Any]) -> list[Any]:
    compact = []
    for item in items[:20]:
        if isinstance(item, dict):
            compact_item = {
                key: safe
                for key, value in item.items()
                for safe in [_safe_summary_text(value)]
                if key in {"code", "field", "question", "message", "text", "assumption"} and safe is not None
            }
            if compact_item:
                compact.append(compact_item)
            continue
        safe = _safe_summary_text(item)
        if safe is not None:
            compact.append(safe)
    return compact


def _compact_assembly_plan_summary(assembly_plan: dict[str, Any] | None) -> dict[str, Any]:
    assembly_plan = assembly_plan or {}
    parts = [part for part in assembly_plan.get("parts", []) if isinstance(part, dict)]
    interfaces = [item for item in assembly_plan.get("interfaces", []) if isinstance(item, dict)]
    blocked = [item for item in assembly_plan.get("blocked_reasons", []) if isinstance(item, dict)]
    quality = assembly_plan.get("quality") if isinstance(assembly_plan.get("quality"), dict) else {}
    part_status_counts = _safe_count_dict(quality.get("part_status_counts")) or _count_field(parts, "part_status")
    generation_strategy_counts = (
        _safe_count_dict(quality.get("part_generation_strategy_counts"))
        or _count_field(parts, "generation_strategy")
    )
    return {
        "present": bool(assembly_plan),
        "scope": _safe_summary_text(assembly_plan.get("scope")),
        "status": _safe_summary_text(assembly_plan.get("status")),
        "part_count": len(parts),
        "interface_count": len(interfaces),
        "fastener_count": len(assembly_plan.get("fasteners", [])) if isinstance(assembly_plan.get("fasteners"), list) else 0,
        "candidate_part_count": sum(1 for part in parts if part.get("supported_candidate") is True),
        "reference_only_count": sum(1 for part in parts if part.get("part_status") == "reference_only"),
        "blocked_part_count": sum(1 for part in parts if part.get("part_status") == "blocked"),
        "part_status_counts": part_status_counts,
        "generation_strategy_counts": generation_strategy_counts,
        "diagnostic_codes": _compact_code_list(assembly_plan.get("diagnostic_codes")),
        "blocked_reason_codes": _compact_code_list([item.get("code") for item in blocked]),
        "parts": [_compact_assembly_part(part, interfaces) for part in parts[:20]],
    }


def _compact_assembly_part(part: dict[str, Any], interfaces: list[dict[str, Any]]) -> dict[str, Any]:
    part_id = _safe_summary_text(part.get("part_id"))
    blocked = [item for item in part.get("blocked_reasons", []) if isinstance(item, dict)]
    return {
        "part_id": part_id,
        "role": _safe_summary_text(part.get("role")),
        "generation_strategy": _safe_summary_text(part.get("generation_strategy")),
        "part_status": _safe_summary_text(part.get("part_status")),
        "supported_candidate": part.get("supported_candidate") is True,
        "reference_only": part.get("part_status") == "reference_only",
        "blocked_reason_codes": _compact_code_list([item.get("code") for item in blocked]),
        "interfaces_count": sum(
            1
            for interface in interfaces
            if part_id is not None and (interface.get("from") == part_id or interface.get("to") == part_id)
        ),
    }


def _compact_part_request_summary(part_request: dict[str, Any] | None) -> dict[str, Any]:
    part_request = part_request or {}
    return {
        "present": bool(part_request),
        "part_id": _safe_summary_text(part_request.get("part_id")),
        "status": _safe_summary_text(part_request.get("status")),
        "generation_strategy": _safe_summary_text(part_request.get("generation_strategy")),
        "interface_constraint_count": (
            len(part_request.get("interface_constraints", []))
            if isinstance(part_request.get("interface_constraints"), list)
            else 0
        ),
        "diagnostic_codes": _compact_code_list(part_request.get("diagnostic_codes")),
    }


def _compact_part_request_review_summary(part_review: dict[str, Any] | None) -> dict[str, Any]:
    part_review = part_review or {}
    checks = part_review.get("checks") if isinstance(part_review.get("checks"), dict) else {}
    return {
        "present": bool(part_review),
        "status": _safe_summary_text(part_review.get("status")),
        "diagnostic_codes": _compact_code_list(part_review.get("diagnostic_codes")),
        "checks": {
            key: checks.get(key)
            for key in (
                "is_reference_only",
                "is_blocked",
                "has_interface_constraints",
                "has_provider_generated_code",
                "has_provider_generated_cad_ir",
                "has_arbitrary_provider_fields",
            )
            if isinstance(checks.get(key), bool)
        },
    }


def _compact_reviewed_part_handoff_summary(handoff: dict[str, Any] | None) -> dict[str, Any]:
    handoff = handoff or {}
    return {
        "present": bool(handoff),
        "part_id": _safe_summary_text(handoff.get("part_id")),
        "status": _safe_summary_text(handoff.get("status")),
        "source_part_request": _safe_summary_text(handoff.get("source_part_request")),
        "source_review": _safe_summary_text(handoff.get("source_review")),
        "interface_constraint_count": (
            len(handoff.get("interface_constraints", []))
            if isinstance(handoff.get("interface_constraints"), list)
            else 0
        ),
        "diagnostic_codes": _compact_code_list(handoff.get("diagnostic_codes")),
    }


def _compact_part_result_review_summary(review: dict[str, Any] | None) -> dict[str, Any]:
    review = review or {}
    checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
    return {
        "present": bool(review),
        "status": _safe_summary_text(review.get("status")),
        "part_id": _safe_summary_text(review.get("part_id")),
        "child_run": _safe_summary_text(review.get("child_run")),
        "diagnostic_codes": _compact_code_list(review.get("diagnostic_codes")),
        "checks": {
            key: checks.get(key)
            for key in (
                "child_run_created",
                "step_created",
                "stl_created",
                "input_ir_created",
                "report_created",
                "single_part_only",
                "no_batch_generation",
                "no_assembly_generation",
                "selected_part_id_preserved",
                "lineage_preserved",
                "interface_constraints_preserved_in_metadata",
            )
            if isinstance(checks.get(key), bool)
        },
        "child_scope": _safe_summary_text(checks.get("child_scope")),
        "revision_note_codes": _compact_code_list(
            [
                item.get("code")
                for item in review.get("revision_notes", [])
                if isinstance(item, dict)
            ]
        ),
    }


def _compact_reviewed_part_lineage_summary(lineage: dict[str, Any] | None) -> dict[str, Any]:
    lineage = lineage or {}
    return {
        "present": bool(lineage),
        "relationship": _safe_summary_text(lineage.get("relationship")),
        "part_id": _safe_summary_text(lineage.get("part_id")),
        "child_run_id": _safe_summary_text(lineage.get("child_run_id")),
        "assembly_plan_artifact": _safe_summary_text(lineage.get("assembly_plan_artifact")),
        "part_create_request_artifact": _safe_summary_text(lineage.get("part_create_request_artifact")),
        "part_request_review_artifact": _safe_summary_text(lineage.get("part_request_review_artifact")),
        "reviewed_part_handoff_artifact": _safe_summary_text(lineage.get("reviewed_part_handoff_artifact")),
    }


def _compact_stage_review_summary(review: dict[str, Any] | None) -> dict[str, Any]:
    review = review or {}
    changes = review.get("requested_changes") if isinstance(review.get("requested_changes"), list) else []
    return {
        "present": bool(review),
        "schema_version": review.get("schema_version") if isinstance(review.get("schema_version"), int) else None,
        "stage": _safe_summary_text(review.get("stage")),
        "review_status": _safe_summary_text(review.get("review_status")),
        "target_rework_stage": _safe_summary_text(review.get("target_rework_stage")),
        "requested_changes_count": len(changes),
        "user_notes_preview": _safe_summary_text(review.get("user_notes")),
        "diagnostic_codes": _compact_code_list(review.get("diagnostic_codes")),
    }


def _compact_code_list(items: Any) -> list[str]:
    values = items if isinstance(items, list) else []
    codes = []
    for item in values:
        text = _safe_summary_text(item)
        if text is not None and text not in codes:
            codes.append(text)
        if len(codes) == 20:
            break
    return codes


def _safe_count_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, item in value.items():
        safe_key = _safe_summary_text(key)
        if safe_key is not None and isinstance(item, int) and item >= 0:
            counts[safe_key] = item
    return counts


def _count_field(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = _safe_summary_text(item.get(field))
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


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


def _compact_gate_decision(decision: Any) -> dict[str, Any] | None:
    if not isinstance(decision, dict):
        return None
    item = {
        key: value
        for key, value in decision.items()
        if key in {"stage", "action", "reason", "timestamp"}
    }
    payload_summary = _compact_payload_summary(decision.get("payload"))
    if payload_summary["items"]:
        item["payload_summary"] = payload_summary
    return item


def _compact_adapter_activity(activity: Any) -> dict[str, Any] | None:
    if not isinstance(activity, dict):
        return None
    provider_identity = activity.get("provider_identity")
    compact = {
        "operation": _safe_summary_text(activity.get("operation")) or "unknown",
        "provider_identity": _compact_adapter_identity(provider_identity if isinstance(provider_identity, dict) else {}),
    }
    trace = _compact_provider_request_trace(activity.get("request_trace_summary"))
    if trace is not None:
        compact["request_trace_summary"] = trace
    return compact


def _compact_provider_request_trace(trace: Any) -> dict[str, Any] | None:
    if not isinstance(trace, dict):
        return None
    provider_identity = trace.get("provider_identity")
    context_shape = trace.get("context_shape")
    payload_shape = trace.get("payload_shape")
    compact = {
        "operation": _safe_summary_text(trace.get("operation")) or "unknown",
        "stage": _safe_summary_text(trace.get("stage")) or "unknown",
        "provider_identity": _compact_adapter_identity(provider_identity if isinstance(provider_identity, dict) else {}),
        "message_count": trace.get("message_count") if isinstance(trace.get("message_count"), int) else 0,
        "context_shape": _compact_trace_context_shape(context_shape if isinstance(context_shape, dict) else {}),
        "knowledge_ids": _compact_text_list(trace.get("knowledge_ids")).get("items", []),
        "payload_shape": _compact_trace_payload_shape(payload_shape if isinstance(payload_shape, dict) else {}),
    }
    return compact


def _compact_trace_context_shape(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_global_rules": bool(shape.get("has_global_rules")),
        "has_stage_skill": bool(shape.get("has_stage_skill")),
        "has_contract_guide": bool(shape.get("has_contract_guide")),
        "selected_knowledge_count": (
            shape["selected_knowledge_count"] if isinstance(shape.get("selected_knowledge_count"), int) else 0
        ),
    }


def _compact_trace_payload_shape(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": _safe_summary_text(shape.get("kind")) or "unknown",
        "top_level_keys": _compact_text_list(shape.get("top_level_keys")).get("items", []),
    }


def _compact_adapter_identity(identity: dict[str, Any]) -> dict[str, Any]:
    compact_identity = {}
    for key, value in identity.items():
        safe_key = _safe_summary_text(key)
        safe_value = _safe_adapter_identity_value(value)
        if safe_key is not None and safe_value is not None:
            compact_identity[safe_key] = safe_value
    return compact_identity


def _compact_payload_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"count": 0, "items": []}
    items = []
    for key in sorted(payload):
        safe_key = _safe_summary_text(key)
        safe_value = _safe_payload_value(payload[key])
        if safe_key is None or safe_value is None:
            continue
        items.append({"key": safe_key, "value": safe_value})
        if len(items) == 5:
            break
    return {"count": len(payload), "items": items}


def _safe_payload_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _safe_summary_text(value)
    if isinstance(value, list):
        safe = [_safe_payload_value(item) for item in value[:3]]
        safe = [item for item in safe if item is not None]
        return ", ".join(str(item) for item in safe) if safe else None
    return None


def _safe_adapter_identity_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (int, float, bool)):
        return value
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer ")):
        return None
    if ":\\" in value or "\\\\" in value:
        return None
    return value[:160]


def _validate_provider_config_inputs(
    provider: str,
    model: str | None,
    timeout_seconds: int | None,
    max_retries: int | None,
) -> None:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("workflow console provider must be a non-empty string")
    if _contains_secret_marker(provider):
        raise ValueError("workflow console provider config must not include secrets")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("workflow console provider model must be a non-empty string when set")
        if _contains_secret_marker(model):
            raise ValueError("workflow console provider config must not include secrets")
    if timeout_seconds is not None and (not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300):
        raise ValueError("workflow console provider timeout_seconds must be between 1 and 300")
    if max_retries is not None and (not isinstance(max_retries, int) or not 0 <= max_retries <= 5):
        raise ValueError("workflow console provider max_retries must be between 0 and 5")


def _contains_secret_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer "))


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
