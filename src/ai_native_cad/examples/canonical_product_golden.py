"""Reproducible current-product Golden for the Agent-first Workbench.

The scripted provider is deliberately part of the example contract.  It proves
the CadFlow product journey and local trust boundaries, not external-provider
design quality.  Candidate source still passes through the registered
model-program skill, attested Tool Broker execution, STEP inspection, and the
reviewable publication gate.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ai_native_cad.domain.records import (
    create_artifact_reference,
    register_artifact_references,
)


PRODUCT_GOLDEN_ID = "canonical_servo_mounting_bracket"
PRODUCT_GOLDEN_WORK_ID = "product_golden_servo_bracket"
PRODUCT_GOLDEN_PART_JOB_ID = "servo_mounting_bracket"
PRODUCT_GOLDEN_RUN_ID = "servo_mounting_bracket_attempt_1"
PRODUCT_GOLDEN_REQUEST_ID = "product_golden_design_1"
PRODUCT_GOLDEN_PROMPT = (
    "Create a compact single-piece mounting bracket for a micro servo. "
    "It should mount to a flat panel with four screws, support the servo "
    "between two upright ears, and leave cable clearance. Choose sensible "
    "prototype dimensions. This is an exploration model, not a "
    "strength-validated release part."
)

PRODUCT_GOLDEN_SOURCE = """import cadquery as cq

def build_model(parameters):
    base_length = float(parameters["base_length"])
    base_width = float(parameters["base_width"])
    base_thickness = float(parameters["base_thickness"])
    ear_spacing = float(parameters["ear_spacing"])
    ear_thickness = float(parameters["ear_thickness"])
    ear_width = float(parameters["ear_width"])
    ear_height = float(parameters["ear_height"])
    mount_hole = float(parameters["mount_hole_diameter"])
    servo_hole = float(parameters["servo_hole_diameter"])

    base = cq.Workplane("XY").box(base_length, base_width, base_thickness)
    ear_z = base_thickness / 2.0 + ear_height / 2.0
    ear_x = ear_spacing / 2.0 + ear_thickness / 2.0
    left_ear = cq.Workplane("XY").box(ear_thickness, ear_width, ear_height).translate(
        (-ear_x, 0.0, ear_z)
    )
    right_ear = cq.Workplane("XY").box(ear_thickness, ear_width, ear_height).translate(
        (ear_x, 0.0, ear_z)
    )
    body = base.union(left_ear).union(right_ear)
    body = body.faces("<Z").workplane().pushPoints(
        [(-23.0, -15.0), (-23.0, 15.0), (23.0, -15.0), (23.0, 15.0)]
    ).hole(mount_hole)
    cable_window = cq.Workplane("XY").box(18.0, 10.0, base_thickness + 2.0).translate(
        (0.0, 10.0, 0.0)
    )
    axle_length = ear_spacing + 2.0 * ear_thickness + 4.0
    axle_cut = cq.Workplane("YZ").circle(servo_hole / 2.0).extrude(axle_length).translate(
        (-axle_length / 2.0, 0.0, base_thickness + ear_height * 0.72)
    )
    return body.cut(cable_window).cut(axle_cut)
