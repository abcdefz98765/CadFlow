"""Deterministic Work view-model inference for the local workflow console."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_native_cad.workflow_console.artifact_display import filter_artifacts_for_display
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, STAGED_ARTIFACT_DIRS

DEBUG_WORK_ID = "__debug_runs__"
DEBUG_WORK_TITLE = "Unclassified / Debug Runs"


def list_works(
    backend: Any,
    *,
    limit: int = 50,
    offset: int = 0,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return paginated inferred Works without provider or CAD execution."""
    index = build_work_index(backend)
    show_debug = bool((filters or {}).get("show_debug"))
    works = [
        work["summary"]
        for work in index["works"]
        if show_debug or work["summary"].get("overall_status") != "debug_only"
    ]
    works = sorted(works, key=lambda item: (item.get("updated_at") or "", item.get("work_id") or ""), reverse=True)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    page = works[offset : offset + limit]
    return {
        "works": page,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned": len(page),
            "total": len(works),
            "has_previous": offset > 0,
            "has_next": offset + len(page) < len(works),
        },
        "filters": {"show_debug": show_debug},
    }


def get_work_summary(backend: Any, work_id: str) -> dict[str, Any]:
    """Return one inferred Work summary."""
    return _find_work(build_work_index(backend), work_id)["summary"]


def get_work_detail(backend: Any, work_id: str) -> dict[str, Any]:
    """Return detail for one inferred Work with current state separated from history."""
    work = _find_work(build_work_index(backend), work_id)
    summary = work["summary"]
    current_run_id = summary.get("latest_run_id") or summary.get("root_run_id")
    current_run = work["runs_by_id"].get(current_run_id) or {}
    parts = _build_parts(work)
    nodes = _build_nodes(work, parts)
    run_history = _build_run_history(work, current_run_id)
    products = _build_products(work)
    return {
        "work_id": summary["work_id"],
        "summary": summary,
        "current_state": {
            "current_run_id": current_run_id,
            "root_run_id": summary.get("root_run_id"),
            "part_counts": summary.get("part_counts") or {},
            "review_status": summary.get("review_status"),
            "report_status": summary.get("report_status"),
            "next_action": summary.get("next_action"),
            "immutability_note": "Current state points to latest relevant run artifacts; run history remains append-only.",
        },
        "parts": parts,
        "nodes": nodes,
        "run_history": run_history,
        "products": products,
        "available_actions": _available_actions(current_run),
        "history_semantics": {
            "runs_are_immutable": True,
            "rework_creates_new_runs": True,
            "old_runs_remain_visible": True,
        },
    }


def build_work_index(backend: Any) -> dict[str, Any]:
    """Infer Works from existing runs and lineage artifacts under configured roots."""
    runs = _load_all_runs(backend)
    root_ids = [run_id for run_id, run in runs.items() if _is_root_candidate(run)]
    member_to_root: dict[str, str] = {}
    for root_id in root_ids:
        for child_id in _referenced_child_run_ids(runs[root_id]):
            if child_id in runs:
                member_to_root[child_id] = root_id
        for run_id, run in runs.items():
            if run_id == root_id:
                continue
            if _lineage_child_id(run) == root_id:
                member_to_root[run_id] = root_id

    works = []
    assigned = set()
    for root_id in sorted(root_ids):
        if root_id in member_to_root:
            continue
        member_ids = sorted({root_id, *[run_id for run_id, owner in member_to_root.items() if owner == root_id]})
        assigned.update(member_ids)
        works.append(_build_work(root_id, member_ids, runs, debug_only=False))

    debug_ids = sorted(run_id for run_id in runs if run_id not in assigned)
    if debug_ids:
        works.append(_build_work(DEBUG_WORK_ID, debug_ids, runs, debug_only=True))
    return {"works": works}


def _load_all_runs(backend: Any) -> dict[str, dict[str, Any]]:
    paths: dict[str, Path] = {}
    seen: set[Path] = set()
    for root in backend._resolved_run_roots():
        if not root.exists():
            continue
        directories = [root, *sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda path: str(path))]
        for path in directories:
            if path.name in STAGED_ARTIFACT_DIRS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if not _has_artifact(path):
                continue
            seen.add(resolved)
            paths[path.name] = path

    runs: dict[str, dict[str, Any]] = {}
    root_names = {name for name, path in paths.items() if _path_is_root_candidate(path)}
    for name in sorted(root_names):
        runs[name] = _read_metadata(backend, paths[name])

    referenced = set()
    for run in runs.values():
        referenced.update(_referenced_child_run_ids(run))
    for name in sorted(referenced):
        if name in paths and name not in runs:
            runs[name] = _read_metadata(backend, paths[name])

    for name, path in paths.items():
        if name not in runs:
            runs[name] = backend.read_run_summary(path)
    return runs


