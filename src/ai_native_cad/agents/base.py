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

    def interpret_user_intent(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the interpreted design intent behind a user prompt."""

    def propose_design_brief(self, intent: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a design brief with assumptions, constraints, and goals."""

    def generate_candidate_plans(
        self,
        design_brief: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return candidate CAD design plans for the brief."""

    def convert_plan_to_ir(self, selected_plan: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return CAD IR for the selected plan."""

    def create_part_ir(
        self,
        reviewed_part_handoff: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return CAD IR for one reviewed part handoff."""

    def parse_revision_request(
        self,
        prompt: str,
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return structured change intent for a revision prompt."""

    def create_revision_plan(
        self,
        change_intent: dict[str, Any],
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a structured plan for revising an existing CadFlow run."""

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
