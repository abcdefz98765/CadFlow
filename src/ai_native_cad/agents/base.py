"""Agent adapter interface.

Adapters convert user language and workflow context into structured contracts.
Execution remains owned by the deterministic CadFlow pipeline.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentAdapter(Protocol):
    """Boundary between agent reasoning and deterministic CAD execution."""

    @property
    def provider_identity(self) -> dict[str, Any]:
        """Return a path/token-free identity for runtime traces."""

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a structured requirement contract."""

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a structured planning artifact."""

    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return constrained repair advice for a failed CAD IR attempt."""

    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a structured review explanation."""
