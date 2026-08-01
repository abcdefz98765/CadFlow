"""Workflow Console adapters for the single M1 Work orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_native_cad.workflow_console.work_index import create_work_manifest

if TYPE_CHECKING:
    from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


class WorkflowConsoleWorkStore:
    """File-backed Work store using safe backend path boundaries."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def create_work(
        self,
        *,
        title: str,
        description: str | None,
        work_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return create_work_manifest(
            self.backend,
            title=title,
            description=description,
            work_id=work_id,
            metadata=metadata,
        )

    def read_work(self, work_id: str) -> dict[str, Any]:
        return self.backend._read_work_manifest(work_id)

    def write_work(self, work_id: str, work: dict[str, Any]) -> None:
        self.backend._write_work_manifest(work_id, work)

    def work_detail(self, work_id: str) -> dict[str, Any]:
        return self.backend.get_work_detail(work_id)

    def next_run_id(self, work_id: str, base: str) -> str:
        return self.backend._next_workspace_run_id(work_id, base)

    def invalidate_projection(self) -> None:
        self.backend.invalidate_work_index()


class WorkflowConsoleDeterministicCompatibility:
    """The sole product adapter to current deterministic Run behavior."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def workspace_config(self) -> dict[str, Any]:
        return self.backend.read_workspace_config()

    def create_run(
        self,
        *,
        work_id: str,
        run_id: str,
        prompt: str,
    ) -> dict[str, Any]:
        return self.backend.create_run_by_id(
            run_id,
            prompt,
            root=self.backend._work_runs_root(work_id),
        )

    def run_stage(
        self,
        *,
        work_id: str,
        run_id: str,
        stage: str,
    ) -> dict[str, Any]:
        return self.backend.run_stage_by_id(
            run_id,
            stage,
            root=self.backend._work_runs_root(work_id),
        )

    def planned_parts(
        self,
        *,
        work_id: str,
        root_run_id: str,
    ) -> list[dict[str, Any]]:
        root_run = self.backend.read_run_metadata_by_id(
            root_run_id,
            root=self.backend._work_runs_root(work_id),
        )
        return self.backend._planned_parts_from_run(root_run)

    def run_exists(self, *, work_id: str, run_id: str) -> bool:
        try:
            self.backend.resolve_run(
                run_id,
                root=self.backend._work_runs_root(work_id),
            )
        except FileNotFoundError:
            return False
        return True
