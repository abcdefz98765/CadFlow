"""Deterministic local stage execution for workflow-console backends."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_native_cad.cad_ir.parser import ir_from_planning_artifact
from ai_native_cad.pipeline.runner import PROJECT_ROOT, run_ir_pipeline, run_text_pipeline
from ai_native_cad.planning import create_planning_artifact
from ai_native_cad.requirements import RequirementAgent

READABLE_ARTIFACTS = {
    "prompt.txt",
    "requirement.json",
    "planning_artifact.json",
    "input_ir.json",
    "report.json",
    "report.md",
    "agent_trace.json",
    "logs/runtime.json",
}

SUPPORTED_STAGES = {"text_pipeline", "requirement", "planning", "part_modeling"}

STATUS_BLOCKED = "blocked"
STATUS_COMPLETED = "completed"
STATUS_CREATED = "created"
STATUS_FAILED = "failed"
STATUS_RUNNING_OR_INCOMPLETE = "running_or_incomplete"
STATUS_SUCCESS = "success"
STATUS_UNKNOWN = "unknown"

WORKFLOW_STATUS_VALUES = {
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_CREATED,
    STATUS_FAILED,
    STATUS_RUNNING_OR_INCOMPLETE,
    STATUS_SUCCESS,
    STATUS_UNKNOWN,
}


class StageRunner:
    """Local execution unit behind the future Web Workflow Console.

    The runner owns deterministic stage execution and artifact persistence. It
    does not own natural-language model behavior; future LLM work belongs
    behind the AgentAdapter boundary.
    """

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.requirement_agent = RequirementAgent()

    def create_run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a local run directory with prompt.txt but do not execute stages."""
        context = dict(context or {})
        context.setdefault("run_name", f"workflow_run_{uuid4().hex}")
        output_dir = self._resolve_output_dir(context)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
        result = {
            "status": STATUS_CREATED,
            "stage": STATUS_CREATED,
            "output_dir": str(output_dir),
        }
        self._write_stage_runtime(output_dir, stage=STATUS_CREATED, status=STATUS_CREATED, result=result)
        return result

    def run_text_pipeline(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the complete deterministic prompt workflow and write artifacts."""
        context = context or {}
        result = run_text_pipeline(
            prompt,
            output_root=context.get("output_root"),
            output_dir=context.get("output_dir"),
            overrides=context.get("overrides"),
        )
        self._write_stage_runtime(
            Path(result["output_dir"]),
            stage="text_pipeline",
            status=result.get("status", STATUS_UNKNOWN),
            result=result,
        )
        return result

    def run_stage(
        self,
        stage: str,
        run_dir: str | Path,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one deterministic stage using artifacts in a run directory."""
        if stage not in SUPPORTED_STAGES:
            raise ValueError(f"unsupported workflow console stage: {stage}")
        context = dict(context or {})
        context["output_dir"] = run_dir
        output_dir = self._require_project_path(Path(run_dir))

        if stage in {"text_pipeline", "requirement"}:
            stage_prompt = prompt if prompt is not None else _read_prompt(output_dir)
            if stage == "text_pipeline":
                return self.run_text_pipeline(stage_prompt, context=context)
            return self.run_requirement(stage_prompt, context=context)

        if stage == "planning":
            requirement = context.get("requirement") or _read_json_required(output_dir / "requirement.json")
            return self.run_planning(requirement, context=context)

        input_ir = context.get("input_ir")
        if input_ir is not None:
            return self.run_part_modeling(input_ir, context=context)
        input_ir = _read_json_if_present(output_dir / "input_ir.json")
        if input_ir is not None:
            return self.run_part_modeling(input_ir, context=context)
        planning_artifact = context.get("planning_artifact") or _read_json_required(output_dir / "planning_artifact.json")
        return self.run_planning_to_part_modeling(planning_artifact, context=context)

    def run_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run Requirement and persist prompt.txt plus requirement.json."""
        context = context or {}
        output_dir = self._resolve_output_dir(context)
        output_dir.mkdir(parents=True, exist_ok=True)
        requirement = self.requirement_agent.parse(prompt, overrides=context.get("overrides"))
        decision = requirement.get("requirement_status", {}).get("flow_decision", {})
        stage_status = _stage_status_from_decision(decision)
        (output_dir / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
        _write_json(output_dir / "requirement.json", requirement)
        result = {
            "status": decision.get("action", "proceed"),
            "stage_status": stage_status,
            "stage": "requirement",
            "output_dir": str(output_dir),
            "requirement": requirement,
            "flow_decision": decision,
        }
        self._write_stage_runtime(output_dir, stage="requirement", status=stage_status, result=result)
        return result

    def run_planning(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run Planning from a requirement artifact and persist planning_artifact.json."""
        context = context or {}
        output_dir = self._resolve_output_dir(context, requirement)
        output_dir.mkdir(parents=True, exist_ok=True)
        planning_artifact = create_planning_artifact(requirement)
        _write_json(output_dir / "planning_artifact.json", planning_artifact)
        decision = planning_artifact.get("flow_gate_status", {}).get("rework_decision", {})
        stage_status = _stage_status_from_decision(decision)
        result = {
            "status": decision.get("action", "proceed"),
            "stage_status": stage_status,
            "stage": "planning",
            "output_dir": str(output_dir),
            "planning_artifact": planning_artifact,
            "flow_decision": decision,
        }
        self._write_stage_runtime(output_dir, stage="planning", status=stage_status, result=result)
        return result

    def run_part_modeling(self, input_ir: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run deterministic Part Modeling from CAD IR and write output artifacts."""
        context = context or {}
        previous_console = None
        if context.get("output_dir"):
            runtime = _read_json_if_present(Path(context["output_dir"]) / "logs" / "runtime.json")
            previous_console = (runtime or {}).get("workflow_console")
        result = run_ir_pipeline(
            input_ir,
            output_root=context.get("output_root"),
            output_dir=context.get("output_dir"),
        )
        self._write_stage_runtime(
            Path(result["output_dir"]),
            stage="part_modeling",
            status=result.get("status", STATUS_UNKNOWN),
            result=result,
            previous_console=previous_console,
        )
        return result

    def run_planning_to_part_modeling(
        self,
        planning_artifact: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create CAD IR from Planning and run Part Modeling."""
        ir = ir_from_planning_artifact(planning_artifact)
        return self.run_part_modeling(ir.to_dict(), context=context)

    def read_artifacts(self, run_dir: str | Path) -> dict[str, Any]:
        """Read known workflow artifacts from an existing run directory."""
        path = self._require_project_path(Path(run_dir))
        artifacts: dict[str, Any] = {}
        for artifact in sorted(READABLE_ARTIFACTS):
            artifact_path = path / artifact
            if not artifact_path.exists():
                continue
            artifacts[artifact] = _read_artifact(artifact_path)
        return artifacts

    def _resolve_output_dir(
        self,
        context: dict[str, Any],
        requirement: dict[str, Any] | None = None,
    ) -> Path:
        if context.get("output_dir"):
            return self._require_project_path(Path(context["output_dir"]))
        run_name = context.get("run_name")
        if run_name is None and requirement is not None:
            run_name = requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type")
        run_name = run_name or "workflow_run"
        root = Path(context.get("output_root") or self.project_root / "outputs")
        if not root.is_absolute():
            root = self.project_root / root
        return self._require_project_path(root / _safe_run_name(str(run_name)))

    def _require_project_path(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"workflow console paths must stay inside project root: {self.project_root}") from exc
        return resolved

    def _write_stage_runtime(
        self,
        output_dir: Path,
        stage: str,
        status: str,
        result: dict[str, Any],
        previous_console: dict[str, Any] | None = None,
    ) -> None:
        runtime_path = output_dir / "logs" / "runtime.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = _read_json_if_present(runtime_path) or {}
        if previous_console is not None and "workflow_console" not in runtime:
            runtime["workflow_console"] = previous_console
        console = runtime.setdefault("workflow_console", {})
        stages = console.setdefault("stages", [])
        entry = {
            "stage": stage,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(output_dir),
            "flow_decision": result.get("flow_decision"),
            "rework_decision": result.get("rework_decision"),
        }
        stages.append({key: value for key, value in entry.items() if value is not None})
        console["latest_stage"] = stages[-1]
        console["stage_count"] = len(stages)
        runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_run_name(value: str) -> str:
    allowed = [char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip()]
    name = "".join(allowed).strip("._")
    return name or "workflow_run"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_artifact(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return text


def _read_prompt(output_dir: Path) -> str:
    prompt_path = output_dir / "prompt.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(str(prompt_path))
    return prompt_path.read_text(encoding="utf-8").strip()


def _read_json_required(path: Path) -> dict[str, Any]:
    value = _read_json_if_present(path)
    if value is None:
        raise FileNotFoundError(str(path))
    return value


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_status_from_decision(decision: dict[str, Any]) -> str:
    return STATUS_COMPLETED if decision.get("action", "proceed") == "proceed" else STATUS_BLOCKED
