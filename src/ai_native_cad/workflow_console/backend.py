"""Dependency-free local backend facade for workflow-console operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.pipeline.runner import PROJECT_ROOT
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS, SUPPORTED_STAGES, StageRunner, _safe_run_name

DOWNLOADABLE_FILES = ("model.step", "model.stl", "preview.png", "model.py")


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
            "artifacts": self.list_artifacts(path),
            "downloadables": self.list_downloadables(path),
        }

    def list_artifacts(self, run_dir: str | Path) -> list[dict[str, Any]]:
        """List known readable artifacts present in a run directory."""
        path = self._require_project_path(Path(run_dir))
        artifacts = []
        for name in sorted(READABLE_ARTIFACTS):
            artifact_path = path / name
            if artifact_path.exists():
                artifacts.append(_file_metadata(name, artifact_path))
        return artifacts

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
        report = _read_json_if_present(path / "report.json")
        trace = _read_json_if_present(path / "agent_trace.json")
        runtime = _read_json_if_present(path / "logs" / "runtime.json")
        runtime_stage = ((runtime or {}).get("workflow_console") or {}).get("latest_stage") or {}
        flow_decision = (report or {}).get("flow_decision") or (trace or {}).get("final_flow_decision")
        rework_decision = (report or {}).get("rework_decision") or (trace or {}).get("rework_decision")
        status = (report or {}).get("status")
        if status is None and report:
            status = "success" if report.get("success") else "failed"
        if status is None and trace:
            status = "blocked" if rework_decision and rework_decision.get("action") == "return" else "running_or_incomplete"
        if status is None and runtime_stage:
            status = runtime_stage.get("status")
        return {
            "status": status or "unknown",
            "success": (report or {}).get("success"),
            "stage": runtime_stage.get("stage"),
            "blocked_stage": (report or {}).get("blocked_stage") or (trace or {}).get("text_pipeline", {}).get("blocked_stage"),
            "attempts": (trace or {}).get("total_attempts"),
            "final_selected_candidate": (trace or {}).get("final_selected_candidate"),
            "flow_decision": flow_decision,
            "rework_decision": rework_decision,
            "runtime": runtime_stage or None,
        }

    def _resolved_run_roots(self) -> list[Path]:
        roots = []
        for root in self.run_roots:
            path = root if root.is_absolute() else self.project_root / root
            roots.append(self._require_project_path(path))
        return roots

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