"""

PRODUCT_GOLDEN_PARAMETERS = {
    "base_length": 58.0,
    "base_width": 42.0,
    "base_thickness": 4.0,
    "ear_spacing": 24.0,
    "ear_thickness": 4.0,
    "ear_width": 20.0,
    "ear_height": 30.0,
    "mount_hole_diameter": 4.2,
    "servo_hole_diameter": 5.0,
}


class CanonicalProductGoldenProvider:
    """Fixed action provider used only to reproduce the current product story."""

    provider_identity = {
        "provider": "scripted_product_golden",
        "model": "canonical_servo_bracket_v1",
    }

    def __init__(self) -> None:
        self.calls = 0
        self._actions = iter(
            [
                {
                    "action": "request_context",
                    "context_key": "part_job",
                },
                {
                    "action": "create_model_program",
                    "model_program": {
                        "api_id": "cadquery_v1",
                        "source": PRODUCT_GOLDEN_SOURCE,
                        "parameters": deepcopy(PRODUCT_GOLDEN_PARAMETERS),
                        "requested_outputs": ["step"],
                    },
                    "assumptions": [
                        "Dimensions are in millimetres.",
                        "The bracket is an exploration prototype in a generic rigid material.",
                    ],
                },
                {"action": "request_execution"},
                {"action": "inspect_observation"},
                {"action": "stop", "stop_reason": "completed"},
            ]
        )

    def choose_design_action(self, *, state: Any, skill_manifest: Any) -> dict[str, Any]:
        self.calls += 1
        return next(self._actions)


def open_canonical_product_golden(
    backend: Any,
    *,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Create or reopen the current Product Golden in the active Workspace."""

    existing = _existing_product_golden(backend)
    if existing is not None:
        _progress(progress_callback, "ready", "completed", "Product example is ready to review")
        return {**existing, "created": False}

    if not backend.read_workspace().get("present"):
        backend.create_workspace(name="CadFlow Workspace")
    _progress(progress_callback, "intent", "running", "Recording the original request")

    work_id = _next_work_id(backend)
    backend.create_work(
        "Compact Micro Servo Mounting Bracket",
        PRODUCT_GOLDEN_PROMPT,
        work_id=work_id,
        metadata={
            "work_classification": "product_example",
            "example_id": PRODUCT_GOLDEN_ID,
            "example_classification": "product_golden",
            "example_reproducibility": "scripted_provider",
            "external_provider_quality_claim": False,
            "teaching_intent": {
                "demonstrates": "How to inspect and act on a completed validated result",
                "will_see": "Known geometry, measured evidence, Reviewable state, Accept, and Revise",
                "can_try": "Inspect the model, accept it, or create a traced revision",
                "understand_after": "Reviewable and accepted are distinct and history remains immutable",
                "requirements": "No external provider credential required",
            },
        },
    )
    attempt = backend.create_work_part_attempt(
        work_id,
        PRODUCT_GOLDEN_PART_JOB_ID,
        prompt=PRODUCT_GOLDEN_PROMPT,
        role="single-piece servo interface bracket",
        run_id=PRODUCT_GOLDEN_RUN_ID if work_id == PRODUCT_GOLDEN_WORK_ID else None,
    )
    attempt_run_id = str(attempt["run"]["run_id"])
    _progress(progress_callback, "design", "running", "Creating a scripted design candidate")

    previous_adapter = backend.stage_runner.agent_adapter
    provider = CanonicalProductGoldenProvider()
    backend.stage_runner.agent_adapter = provider
    try:
        episode = backend.run_work_part_design_episode(
            work_id,
            PRODUCT_GOLDEN_PART_JOB_ID,
            request_id=PRODUCT_GOLDEN_REQUEST_ID,
            objective=PRODUCT_GOLDEN_PROMPT,
        )
    finally:
        backend.stage_runner.agent_adapter = previous_adapter

    reviewable = episode.get("reviewable_result")
    if not isinstance(reviewable, dict):
        stop_reason = (episode.get("episode") or {}).get("stop_reason")
        raise RuntimeError(
            "Product example did not produce a reviewable result"
            + (f": {stop_reason}" if stop_reason else "")
        )
    _progress(progress_callback, "build_evaluate", "completed", "Geometry and STEP inspection passed")

    run_id = attempt_run_id
    design_brief_id = _persist_design_brief(
        backend,
        work_id=work_id,
        run_id=run_id,
        episode=episode,
    )
    backend.invalidate_work_index()
    _progress(progress_callback, "ready", "completed", "Reviewable result is ready; it remains unaccepted")
    return {
        "work_id": work_id,
        "run_id": run_id,
        "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
        "reviewable_result_id": reviewable["reviewable_result_id"],
        "design_brief_id": design_brief_id,
        "created": True,
        "provider": "scripted_product_golden",
        "capability_mode": reviewable.get("capability_mode"),
        "accepted": False,
        "external_provider_quality_proof": False,
        "progress": [
            {"phase": "intent", "status": "completed"},
            {"phase": "design", "status": "completed"},
            {"phase": "build_evaluate", "status": "completed"},
            {"phase": "accept_deliver", "status": "reviewable"},
        ],
    }


