"""Typed ports owned by the product Work orchestrator."""

from __future__ import annotations

from typing import Any, Protocol


class WorkStorePort(Protocol):
    """Mutable Work storage; historical Run contents are outside this port."""

    def create_work(
        self,
        *,
        title: str,
        description: str | None,
        work_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    def read_work(self, work_id: str) -> dict[str, Any]: ...

    def write_work(self, work_id: str, work: dict[str, Any]) -> None: ...

    def work_detail(self, work_id: str) -> dict[str, Any]: ...

    def next_run_id(self, work_id: str, base: str) -> str: ...

    def invalidate_projection(self) -> None: ...


class DeterministicCompatibilityPort(Protocol):
    """The one M1 port for deterministic legacy Run behavior."""

    def workspace_config(self) -> dict[str, Any]: ...

    def create_run(
        self,
        *,
        work_id: str,
        run_id: str,
        prompt: str,
    ) -> dict[str, Any]: ...

    def run_stage(
        self,
        *,
        work_id: str,
        run_id: str,
        stage: str,
    ) -> dict[str, Any]: ...

    def planned_parts(
        self,
        *,
        work_id: str,
        root_run_id: str,
    ) -> list[dict[str, Any]]: ...

    def run_exists(self, *, work_id: str, run_id: str) -> bool: ...
