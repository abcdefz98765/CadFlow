"""Deterministic Work view-model inference for the local workflow console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.workflow_console.artifact_display import filter_artifacts_for_display
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, STAGED_ARTIFACT_DIRS

DEBUG_WORK_ID = "__debug_runs__"
DEBUG_WORK_TITLE = "Unclassified / Debug Runs"
WORKSPACE_WORKS_DIR_NAME = "works"
LEGACY_WORKS_DIR_NAME = "_works"
WORKS_DIR_NAME = LEGACY_WORKS_DIR_NAME
WORK_MANIFEST_NAME = "work_manifest.json"
WORK_MANIFEST_SCHEMA_VERSION = 1


def list_works(
    backend: Any,
    *,
    limit: int = 50,
    offset: int = 0,
    filters: dict[str, Any] | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return paginated inferred Works without provider or CAD execution."""
    index = index or build_work_index(backend)
    works = [work["summary"] for work in index["works"]]
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
        "filters": {},
    }


def get_work_summary(backend: Any, work_id: str) -> dict[str, Any]:
    """Return one inferred Work summary."""
    return _find_work(build_work_index(backend), work_id)["summary"]


def get_work_summary_from_index(index: dict[str, Any], work_id: str) -> dict[str, Any]:
    """Return one Work summary from a prebuilt index."""
    return _find_work(index, work_id)["summary"]


