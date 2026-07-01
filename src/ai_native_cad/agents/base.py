"""Agent adapter interface.

Adapters convert user language and workflow context into structured contracts.
Execution remains owned by the deterministic CadFlow pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentAdapter(ABC):
    """Boundary between agent reasoning and deterministic CAD execution."""

    @abstractmethod
    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a structured requirement contract."""

    @abstractmethod
    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a structured planning artifact."""

    @abstractmethod
    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return constrained repair advice for a failed CAD IR attempt."""

    @abstractmethod
    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a structured review explanation."""
