"""Canonical CadFlow domain records and compatibility projections."""

from ai_native_cad.domain.records import (
    ARTIFACT_REFERENCE_SCHEMA_VERSION,
    DOMAIN_RECORD_SCHEMA_VERSION,
    WORK_SCHEMA_VERSION,
    accept_part_result,
    advance_active_lineage,
    append_part_attempt,
    begin_work_intent,
    create_artifact_reference,
    create_assembly_job_record,
    create_deliverable_package_record,
    create_work_record,
    project_product_state,
    project_work_record,
    record_candidate_selection,
    register_artifact_references,
    validate_work_record,
)

__all__ = [
    "ARTIFACT_REFERENCE_SCHEMA_VERSION",
    "DOMAIN_RECORD_SCHEMA_VERSION",
    "WORK_SCHEMA_VERSION",
    "accept_part_result",
    "advance_active_lineage",
    "append_part_attempt",
    "begin_work_intent",
    "create_artifact_reference",
    "create_assembly_job_record",
    "create_deliverable_package_record",
    "create_work_record",
    "project_product_state",
    "project_work_record",
    "record_candidate_selection",
    "register_artifact_references",
    "validate_work_record",
]