def _read_metadata(backend: Any, path: Path) -> dict[str, Any]:
    metadata = backend.read_run_metadata(path)
    metadata["run_id"] = path.name
    return metadata


def _has_artifact(path: Path) -> bool:
    from ai_native_cad.workflow_console.backend import _has_workflow_artifact

    return _has_workflow_artifact(path)


def _path_is_root_candidate(path: Path) -> bool:
    return any(
        (path / name).exists()
        for name in (
            "assembly_plan.json",
            "01_design/assembly_plan.json",
            "workflow_review.json",
            "stage_review.json",
        )
    )


def _is_root_candidate(run: dict[str, Any]) -> bool:
    artifacts = _artifact_names(run)
    reviewed = _dict(run.get("reviewed_part_summary"))
    assembly = _dict(reviewed.get("assembly_plan"))
    return any(name in artifacts for name in ("assembly_plan.json", "workflow_review.json", "stage_review.json")) or bool(
        assembly.get("present")
    )


def _build_work(root_id: str, member_ids: list[str], runs: dict[str, dict[str, Any]], *, debug_only: bool) -> dict[str, Any]:
    runs_by_id = {run_id: runs[run_id] for run_id in member_ids if run_id in runs}
    latest_run_id = _latest_work_state_run_id(root_id, runs_by_id) or (member_ids[0] if member_ids else root_id)
    root_run = runs_by_id.get(root_id) or runs_by_id.get(latest_run_id) or {}
    parts = _build_parts({"summary": {"root_run_id": root_id}, "runs_by_id": runs_by_id})
    part_counts = _part_counts(parts)
    summary = {
        "work_id": root_id,
        "title": DEBUG_WORK_TITLE if debug_only else _work_title(root_run, root_id),
        "overall_status": "debug_only" if debug_only else _overall_status(part_counts, root_run),
        "root_run_id": None if debug_only else root_id,
        "latest_run_id": latest_run_id,
        "part_counts": part_counts,
        "review_status": _review_status(root_run, parts),
        "report_status": _report_status(root_run),
        "readiness_score": _readiness_score(root_run, part_counts),
        "risk_level": _risk_level(root_run, part_counts),
        "next_action": _next_action(part_counts, root_run),
        "updated_at": max((run.get("updated_at") or "" for run in runs_by_id.values()), default=None),
        "diagnostic_codes": _diagnostic_codes(root_run, parts),
    }
    return {"summary": summary, "runs_by_id": runs_by_id}


def _build_parts(work: dict[str, Any]) -> list[dict[str, Any]]:
    root_run = work["runs_by_id"].get(work["summary"].get("root_run_id")) or _latest_run(work["runs_by_id"]) or {}
    assembly_parts = _assembly_parts(root_run)
    rows = []
    for part in assembly_parts:
        part_id = part.get("part_id")
        status = _part_status(part, work["runs_by_id"])
        review = _part_review_for(part_id, work["runs_by_id"])
        latest_run_id = _latest_part_run_id(part_id, work["runs_by_id"]) or work["summary"].get("root_run_id")
        rows.append({
            "part_id": part_id,
            "role": part.get("role"),
            "status": status,
            "current_stage": _part_stage(status, review),
            "latest_run_id": latest_run_id,
            "attempt_count": _part_attempt_count(part_id, work["runs_by_id"]),
            "has_step": _part_has_download(part_id, work["runs_by_id"], "model.step"),
            "has_stl": _part_has_download(part_id, work["runs_by_id"], "model.stl"),
            "review_status": _dict(review).get("status") or part.get("part_status"),
            "next_action": _part_next_action(status),
        })
    if rows:
        return rows
    for run_id, run in sorted(work["runs_by_id"].items()):
        selected = run.get("selected_part_id")
        if selected:
            rows.append({
                "part_id": selected,
                "role": None,
                "status": "accepted" if run.get("has_step") or _has_download(run, "model.step") else "incomplete",
                "current_stage": "single_part_generation",
                "latest_run_id": run_id,
                "attempt_count": 1,
                "has_step": bool(run.get("has_step")) or _has_download(run, "model.step"),
                "has_stl": bool(run.get("has_stl")) or _has_download(run, "model.stl"),
                "review_status": _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review")).get("status"),
                "next_action": "View products",
            })
    return rows