def get_work_detail(backend: Any, work_id: str, *, index: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return detail for one inferred Work with current state separated from history."""
    work = _find_work(index or build_work_index(backend), work_id)
    summary = work["summary"]
    active_lineage = summary.get("active_lineage") if isinstance(summary.get("active_lineage"), dict) else {}
    current_run_id = active_lineage.get("active_root_run_id") or summary.get("root_run_id")
    current_run = work["runs_by_id"].get(current_run_id) or {}
    parts = _build_parts(work)
    nodes = _build_nodes(work, parts)
    run_history = _build_run_history(work, active_lineage)
    products = _build_products(work)
    return {
        "work_id": summary["work_id"],
        "summary": summary,
        "entity_state": work.get("entity_state") or _empty_entity_state(summary["work_id"]),
        "current_state": {
            "current_run_id": current_run_id,
            "root_run_id": summary.get("root_run_id"),
            "active_lineage": active_lineage,
            "part_counts": summary.get("part_counts") or {},
            "review_status": summary.get("review_status"),
            "report_status": summary.get("report_status"),
            "next_action": summary.get("next_action"),
            "immutability_note": "Current state points to the explicit active lineage; run history remains append-only.",
        },
        "parts": parts,
        "nodes": nodes,
        "run_history": run_history,
        "products": products,
        "directory_map": _build_directory_map(summary, current_run, parts, products, run_history),
        "available_actions": _available_actions(current_run),
        "history_semantics": {
            "runs_are_immutable": True,
            "rework_creates_new_runs": True,
            "old_runs_remain_visible": True,
        },
    }


def build_work_index(backend: Any, *, include_debug: bool = False) -> dict[str, Any]:
    """Load only manifest-backed Works and their Work-contained runs."""
    manifests = _load_work_manifests(backend)
    works = []
    for work_id, manifest in sorted(manifests.items()):
        runs = _load_work_runs(backend, work_id)
        member_ids = [run_id for run_id in _manifest_run_ids(manifest) if run_id in runs]
        for run_id in runs:
            if run_id not in member_ids:
                member_ids.append(run_id)
        works.append(_build_work(work_id, member_ids, runs, debug_only=False, manifest=manifest))
    return {"works": works}


def create_work_manifest(
    backend: Any,
    *,
    title: str,
    description: str | None = None,
    work_id: str | None = None,
    status: str = "incomplete",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a file-backed Work entity without creating runs or executing CAD."""
    title = _validate_manifest_text(title, "title", limit=120, required=True)
    description = _validate_manifest_text(description or "", "description", limit=1000, required=False)
    if work_id is None:
        from ai_native_cad.workflow_console.stage_runner import _safe_run_name

        work_id = _safe_run_name(title) or "work"
    backend._require_safe_run_id(work_id)
    if work_id in {DEBUG_WORK_ID, WORKSPACE_WORKS_DIR_NAME, LEGACY_WORKS_DIR_NAME}:
        raise ValueError(f"workflow console work id is reserved: {work_id}")
    if status not in {"incomplete", "active", "paused", "archived"}:
        raise ValueError(f"unsupported workflow console work status: {status}")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("workflow console work metadata must be a dictionary")
    safe_metadata = _safe_metadata(metadata or {})
    works_root = _works_root(backend)
    work_dir = backend._require_child_path(works_root, work_id)
    manifest_path = backend._require_child_path(work_dir, WORK_MANIFEST_NAME)
    if manifest_path.exists():
        raise FileExistsError(f"workflow console work already exists: {work_id}")
    work_dir.mkdir(parents=True, exist_ok=False)
    backend._require_child_path(work_dir, "runs").mkdir(parents=True, exist_ok=False)
    now = _now_timestamp()
    manifest = {
        "schema_version": WORK_MANIFEST_SCHEMA_VERSION,
        "work_id": work_id,
        "title": title,
        "description": description,
        "status": status,
        "created_at": now,
        "updated_at": now,
        "current_run_id": None,
        "root_run_id": None,
        "active_lineage": _empty_active_lineage(),
        "run_ids": [],
        "part_jobs": [],
        "accepted_part_results": {},
        "candidate_selection": {},
        "requirement": {"status": "not_started", "root_run_id": None},
        "advancement_mode": backend.read_workspace_config().get("advancement_mode", "manual_confirm"),
        "metadata": safe_metadata,
    }
    manifest_path.write_text(_json_dumps(manifest), encoding="utf-8")
    return {"work": _public_manifest(manifest)}


def _load_work_runs(backend: Any, work_id: str) -> dict[str, dict[str, Any]]:
    root = backend._work_runs_root(work_id)
    if not root.exists():
        return {}
    return {
        path.name: _read_metadata(backend, path)
        for path in sorted(root.iterdir(), key=lambda item: item.name)
        if path.is_dir() and _has_artifact(path)
    }


def _load_debug_runs(backend: Any, excluded_run_ids: set[str]) -> dict[str, dict[str, Any]]:
    paths: dict[str, Path] = {}
    seen: set[Path] = set()
    for root in backend._resolved_run_roots():
        if not root.exists():
            continue
        directories = [root, *sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda path: str(path))]
        for path in directories:
            if path.name in STAGED_ARTIFACT_DIRS or path.name in {WORKSPACE_WORKS_DIR_NAME, LEGACY_WORKS_DIR_NAME}:
                continue
            if _work_storage_dir_in_parts(path.relative_to(root).parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if not _has_artifact(path):
                continue
            seen.add(resolved)
            paths[path.name] = path

    return {
        name: _cheap_debug_run(path)
        for name, path in paths.items()
        if name not in excluded_run_ids
    }


def _cheap_debug_run(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "run_id": path.name,
        "updated_at": _timestamp(stat.st_mtime),
        "status": {"status": "debug_only"},
        "selected_part_id": None,
        "workflow_review_summary": {},
        "rework_decision_summary": {},
        "has_step": (path / "model.step").exists(),
        "has_stl": (path / "model.stl").exists(),
        "child_run_count": 0,
        "downloadables": [],
        "artifacts": [],
    }


def _find_root_candidate_paths(backend: Any) -> set[Path]:
    candidates: set[Path] = set()
    for root in backend._resolved_run_roots():
        if not root.exists():
            continue
        for artifact in (
            "assembly_plan.json",
            "workflow_review.json",
            "stage_review.json",
            "rework_decision.json",
            "part_result_review.json",
        ):
            for path in root.rglob(artifact):
                owner = _artifact_owner_dir(root, path)
                if owner is not None and _has_artifact(owner):
                    candidates.add(owner)
    return candidates


def _artifact_owner_dir(root: Path, artifact_path: Path) -> Path | None:
    try:
        parts = artifact_path.relative_to(root).parts
    except ValueError:
        return None
    if _work_storage_dir_in_parts(parts):
        return None
    parent = artifact_path.parent
    if parent.name in STAGED_ARTIFACT_DIRS:
        parent = parent.parent
    if parent.name in STAGED_ARTIFACT_DIRS or parent == root:
        return None
    return parent


def _find_run_path_by_name(backend: Any, run_id: str) -> Path | None:
    try:
        backend._require_safe_run_id(run_id)
    except ValueError:
        return None
    for root in backend._resolved_run_roots():
        direct = root / run_id
        if direct.is_dir() and _has_artifact(direct):
            return direct
        for path in root.rglob(run_id):
            try:
                parts = path.relative_to(root).parts
            except ValueError:
                continue
            if _work_storage_dir_in_parts(parts):
                continue
            if path.name == run_id and path.is_dir() and _has_artifact(path):
                return path
    return None


def _load_work_manifests(backend: Any) -> dict[str, dict[str, Any]]:
    manifests = {}
    for works_root in _work_manifest_roots(backend):
        if not works_root.exists():
            continue
        for manifest_path in sorted(works_root.glob(f"*/{WORK_MANIFEST_NAME}"), key=lambda path: str(path)):
            manifest = _read_json_if_present(manifest_path)
            public = _public_manifest(manifest)
            if public is not None and public["work_id"] not in manifests:
                manifests[public["work_id"]] = public
    return manifests


def _read_metadata(backend: Any, path: Path) -> dict[str, Any]:
    metadata = backend.read_run_metadata(path)
    metadata["run_id"] = path.name
    return metadata


def _works_root(backend: Any) -> Path:
    return backend._resolve_workspace_path(WORKSPACE_WORKS_DIR_NAME)


def _work_manifest_roots(backend: Any) -> list[Path]:
    return [_works_root(backend)]


def _work_storage_dir_in_parts(parts: tuple[str, ...]) -> bool:
    return WORKSPACE_WORKS_DIR_NAME in parts or LEGACY_WORKS_DIR_NAME in parts


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _public_manifest(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    work_id = value.get("work_id")
    title = value.get("title")
    if not isinstance(work_id, str) or not work_id or not isinstance(title, str) or not title:
        return None
    public = {
        "schema_version": value.get("schema_version") if isinstance(value.get("schema_version"), int) else WORK_MANIFEST_SCHEMA_VERSION,
        "work_id": work_id,
        "title": _validate_manifest_text(title, "title", limit=120, required=True),
        "description": _validate_manifest_text(value.get("description") or "", "description", limit=1000, required=False),
        "status": value.get("status") if value.get("status") in {"incomplete", "active", "paused", "archived"} else "incomplete",
        "created_at": _safe_optional_text(value.get("created_at"), limit=80),
        "updated_at": _safe_optional_text(value.get("updated_at"), limit=80),
        "current_run_id": _safe_optional_text(value.get("current_run_id"), limit=120),
        "root_run_id": _safe_optional_text(value.get("root_run_id"), limit=120),
        "active_lineage": _safe_active_lineage(value.get("active_lineage")),
        "run_ids": [
            item
            for item in value.get("run_ids", [])
            if isinstance(item, str) and item and "/" not in item and "\\" not in item and ":" not in item
        ][:200],
        "part_jobs": _safe_part_jobs(value.get("part_jobs")),
        "accepted_part_results": _safe_accepted_part_results(value.get("accepted_part_results")),
        "candidate_selection": _safe_candidate_selection(value.get("candidate_selection")),
        "requirement": _safe_requirement_state(value.get("requirement")),
        "advancement_mode": value.get("advancement_mode") if value.get("advancement_mode") in {"manual_confirm", "auto_advance"} else "manual_confirm",
        "metadata": _safe_metadata(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
    }
    return public


def _entity_state(work_id: str, manifest: dict[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return _empty_entity_state(work_id)
    return {
        "present": True,
        "schema_version": manifest.get("schema_version"),
        "work_id": manifest.get("work_id"),
        "title": manifest.get("title"),
        "description": manifest.get("description"),
        "status": manifest.get("status"),
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "current_run_id": manifest.get("current_run_id"),
        "root_run_id": manifest.get("root_run_id"),
        "active_lineage": manifest.get("active_lineage") or _empty_active_lineage(),
        "run_ids": manifest.get("run_ids") or [],
        "part_jobs": manifest.get("part_jobs") or [],
        "accepted_part_results": manifest.get("accepted_part_results") or {},
        "candidate_selection": manifest.get("candidate_selection") or {},
        "requirement": manifest.get("requirement") or {},
        "advancement_mode": manifest.get("advancement_mode") or "manual_confirm",
        "metadata": manifest.get("metadata") or {},
    }


def _empty_entity_state(work_id: str) -> dict[str, Any]:
    return {
        "present": False,
        "schema_version": None,
        "work_id": work_id,
        "title": None,
        "description": None,
        "status": None,
        "created_at": None,
        "updated_at": None,
        "current_run_id": None,
        "root_run_id": None,
        "active_lineage": _empty_active_lineage(),
        "run_ids": [],
        "part_jobs": [],
        "requirement": {"status": "not_started", "root_run_id": None},
        "advancement_mode": "manual_confirm",
        "metadata": {},
    }


def _manifest_run_ids(manifest: dict[str, Any]) -> list[str]:
    return [item for item in manifest.get("run_ids", []) if isinstance(item, str) and item]


def _validate_manifest_text(value: Any, label: str, *, limit: int, required: bool) -> str:
    if value is None:
        if required:
            raise ValueError(f"workflow console work {label} is required")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"workflow console work {label} must be a string")
    text = value.strip()
    if required and not text:
        raise ValueError(f"workflow console work {label} is required")
    lowered = text.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer ")):
        raise ValueError("workflow console work manifest must not include secrets")
    if ":\\" in text or "\\\\" in text:
        raise ValueError(f"workflow console work {label} must not include local paths")
    return text[:limit]


def _safe_optional_text(value: Any, *, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer ")):
        return None
    if ":\\" in value or "\\\\" in value:
        return None
    return value[:limit]


def _safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    public = {}
    for key, item in value.items():
        safe_key = _safe_optional_text(key, limit=80)
        if safe_key is None:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe_value = _safe_optional_text(item, limit=240) if isinstance(item, str) else item
            if safe_value is not None:
                public[safe_key] = safe_value
        if len(public) == 20:
            break
    return public


def _safe_requirement_state(value: Any) -> dict[str, Any]:
    state = value if isinstance(value, dict) else {}
    status = state.get("status") if state.get("status") in {"not_started", "draft", "needs_confirmation", "confirmed", "blocked"} else "not_started"
    return {
        "status": status,
        "root_run_id": _safe_run_ref(state.get("root_run_id")),
        "prompt_present": bool(state.get("prompt_present")),
        "confirmation_required": bool(state.get("confirmation_required")),
    }


def _safe_part_jobs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    jobs = []
    for item in value:
        if not isinstance(item, dict):
            continue
        part_id = _safe_optional_text(item.get("part_id"), limit=120)
        if not part_id:
            continue
        run_id = _safe_run_ref(item.get("run_id"))
        jobs.append({
            "part_id": part_id,
            "role": _safe_optional_text(item.get("role"), limit=160),
            "status": _safe_optional_text(item.get("status"), limit=80) or "planned",
            "run_id": run_id,
            "source": _safe_optional_text(item.get("source"), limit=80) or "manifest",
        })
        if len(jobs) == 200:
            break
    return jobs


def _safe_run_ref(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if "/" in value or "\\" in value or ":" in value or value in {".", ".."}:
        return None
    return value[:120]


def _empty_active_lineage() -> dict[str, Any]:
    """Return the persisted Work pointer contract without inferring a Run."""
    return {
        "active_root_run_id": None,
        "active_leaf_run_id": None,
        "accepted_run_ids": [],
        "superseded_run_ids": [],
        "latest_attempt_run_id": None,
    }


def _safe_active_lineage(value: Any) -> dict[str, Any]:
    """Keep the mutable Work lineage pointer path-safe and bounded."""
    raw = value if isinstance(value, dict) else {}
    result = _empty_active_lineage()
    for key in ("active_root_run_id", "active_leaf_run_id", "latest_attempt_run_id"):
        result[key] = _safe_run_ref(raw.get(key))
    for key in ("accepted_run_ids", "superseded_run_ids"):
        values = raw.get(key, []) if isinstance(raw.get(key), list) else []
        result[key] = list(dict.fromkeys(item for item in values if _safe_run_ref(item)))[:200]
    return result


def _safe_accepted_part_results(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for part_id, item in value.items():
        if not isinstance(part_id, str) or not part_id or not isinstance(item, dict):
            continue
        child_run_id = item.get("child_run_id")
        review_id = item.get("review_id")
        status = item.get("status")
        if all(isinstance(field, str) and field for field in (child_run_id, review_id, status)):
            result[part_id] = {"child_run_id": child_run_id, "review_id": review_id, "status": status}
    return result


def _safe_candidate_selection(value: Any) -> dict[str, Any]:
    """Expose a compact Work-level candidate-selection decision, never paths."""
    if not isinstance(value, dict):
        return {}
    selected = value.get("selected_candidate")
    if not isinstance(selected, str) or not selected:
        return {}
    affected = value.get("downstream_stages_affected")
    return {
        "reason": _safe_optional_text(value.get("reason"), limit=240),
        "previous_selected_candidate": _safe_optional_text(value.get("previous_selected_candidate"), limit=120),
        "selected_candidate": selected,
        "created_at": _safe_optional_text(value.get("created_at"), limit=80),
        "downstream_stages_affected": [
            item for item in affected if isinstance(item, str) and item
        ][:20] if isinstance(affected, list) else [],
    }


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _now_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _timestamp(seconds: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


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


def _resolve_active_lineage(
    manifest: dict[str, Any] | None,
    runs: dict[str, dict[str, Any]],
    root_run_id: str | None,
    latest_attempt_run_id: str | None,
) -> dict[str, Any]:
    """Resolve an explicit Work pointer, or a conservative legacy projection.

    A legacy Work must not promote a newer attempt to accepted/current merely
    because it has a later timestamp. Its root remains the only safe active
    evidence until a user-facing action writes an explicit lineage contract.
    """
    stored = (manifest or {}).get("active_lineage")
    has_explicit = isinstance(stored, dict) and any(stored.get(key) for key in ("active_root_run_id", "accepted_run_ids"))
    lineage = _safe_active_lineage(stored)
    if has_explicit:
        accepted = [run_id for run_id in lineage["accepted_run_ids"] if run_id in runs]
        root = lineage["active_root_run_id"] if lineage["active_root_run_id"] in runs else (accepted[0] if accepted else root_run_id)
        leaf = lineage["active_leaf_run_id"] or root
        return {
            **lineage,
            "active_root_run_id": root,
            "active_leaf_run_id": leaf,
            "accepted_run_ids": accepted or ([root] if root else []),
            "superseded_run_ids": [run_id for run_id in lineage["superseded_run_ids"] if run_id in runs],
            "latest_attempt_run_id": lineage["latest_attempt_run_id"] or latest_attempt_run_id,
            "lineage_inferred": False,
        }
    root = root_run_id if root_run_id in runs else None
    return {
        "active_root_run_id": root,
        "active_leaf_run_id": root,
        "accepted_run_ids": [root] if root else [],
        "superseded_run_ids": [],
        "latest_attempt_run_id": latest_attempt_run_id,
        "lineage_inferred": True,
    }


def _build_work(
    root_id: str,
    member_ids: list[str],
    runs: dict[str, dict[str, Any]],
    *,
    debug_only: bool,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runs_by_id = {run_id: runs[run_id] for run_id in member_ids if run_id in runs}
    latest_run_id = (
        manifest.get("current_run_id")
        if manifest and isinstance(manifest.get("current_run_id"), str) and manifest.get("current_run_id") in runs_by_id
        else _latest_work_state_run_id(root_id, runs_by_id)
    ) or (member_ids[0] if member_ids else None)
    root_run_id = (
        manifest.get("root_run_id")
        if manifest and isinstance(manifest.get("root_run_id"), str) and manifest.get("root_run_id") in runs_by_id
        else (None if debug_only else (root_id if root_id in runs_by_id else latest_run_id))
    )
    active_lineage = _resolve_active_lineage(manifest, runs_by_id, root_run_id, latest_run_id)
    active_root_run_id = active_lineage.get("active_root_run_id") or root_run_id
    root_run = runs_by_id.get(active_root_run_id) or runs_by_id.get(root_run_id) or runs_by_id.get(root_id) or {}
    parts = _build_parts({"summary": {"root_run_id": root_run_id or root_id}, "runs_by_id": runs_by_id, "entity_state": _entity_state(root_id, manifest)})
    part_counts = _part_counts(parts)
    title = DEBUG_WORK_TITLE if debug_only else ((manifest or {}).get("title") or _work_title(root_run, root_id))
    status = (manifest or {}).get("status") or "incomplete"
    summary = {
        "work_id": root_id,
        "title": title,
        "overall_status": "debug_only" if debug_only else _overall_status(part_counts, root_run),
        "root_run_id": root_run_id,
        "latest_run_id": latest_run_id,
        "active_lineage": active_lineage,
        "entity_status": status,
        "has_manifest": manifest is not None,
        "part_counts": part_counts,
        "review_status": _review_status(root_run, parts),
        "report_status": _report_status(root_run),
        "readiness_score": _readiness_score(root_run, part_counts),
        "risk_level": _risk_level(root_run, part_counts),
        "next_action": (
            "Create Part Request"
            if _dict(_entity_state(root_id, manifest).get("candidate_selection")).get("selected_candidate")
            else _next_action(part_counts, root_run)
        ),
        "updated_at": max([str((manifest or {}).get("updated_at") or ""), *[run.get("updated_at") or "" for run in runs_by_id.values()]], default=None),
        "diagnostic_codes": _diagnostic_codes(root_run, parts),
    }
    return {"summary": summary, "runs_by_id": runs_by_id, "entity_state": _entity_state(root_id, manifest)}


def _build_parts(work: dict[str, Any]) -> list[dict[str, Any]]:
    root_run = work["runs_by_id"].get(work["summary"].get("root_run_id")) or _latest_run(work["runs_by_id"]) or {}
    assembly_parts = _assembly_parts(root_run)
    rows = []
    for part in assembly_parts:
        part_id = part.get("part_id")
        accepted_results = _dict(work.get("entity_state")).get("accepted_part_results") or {}
        accepted_result = _dict(accepted_results.get(part_id)) if isinstance(part_id, str) else {}
        status = "accepted" if accepted_result.get("status") == "approved" else _part_status(part, work["runs_by_id"])
        review = _part_review_for(part_id, work["runs_by_id"])
        latest_run_id = _latest_part_run_id(part_id, work["runs_by_id"]) or work["summary"].get("root_run_id")
        accepted_run_id = _accepted_run_id(accepted_result)
        attempt_run_id = _part_download_run_id(part_id, work["runs_by_id"])
        rows.append({
            "part_id": part_id,
            "role": part.get("role"),
            "status": status,
            "result_status": "accepted" if status == "accepted" else ("ready_for_review" if status == "needs_review" else status),
            "user_review_status": "approved" if accepted_result.get("status") == "approved" else "not_reviewed",
            "agent_review_status": _dict(review).get("status"),
            "current_stage": _part_stage(status, review),
            "latest_run_id": latest_run_id,
            "download_run_id": accepted_run_id or attempt_run_id,
            "attempt_count": _part_attempt_count(part_id, work["runs_by_id"]),
            "has_step": _part_has_download(part_id, work["runs_by_id"], "model.step"),
            "has_stl": _part_has_download(part_id, work["runs_by_id"], "model.stl"),
            "has_preview": _part_has_download(part_id, work["runs_by_id"], "preview.png"),
            "deliverable_available": bool(
                accepted_run_id and _run_or_child_has_download(work["runs_by_id"], accepted_run_id, "model.step")
            ),
            "review_status": accepted_result.get("status") or _dict(review).get("status") or part.get("part_status"),
            "next_action": _part_next_action(status),
        })
    manifest_jobs = _dict(work.get("entity_state")).get("part_jobs") or []
    existing_ids = {row.get("part_id") for row in rows}
    for job in manifest_jobs:
        if not isinstance(job, dict) or job.get("part_id") in existing_ids:
            continue
        run_id = job.get("run_id")
        run = work["runs_by_id"].get(run_id) if isinstance(run_id, str) else None
        status = job.get("status") or ("incomplete" if run_id else "planned")
        rows.append({
            "part_id": job.get("part_id"),
            "role": job.get("role"),
            "status": status,
            "current_stage": "part_run" if run_id else "planned",
            "latest_run_id": run_id,
            "download_run_id": _part_download_run_id(job.get("part_id"), work["runs_by_id"]),
            "attempt_count": 1 if run_id else 0,
            "has_step": bool(run and _has_download(run, "model.step")),
            "has_stl": bool(run and _has_download(run, "model.stl")),
            "has_preview": bool(run and _has_download(run, "preview.png")),
            "review_status": None,
            "next_action": "Open part run" if run_id else "Create part run",
        })
    if rows:
        return rows
    accepted_results = _dict(work.get("entity_state")).get("accepted_part_results") or {}
    for run_id, run in sorted(work["runs_by_id"].items()):
        selected = run.get("selected_part_id")
        if selected:
            accepted_result = _dict(accepted_results.get(selected)) if isinstance(selected, str) else {}
            accepted_run_id = _accepted_run_id(accepted_result)
            generated = bool(run.get("has_step")) or _has_download(run, "model.step")
            status = "accepted" if accepted_run_id == run_id and accepted_result.get("status") == "approved" else ("needs_review" if generated else "incomplete")
            rows.append({
                "part_id": selected,
                "role": None,
                "status": status,
                "result_status": "accepted" if status == "accepted" else ("ready_for_review" if generated else "incomplete"),
                "user_review_status": "approved" if status == "accepted" else "not_reviewed",
                "agent_review_status": _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review")).get("status"),
                "current_stage": "single_part_generation",
                "latest_run_id": run_id,
                "download_run_id": run_id if any(_has_download(run, name) for name in DOWNLOADABLE_FILES) else None,
                "attempt_count": 1,
                "has_step": bool(run.get("has_step")) or _has_download(run, "model.step"),
                "has_stl": bool(run.get("has_stl")) or _has_download(run, "model.stl"),
                "has_preview": _has_download(run, "preview.png"),
                "deliverable_available": status == "accepted" and generated,
                "review_status": _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review")).get("status"),
                "next_action": "View products",
            })
    return rows


def _build_nodes(work: dict[str, Any], parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root_id = work["summary"].get("root_run_id")
    root = work["runs_by_id"].get(root_id) or _latest_run(work["runs_by_id"]) or {}
    artifacts = _artifact_names(root)
    assembly_parts = _assembly_parts(root)
    has_assembly_plan = "assembly_plan.json" in artifacts
    plan_node_id = "assembly_plan" if has_assembly_plan or assembly_parts else "planning"
    plan_label = "Split / Assembly Plan" if plan_node_id == "assembly_plan" else "Planning"
    plan_artifacts = [name for name in ("assembly_plan.json", "planning_artifact.json") if name in artifacts]
    plan_status = "completed" if plan_artifacts or assembly_parts else "not_started"
    plan_summary = f"{len(assembly_parts)} parts detected." if plan_node_id == "assembly_plan" else "Single-part planning artifact is present."
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
            "id": plan_node_id,
            "label": plan_label,
            "kind": "stage",
            "status": plan_status,
            "summary": plan_summary if plan_status == "completed" else "Planning has not started.",
            "artifacts": plan_artifacts,
            "actions": ["stage_review"] if plan_artifacts else [],
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


def _build_run_history(work: dict[str, Any], active_lineage: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for run_id, run in sorted(work["runs_by_id"].items(), key=lambda item: (item[1].get("updated_at") or "", item[0]), reverse=True):
        status = _dict(run.get("status"))
        relation, parent_run_id = _run_lineage_relation(run)
        if run_id == active_lineage.get("active_leaf_run_id") or run_id == active_lineage.get("active_root_run_id"):
            lineage_state = "active"
        elif run_id in active_lineage.get("accepted_run_ids", []):
            lineage_state = "accepted"
        elif run_id in active_lineage.get("superseded_run_ids", []):
            lineage_state = "superseded"
        elif status.get("status") in {"failed", "blocked", "error"}:
            lineage_state = "failed_branch"
        else:
            lineage_state = "historical"
        rows.append({
            "run_id": run_id,
            "kind": _run_kind(run),
            "status": status.get("status"),
            "summary": _run_summary_line(run),
            "created_at": run.get("updated_at"),
            "parent_run_id": parent_run_id,
            "root_run_id": active_lineage.get("active_root_run_id"),
            "relation": relation,
            "lineage_state": lineage_state,
            "is_current": lineage_state == "active",
            "immutable": True,
        })
    return rows


def _run_lineage_relation(run: dict[str, Any]) -> tuple[str, str | None]:
    """Expose safe run relationships from existing compact lineage summaries."""
    rework = _dict(run.get("rework_decision_summary"))
    parent = rework.get("parent_run_id")
    if isinstance(parent, str) and parent:
        return "explicit_rework_child", parent
    revision = _dict(run.get("revision_summary"))
    parent = revision.get("parent_run_id")
    if isinstance(parent, str) and parent:
        return str(revision.get("relationship") or "revision_child"), parent
    return "root", None


def _build_products(work: dict[str, Any]) -> dict[str, Any]:
    accepted_results = _dict(work.get("entity_state")).get("accepted_part_results") or {}
    accepted_run_to_parts: dict[str, list[str]] = {}
    for part_id, value in (accepted_results.items() if isinstance(accepted_results, dict) else ()):
        accepted = _dict(value)
        run_id = _accepted_run_id(accepted)
        if accepted.get("status") == "approved" and run_id:
            accepted_run_to_parts.setdefault(run_id, []).append(str(part_id))

    accepted_artifacts: dict[tuple[str, str], dict[str, Any]] = {}
    supporting_artifacts: dict[tuple[str, str], dict[str, Any]] = {}
    accepted_downloads: dict[tuple[str, str], dict[str, Any]] = {}
    reviewable_downloads: dict[tuple[str, str], dict[str, Any]] = {}
    failed_attempt_output_count = 0
    untrusted_output_count = 0
    for record in _iter_run_output_records(work["runs_by_id"]):
        run_id = str(record.get("run_id") or "")
        status = _status_value(record.get("status"))
        accepted_parts = accepted_run_to_parts.get(run_id, [])
        downloads = [name for name in record.get("downloadables", []) if name in {"model.step", "model.stl", "preview.png"}]
        for name in record.get("artifacts", []):
            supporting_artifacts[(run_id, name)] = {
                "name": name,
                "source_run_id": run_id,
                "trust_status": "evidence",
                "collapsed": True,
                "read_on_demand": True,
            }
        if accepted_parts:
            for name in record.get("artifacts", []):
                accepted_artifacts[(run_id, name)] = {
                    "name": name,
                    "source_run_id": run_id,
                    "part_ids": accepted_parts,
                    "trust_status": "accepted",
                    "collapsed": True,
                    "read_on_demand": True,
                }
            for name in downloads:
                accepted_downloads[(run_id, name)] = {
                    "name": name,
                    "source_run_id": run_id,
                    "part_ids": accepted_parts,
                    "available": True,
                    "trust_status": "accepted",
                }
        elif _attempt_status_is_failed(status):
            failed_attempt_output_count += len(downloads)
        elif _attempt_status_is_reviewable(status):
            for name in downloads:
                reviewable_downloads[(run_id, name)] = {
                    "name": name,
                    "source_run_id": run_id,
                    "available": True,
                    "trust_status": "reviewable",
                }
        else:
            untrusted_output_count += len(downloads)
    return {
        "artifact_state": {
            "accepted_deliverable_count": len(accepted_downloads),
            "reviewable_output_count": len(reviewable_downloads),
            "failed_attempt_output_count": failed_attempt_output_count,
            "untrusted_output_count": untrusted_output_count,
        },
        "accepted_deliverables": list(accepted_downloads.values()),
        "reviewable_outputs": list(reviewable_downloads.values()),
        "failed_attempt_outputs_are_diagnostics": True,
        "supporting_artifacts": filter_artifacts_for_display(list(supporting_artifacts.values())),
        # Compatibility fields now have strict semantics: Work Products and
        # Deliverables contain only explicitly accepted results.
        "human_facing": filter_artifacts_for_display(list(accepted_artifacts.values())),
        "downloadables": list(accepted_downloads.values()),
        "artifacts_secondary_by_default": True,
    }


def _build_directory_map(
    summary: dict[str, Any],
    current_run: dict[str, Any],
    parts: list[dict[str, Any]],
    products: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    artifacts = _artifact_names(current_run)
    return {
        "inputs": {
            "title": "Inputs",
            "items": [
                {"label": "Original request", "status": "completed" if "prompt.txt" in artifacts else "not_started"},
                {"label": "Reviewed requirement", "status": "completed" if "requirement_v2.json" in artifacts else "not_started"},
            ],
        },
        "planning": {
            "title": "Planning",
            "items": [{"label": "Assembly plan", "status": "completed" if "assembly_plan.json" in artifacts else "not_started"}],
        },
        "parts": {
            "title": "Parts",
            "items": [{"label": str(part.get("part_id") or "Part"), "status": part.get("status") or "incomplete"} for part in parts],
        },
        "deliverables": {
            "title": "Deliverables",
            "items": [{"label": name, "status": "completed"} for name in (item.get("name") for item in products.get("downloadables", [])) if name],
        },
        "history": {
            "title": "History",
            "items": [{"label": str(item.get("run_id") or "Run"), "status": item.get("status") or "incomplete"} for item in history],
        },
        "work_id": summary.get("work_id"),
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
        if counts["needs_review"]:
            return "needs_review"
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
    if review_status in {"accepted_for_preview", "accepted", "success", "ready_for_review"} and _part_has_download(part.get("part_id"), runs, "model.step"):
        return "needs_review"
    if review_status and ("blocked" in str(review_status) or "failed" in str(review_status)):
        return "blocked"
    if part.get("part_status") == "blocked":
        return "blocked"
    if part.get("supported_candidate") is True:
        return "incomplete"
    return "blocked" if part.get("supported_candidate") is False else "incomplete"


def _accepted_run_id(value: dict[str, Any]) -> str | None:
    run_id = value.get("child_run_id") or value.get("run_id")
    return run_id if isinstance(run_id, str) and run_id else None


def _run_or_child_has_download(runs: dict[str, dict[str, Any]], target_run_id: str, name: str) -> bool:
    run = runs.get(target_run_id)
    if isinstance(run, dict) and _has_download(run, name):
        return True
    for parent in runs.values():
        for child in parent.get("child_runs", []):
            if isinstance(child, dict) and child.get("run_id") == target_run_id and name in (child.get("downloadables") or []):
                return True
    return False


def _iter_run_output_records(runs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for run_id, run in runs.items():
        records.append({
            "run_id": run_id,
            "status": run.get("status"),
            "artifacts": _artifact_name_list(run.get("artifacts")),
            "downloadables": _artifact_name_list(run.get("downloadables")),
        })
        for child in run.get("child_runs", []):
            if not isinstance(child, dict) or not isinstance(child.get("run_id"), str):
                continue
            records.append({
                "run_id": child["run_id"],
                "status": child.get("status"),
                "artifacts": _artifact_name_list(child.get("artifacts")),
                "downloadables": _artifact_name_list(child.get("downloadables")),
            })
    return records


def _artifact_name_list(value: Any) -> list[str]:
    result = []
    for item in value if isinstance(value, list) else []:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name:
            result.append(name)
    return result


def _status_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("status")
    return str(value or "unknown")


def _attempt_status_is_failed(value: str) -> bool:
    return value in {"failed", "blocked", "error"} or "failed" in value or "blocked" in value


def _attempt_status_is_reviewable(value: str) -> bool:
    return value in {
        "success",
        "completed",
        "completed_with_assumptions",
        "ready_for_review",
        "accepted_for_preview",
        "generated",
        "accepted",
        "approved",
    }


def _part_review_for(part_id: Any, runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for run in runs.values():
        review = _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review"))
        if part_id is None or review.get("part_id") in {part_id, None}:
            if review.get("present"):
                return review
    return {}


def _part_has_download(part_id: Any, runs: dict[str, dict[str, Any]], name: str) -> bool:
    for run_id, run in runs.items():
        review = _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review"))
        selected = run.get("selected_part_id") or review.get("part_id")
        if part_id is not None and selected not in {part_id, None}:
            continue
        if part_id is not None and selected is None and not _run_id_matches_part(run_id, part_id):
            continue
        if _has_download(run, name):
            return True
        for child in run.get("child_runs", []):
            if isinstance(child, dict) and _child_matches_part(child, part_id) and name in (child.get("downloadables") or []):
                return True
    return False


def _part_download_run_id(part_id: Any, runs: dict[str, dict[str, Any]]) -> str | None:
    for name in ("model.stl", "model.step", "preview.png"):
        for run_id, run in runs.items():
            review = _dict(_dict(run.get("reviewed_part_summary")).get("part_result_review"))
            selected = run.get("selected_part_id") or review.get("part_id")
            if part_id is not None and selected not in {part_id, None}:
                continue
            if part_id is not None and selected is None and not _run_id_matches_part(run_id, part_id):
                continue
            if _has_download(run, name):
                return run_id
            for child in run.get("child_runs", []):
                if isinstance(child, dict) and _child_matches_part(child, part_id) and name in (child.get("downloadables") or []):
                    child_id = child.get("run_id")
                    return child_id if isinstance(child_id, str) and child_id else None
    return None


def _child_matches_part(child: dict[str, Any], part_id: Any) -> bool:
    if part_id is None:
        return True
    child_part = child.get("part_id") or child.get("selected_part_id")
    if child_part is not None:
        return child_part == part_id
    child_id = child.get("run_id")
    return _run_id_matches_part(child_id, part_id)


def _run_id_matches_part(run_id: Any, part_id: Any) -> bool:
    if not isinstance(run_id, str):
        return False
    normalized = str(part_id).lower().replace("-", "_")
    tokens = {token for token in run_id.lower().replace("-", "_").split("_") if token}
    return normalized in tokens


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