def _persist_design_brief(
    backend: Any,
    *,
    work_id: str,
    run_id: str,
    episode: dict[str, Any],
) -> str:
    artifact_id = f"product_golden_design_brief_{run_id}"
    run_dir = backend._require_child_path(backend._work_runs_root(work_id), run_id)
    path = backend._require_child_path(run_dir, "design_brief.json")
    brief = {
        "artifact_type": "design_brief",
        "schema_version": 1,
        "work_id": work_id,
        "run_id": run_id,
        "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
        "phase": "design",
        "checkpoint": "design_brief",
        "trust_role": "candidate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content": {
            "concept": "Single-piece U-bracket with a panel-mounting base and two servo support ears.",
            "geometry_strategy": "Union a drilled base plate and two upright ears, then cut a cable window and aligned servo-axis bore.",
            "important_parameters": [
                {"name": "base", "value": "58 × 42 × 4", "unit": "mm"},
                {"name": "ear spacing", "value": 24.0, "unit": "mm"},
                {"name": "ear height", "value": 30.0, "unit": "mm"},
                {"name": "panel holes", "value": "4 × Ø4.2", "unit": "mm"},
                {"name": "servo-axis bore", "value": "Ø5.0", "unit": "mm"},
            ],
            "functional_features": [
                "Four panel-mounting holes",
                "Two upright servo support ears",
                "Aligned servo-axis bore",
                "Base cable-clearance window",
            ],
            "interfaces": [
                "Flat panel through four clearance holes",
                "Generic micro-servo envelope between 24 mm-spaced ears",
            ],
            "user_constraints": [
                "Single-piece compact bracket",
                "Four-screw flat-panel mounting",
                "Two support ears",
                "Cable clearance",
                "Exploration model only",
            ],
            "assumptions": [
                "Generic rigid prototype material",
                "Nominal micro-servo envelope; no manufacturer model supplied",
            ],
            "tradeoffs": [
                "A single solid is easy to inspect and prototype, but the ear spacing is not fit-validated against a named servo.",
            ],
            "changes_after_repair": [],
            "repair_count": 0,
            "source_capability_mode": "scripted provider + attested cadquery_v1 model program",
            "external_provider_quality_proof": False,
            "translations": {
                "zh": {
                    "concept": "由一块面板安装底板和两侧舵机支撑耳组成的一体式 U 形支架。",
                    "geometry_strategy": "将带孔底板与两个竖直支撑耳合并，再切出走线窗口和同轴舵机孔。",
                    "important_parameters": [
                        {"name": "底板", "value": "58 × 42 × 4", "unit": "mm"},
                        {"name": "支撑耳间距", "value": 24.0, "unit": "mm"},
                        {"name": "支撑耳高度", "value": 30.0, "unit": "mm"},
                        {"name": "面板安装孔", "value": "4 × Ø4.2", "unit": "mm"},
                        {"name": "舵机轴孔", "value": "Ø5.0", "unit": "mm"},
                    ],
                    "functional_features": [
                        "四个面板安装孔",
                        "两个竖直舵机支撑耳",
                        "同轴舵机孔",
                        "底板走线窗口",
                    ],
                    "interfaces": [
                        "通过四个间隙孔连接平面面板",
                        "通用微型舵机安装在间距 24 mm 的支撑耳之间",
                    ],
                    "user_constraints": [
                        "紧凑的一体式支架",
                        "四螺钉平面安装",
                        "两个支撑耳",
                        "保留走线空间",
                        "仅用于探索模型",
                    ],
                    "assumptions": [
                        "使用通用刚性原型材料",
                        "采用标称微型舵机包络；未提供制造商模型",
                    ],
                    "tradeoffs": [
                        "单一实体便于检查和快速制作，但支撑耳间距尚未与指定舵机进行装配验证。",
                    ],
                    "source_capability_mode": "脚本化 provider + 经证明的 cadquery_v1 模型程序",
                }
            },
        },
    }
    path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sources = [
        item.get("artifact_id")
        for item in episode.get("artifact_references", [])
        if isinstance(item, dict) and item.get("trust_role") == "candidate"
    ]
    reference = create_artifact_reference(
        artifact_id=artifact_id,
        work_id=work_id,
        run_id=run_id,
        part_job_id=PRODUCT_GOLDEN_PART_JOB_ID,
        relative_path="design_brief.json",
        phase="design",
        checkpoint="design_brief",
        trust_role="candidate",
        source_artifact_ids=[value for value in sources if isinstance(value, str)][:4],
        validation_status="not_validated",
    )
    manifest = register_artifact_references(
        backend._read_work_manifest(work_id),
        [reference],
    )
    backend._write_work_manifest(work_id, manifest)
    return artifact_id


def _existing_product_golden(backend: Any) -> dict[str, Any] | None:
    for work in backend.list_works(limit=500).get("works", []):
        if not isinstance(work, dict):
            continue
        work_id = work.get("work_id")
        if not isinstance(work_id, str):
            continue
        manifest = backend._read_work_manifest(work_id)
        metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
        if metadata.get("example_id") != PRODUCT_GOLDEN_ID:
            continue
        reviewable = next(
            (
                item
                for item in manifest.get("artifact_references", [])
                if isinstance(item, dict)
                and item.get("checkpoint") == "reviewable_result"
                and item.get("trust_role") == "reviewable_result"
                and str(item.get("relative_path") or "").endswith("/reviewable_result.json")
            ),
            None,
        )
        if reviewable:
            return {
                "work_id": work_id,
                "run_id": reviewable.get("run_id"),
                "part_job_id": reviewable.get("part_job_id"),
                "reviewable_result_id": reviewable.get("artifact_id"),
                "accepted": bool(manifest.get("accepted_part_results", {}).get(PRODUCT_GOLDEN_PART_JOB_ID)),
                "provider": "scripted_product_golden",
                "external_provider_quality_proof": False,
                "progress": [],
            }
    return None


def _next_work_id(backend: Any) -> str:
    existing = {
        item.get("work_id")
        for item in backend.list_works(limit=500).get("works", [])
        if isinstance(item, dict)
    }
    if PRODUCT_GOLDEN_WORK_ID not in existing:
        return PRODUCT_GOLDEN_WORK_ID
    for index in range(2, 10_000):
        candidate = f"{PRODUCT_GOLDEN_WORK_ID}_{index}"
        if candidate not in existing:
            return candidate
    raise FileExistsError("Product Golden Work id space is exhausted")


def _progress(callback: Any | None, phase: str, status: str, message: str) -> None:
    if callback is not None:
        callback({"phase": phase, "status": status, "message": message})


__all__ = [
    "CanonicalProductGoldenProvider",
    "PRODUCT_GOLDEN_ID",
    "PRODUCT_GOLDEN_PARAMETERS",
    "PRODUCT_GOLDEN_PART_JOB_ID",
    "PRODUCT_GOLDEN_PROMPT",
    "PRODUCT_GOLDEN_SOURCE",
    "PRODUCT_GOLDEN_WORK_ID",
    "open_canonical_product_golden",
]