def _build_nodes(work: dict[str, Any], parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root_id = work["summary"].get("root_run_id")
    root = work["runs_by_id"].get(root_id) or _latest_run(work["runs_by_id"]) or {}
    artifacts = _artifact_names(root)
    nodes = [
        {
            "id": "requirement",
            "label": "Requirement",
            "kind": "stage",
            "status": "completed" if "requirement.json" in artifacts or "prompt.txt" in artifacts else "not_started",
            "summary": "Requirement artifacts are present." if "requirement.json" in artifacts else "Prompt captured.",
            "artifacts": [name for name in ("prompt.txt", "requirement.json") if name in artifacts],
            "actions": ["stage_review"],
        },
        {
            "id": "assembly_plan",
            "label": "Assembly Plan",
            "kind": "stage",
            "status": "completed" if _assembly_parts(root) else "not_started",
            "summary": f"{len(_assembly_parts(root))} parts detected.",
            "artifacts": ["assembly_plan.json"] if "assembly_plan.json" in artifacts else [],
            "actions": ["stage_review"] if "assembly_plan.json" in artifacts else [],
        },
    ]
    for part in parts:
        nodes.append({
            "id": f"part:{part.get('part_id')}",
            "label": part.get("part_id") or "part",
            "kind": "part",
            "status": part.get("status") or "incomplete",
            "summary": _part_node_summary(part),
            "artifacts": _part_artifacts(part),
            "actions": _part_actions(part),
        })
    for name, label in (("workflow_review.json", "Workflow Review"), ("stage_review.json", "Stage Review"), ("rework_decision.json", "Rework Decision")):
        if name in artifacts:
            nodes.append({
                "id": name.removesuffix(".json"),
                "label": label,
                "kind": "stage",
                "status": "completed",
                "summary": f"{label} artifact is present.",
                "artifacts": [name],
                "actions": ["run_rework"] if name == "stage_review.json" else [],
            })
    return nodes


def _build_run_history(work: dict[str, Any], current_run_id: str | None) -> list[dict[str, Any]]:
    rows = []
    for run_id, run in sorted(work["runs_by_id"].items(), key=lambda item: (item[1].get("updated_at") or "", item[0]), reverse=True):
        status = _dict(run.get("status"))
        rows.append({
            "run_id": run_id,
            "kind": _run_kind(run),
            "status": status.get("status"),
            "summary": _run_summary_line(run),
            "created_at": run.get("updated_at"),
            "is_current": run_id == current_run_id,
            "immutable": True,
        })
    return rows


def _build_products(work: dict[str, Any]) -> dict[str, Any]:
    artifact_by_name = {}
    download_by_name = {}
    for run in work["runs_by_id"].values():
        for item in run.get("artifacts", []):
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                artifact_by_name[item["name"]] = {"name": item["name"], "collapsed": True, "read_on_demand": True}
        for item in run.get("downloadables", []):
            if isinstance(item, dict) and item.get("name") in DOWNLOADABLE_FILES:
                download_by_name[item["name"]] = {"name": item["name"], "available": True}
    return {
        "human_facing": filter_artifacts_for_display(list(artifact_by_name.values())),
        "downloadables": list(download_by_name.values()),
        "artifacts_secondary_by_default": True,
    }


def _available_actions(run: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = _artifact_names(run)
    stage_review = _dict(run.get("stage_review_summary"))
    return [
        {"action": "save_stage_review", "available": True, "reason": None},
        {"action": "create_workflow_review", "available": True, "reason": None},
        {
            "action": "run_rework",
            "available": stage_review.get("review_status") == "needs_revision",
            "reason": None if stage_review.get("review_status") == "needs_revision" else "Save a needs_revision stage review first.",
        },
        {
            "action": "reviewed_part_staged_actions",
            "available": "assembly_plan.json" in artifacts,
            "reason": None if "assembly_plan.json" in artifacts else "Assembly plan is required.",
        },
    ]


def _overall_status(counts: dict[str, int], run: dict[str, Any]) -> str:
    meaningful = counts["accepted"] + counts["blocked"] + counts["needs_review"] + counts["incomplete"]
    if counts["blocked"]:
        return "partial_success" if counts["accepted"] else "blocked"
    if counts["needs_review"]:
        return "needs_review"
    if meaningful and counts["accepted"] == meaningful:
        return "accepted"
    if meaningful:
        return "incomplete"
    status = _dict(run.get("status")).get("status")
    return "accepted" if status in {"success", "completed"} else "incomplete"


def _part_counts(parts: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(parts), "accepted": 0, "blocked": 0, "needs_review": 0, "reference_only": 0, "incomplete": 0}
    for part in parts:
        status = part.get("status")
        if status in counts:
            counts[status] += 1
        elif status == "skipped":
            counts["reference_only"] += 1
        else:
            counts["incomplete"] += 1
    return counts


def _part_status(part: dict[str, Any], runs: dict[str, dict[str, Any]]) -> str:
    if part.get("reference_only") or part.get("part_status") == "reference_only":
        return "reference_only"
    review = _part_review_for(part.get("part_id"), runs)
    review_status = _dict(review).get("status")
    if review_status in {"accepted_for_preview", "accepted", "success"} and _part_has_download(part.get("part_id"), runs, "model.step"):
        return "accepted"
    if review_status and ("blocked" in str(review_status) or "failed" in str(review_status)):
        return "blocked"
    if part.get("part_status") == "blocked":
        return "blocked"
    if part.get("supported_candidate") is True:
        return "incomplete"
    return "blocked" if part.get("supported_candidate") is False else "incomplete"


def _part_review_for(part_id: Any, runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for run in runs.values():
        review = _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review"))
        if part_id is None or review.get("part_id") in {part_id, None}:
            if review.get("present"):
                return review
    return {}


def _part_has_download(part_id: Any, runs: dict[str, dict[str, Any]], name: str) -> bool:
    for run in runs.values():
        review = _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review"))
        selected = run.get("selected_part_id") or review.get("part_id")
        if part_id is not None and selected not in {part_id, None}:
            continue
        if _has_download(run, name):
            return True
        for child in run.get("child_runs", []):
            if isinstance(child, dict) and name in (child.get("downloadables") or []):
                return True
    return False


def _has_download(run: dict[str, Any], name: str) -> bool:
    return any(isinstance(item, dict) and item.get("name") == name for item in run.get("downloadables", []))


def _assembly_parts(run: dict[str, Any]) -> list[dict[str, Any]]:
    reviewed = _dict(run.get("reviewed_part_summary"))
    assembly = _dict(reviewed.get("assembly_plan"))
    return [part for part in assembly.get("parts", []) if isinstance(part, dict)]


def _referenced_child_run_ids(run: dict[str, Any]) -> set[str]:
    ids = {child.get("run_id") for child in run.get("child_runs", []) if isinstance(child, dict)}
    lineage = _dict(_dict(run.get("reviewed_part_summary")).get("lineage"))
    ids.add(lineage.get("child_run_id"))
    rework = _dict(run.get("rework_decision_summary"))
    ids.add(rework.get("child_run_id"))
    return {item for item in ids if isinstance(item, str) and item}


def _lineage_child_id(run: dict[str, Any]) -> str | None:
    lineage = _dict(_dict(run.get("reviewed_part_summary")).get("lineage"))
    value = lineage.get("child_run_id")
    return value if isinstance(value, str) else None


def _latest_run_id(runs: dict[str, dict[str, Any]]) -> str | None:
    if not runs:
        return None
    return max(runs.items(), key=lambda item: (item[1].get("updated_at") or "", item[0]))[0]


def _latest_work_state_run_id(root_id: str, runs: dict[str, dict[str, Any]]) -> str | None:
    candidates = {root_id}
    root = runs.get(root_id) or {}
    candidates.update(_referenced_rework_run_ids(root))
    present = {run_id: runs[run_id] for run_id in candidates if run_id in runs}
    return _latest_run_id(present) or (root_id if root_id in runs else _latest_run_id(runs))


def _referenced_rework_run_ids(run: dict[str, Any]) -> set[str]:
    rework = _dict(run.get("rework_decision_summary"))
    value = rework.get("child_run_id")
    return {value} if isinstance(value, str) and value else set()


def _latest_run(runs: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    run_id = _latest_run_id(runs)
    return runs.get(run_id) if run_id is not None else None


def _latest_part_run_id(part_id: Any, runs: dict[str, dict[str, Any]]) -> str | None:
    candidates = []
    for run_id, run in runs.items():
        selected = run.get("selected_part_id") or _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review")).get("part_id")
        if part_id is None or selected == part_id:
            candidates.append((run.get("updated_at") or "", run_id))
    return max(candidates)[1] if candidates else None


def _part_attempt_count(part_id: Any, runs: dict[str, dict[str, Any]]) -> int:
    return sum(1 for run in runs.values() if run.get("selected_part_id") == part_id or _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review")).get("part_id") == part_id)


def _review_status(run: dict[str, Any], parts: list[dict[str, Any]]) -> str:
    stage = _dict(run.get("stage_review_summary"))
    if stage.get("review_status"):
        return stage["review_status"]
    if any(part.get("status") == "blocked" for part in parts):
        return "needs_revision"
    return "accepted" if parts and all(part.get("status") in {"accepted", "reference_only"} for part in parts) else "needs_review"


def _report_status(run: dict[str, Any]) -> str:
    review = _dict(run.get("workflow_review_summary"))
    return review.get("risk_level") and f"{review.get('risk_level')}_risk" or (_dict(run.get("status")).get("status") or "unknown")


def _readiness_score(run: dict[str, Any], counts: dict[str, int]) -> int:
    review = _dict(run.get("workflow_review_summary"))
    if isinstance(review.get("readiness_score"), int):
        return review["readiness_score"]
    meaningful = counts["accepted"] + counts["blocked"] + counts["needs_review"] + counts["incomplete"]
    return int(100 * counts["accepted"] / meaningful) if meaningful else 0


def _risk_level(run: dict[str, Any], counts: dict[str, int]) -> str:
    review = _dict(run.get("workflow_review_summary"))
    if review.get("risk_level"):
        return review["risk_level"]
    if counts["blocked"]:
        return "medium" if counts["accepted"] else "high"
    return "low" if counts["accepted"] else "unknown"


def _next_action(counts: dict[str, int], run: dict[str, Any]) -> str:
    if counts["blocked"]:
        return "Review blocked part or run rework"
    if counts["needs_review"]:
        return "Review generated part results"
    if counts["incomplete"]:
        return "Continue reviewed-part staged workflow"
    if counts["accepted"]:
        return "View products"
    return "Inspect run history"


def _diagnostic_codes(run: dict[str, Any], parts: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    reviewed = _dict(run.get("reviewed_part_summary"))
    for section in ("assembly_plan", "part_result_review"):
        for code in _dict(reviewed.get(section)).get("diagnostic_codes", []) or []:
            if isinstance(code, str) and code not in codes:
                codes.append(code)
    for part in parts:
        status = part.get("review_status")
        if isinstance(status, str) and "blocked" in status and status not in codes:
            codes.append(status)
    return codes[:20]


def _work_title(run: dict[str, Any], fallback: str) -> str:
    requirement = _dict(_dict(run.get("report_summary")).get("requirement_summary"))
    for key in ("product_family", "part_family", "part_type", "scope"):
        value = requirement.get(key)
        if isinstance(value, str) and value:
            return value.replace("_", " ").title()
    return fallback.replace("_", " ").title()


def _run_kind(run: dict[str, Any]) -> str:
    artifacts = _artifact_names(run)
    if "assembly_plan.json" in artifacts:
        return "root_planning"
    if "part_result_review.json" in artifacts:
        return "part_attempt"
    if "rework_decision.json" in artifacts:
        return "rework"
    return "debug"


def _run_summary_line(run: dict[str, Any]) -> str:
    selected = run.get("selected_part_id")
    status = _dict(run.get("status")).get("status") or "unknown"
    return f"{selected}: {status}" if selected else status


def _part_stage(status: str, review: dict[str, Any]) -> str:
    if status == "reference_only":
        return "skipped"
    if _dict(review).get("present"):
        return "part_result_review"
    return "single_part_generation"


def _part_next_action(status: str) -> str:
    return {
        "accepted": "View products",
        "blocked": "Add stage review or run rework",
        "reference_only": "None",
        "needs_review": "Review part result",
    }.get(status, "Continue staged workflow")


def _part_node_summary(part: dict[str, Any]) -> str:
    if part.get("status") == "accepted":
        return "STEP/STL generated and accepted for preview."
    if part.get("status") == "blocked":
        return f"Blocked: {part.get('review_status') or 'part generation unavailable'}."
    if part.get("status") == "reference_only":
        return "Reference-only part skipped for generation."
    return "Part is not complete."


def _part_artifacts(part: dict[str, Any]) -> list[str]:
    artifacts = []
    if part.get("has_step"):
        artifacts.append("model.step")
    if part.get("has_stl"):
        artifacts.append("model.stl")
    if part.get("review_status"):
        artifacts.append("part_result_review.json")
    return artifacts


def _part_actions(part: dict[str, Any]) -> list[str]:
    if part.get("status") == "accepted":
        return ["view_artifacts"]
    if part.get("status") == "blocked":
        return ["stage_review", "run_rework"]
    return ["stage_review"]


def _artifact_names(run: dict[str, Any]) -> set[str]:
    return {item.get("name") for item in run.get("artifacts", []) if isinstance(item, dict) and isinstance(item.get("name"), str)}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_work(index: dict[str, Any], work_id: str) -> dict[str, Any]:
    for work in index["works"]:
        if work["summary"].get("work_id") == work_id:
            return work
    raise FileNotFoundError(f"workflow console work not found: {work_id}")
