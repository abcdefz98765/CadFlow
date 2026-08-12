"""CadFlow Agent-first CAD workbench API.

Canonical product entry points are exported first. Historical planning,
template-pipeline, and fixed Workflow symbols remain compatibility exports.
"""

from ai_native_cad.domain.records import (
    create_artifact_reference,
    create_work_record,
    project_product_state,
)
from ai_native_cad.orchestration import WorkOrchestrator

from ai_native_cad.assembly_planner import create_assembly_plan, create_assembly_configs, write_assembly_plan
from ai_native_cad.cad_ir import CADIR, ir_from_file, ir_from_planning_artifact, ir_from_text
from ai_native_cad.pipeline import (
    run_agent_create_pipeline,
    run_agent_revision_pipeline,
    run_ir_pipeline,
    run_provider_create_pipeline,
    run_provider_normalized_design_create_pipeline,
    run_provider_normalized_create_pipeline,
    run_reviewed_part_agent_ir_create_pipeline,
    run_text_pipeline,
)
from ai_native_cad.planning import PlanningHandoffBlocked, create_planning_artifact
from ai_native_cad.requirements import RequirementAgent
from ai_native_cad.workflow import CADWorkflow, run_workflow

__all__ = [
    "WorkOrchestrator",
    "create_artifact_reference",
    "create_work_record",
    "project_product_state",
    # Compatibility exports below remain callable for stored Runs and known
    # integrations; they are not the normal Current Work architecture.
    "CADIR",
    "CADWorkflow",
    "RequirementAgent",
    "create_assembly_configs",
    "create_assembly_plan",
    "create_planning_artifact",
    "ir_from_file",
    "ir_from_planning_artifact",
    "ir_from_text",
    "PlanningHandoffBlocked",
    "run_agent_create_pipeline",
    "run_agent_revision_pipeline",
    "run_ir_pipeline",
    "run_provider_create_pipeline",
    "run_provider_normalized_design_create_pipeline",
    "run_provider_normalized_create_pipeline",
    "run_reviewed_part_agent_ir_create_pipeline",
    "run_text_pipeline",
    "run_workflow",
    "write_assembly_plan",
]
