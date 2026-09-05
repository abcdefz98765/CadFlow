"""Focused regressions for transient live Part execution state."""

from __future__ import annotations

import asyncio
import threading

from ai_native_cad.workflow_console.action_lifecycle import (
    _continue_agent_async,
    _design_runnable_parts_async,
    _pending_action_matches,
    _set_action_execution,
    ActionExecutionState,
)
from ai_native_cad.workflow_console.canonical_interaction import project_canonical_interaction
from ai_native_cad.workflow_console.workflow_graph_ui import workflow_graph_with_runtime
from ai_native_cad.workflow_console.product_usability import _budget_exhaustion_copy
from ai_native_cad.workflow_console.workflow_page_view_model import _workbench_part_jobs


def test_retry_child_attempt_is_visible_before_blocking_provider_releases():
    class Backend:
        def __init__(self):
            self.release = threading.Event()
            self.create_calls = 0
            self.manifest = {
                "accepted_part_results": {"clamp": {"result_id": "accepted"}},
                "artifact_references": [],
                "part_jobs": [{
                    "part_job_id": "clamp", "role": "fixture clamp",
                    "active_attempt_run_id": "attempt_1",
                    "attempts": [{"run_id": "attempt_1", "parent_run_id": None}],
                }],
            }

        def _read_work_manifest(self, _work_id):
            import copy
            return copy.deepcopy(self.manifest)

        def create_work_part_attempt(self, _work, _part, *, role, parent_run_id):
            self.create_calls += 1
            job = self.manifest["part_jobs"][0]
            job["attempts"].append({"run_id": "attempt_2", "parent_run_id": parent_run_id})
            job["active_attempt_run_id"] = "attempt_2"
            return {"part_job": dict(job)}

        def run_work_part_design_episode(self, *_args, **_kwargs):
            self.release.wait(timeout=3)
            self.manifest["artifact_references"].append({"artifact_id": "episode"})
            return {"episode": {"status": "completed", "stop_reason": "completed"}}

    async def exercise():
        backend, state, refreshes = Backend(), {}, []
        task = asyncio.create_task(_continue_agent_async(
            backend,
            {"key": "retry_agent", "target_work_id": "w", "part_job_id": "clamp", "target_run_id": "attempt_1", "recovery_mode": "new_attempt"},
            state, lambda: refreshes.append(backend._read_work_manifest("w")), "en",
        ))
        for _ in range(20):
            await asyncio.sleep(0.01)
            if backend.manifest["part_jobs"][0]["active_attempt_run_id"] == "attempt_2":
                break
        assert backend.manifest["part_jobs"][0]["active_attempt_run_id"] == "attempt_2"
        assert state["action_execution"]["target_run_id"] == "attempt_2"
        assert state["action_execution"]["status"] == "pending"
        assert refreshes and refreshes[-1]["part_jobs"][0]["active_attempt_run_id"] == "attempt_2"
        assert backend.manifest["accepted_part_results"] == {"clamp": {"result_id": "accepted"}}
        assert _pending_action_matches(state, {
            "key": "retry_agent", "target_work_id": "w", "part_job_id": "clamp",
            "target_run_id": "attempt_1", "recovery_mode": "new_attempt",
        })
        duplicate = await _continue_agent_async(
            backend,
            {"key": "retry_agent", "target_work_id": "w", "part_job_id": "clamp", "target_run_id": "attempt_1", "recovery_mode": "new_attempt"},
            state, lambda: None, "en",
        )
        assert duplicate is None
        assert backend.create_calls == 1
        backend.release.set()
        await task

    asyncio.run(exercise())


def test_retry_child_creation_failure_is_visible_and_does_not_call_provider():
    class Backend:
        def __init__(self):
            self.provider_calls = 0

        def _read_work_manifest(self, _work_id):
            return {
                "accepted_part_results": {}, "artifact_references": [],
                "part_jobs": [{"part_job_id": "clamp", "role": "clamp", "active_attempt_run_id": "attempt_1", "attempts": [{"run_id": "attempt_1"}]}],
            }

        def create_work_part_attempt(self, *_args, **_kwargs):
            raise OSError("manifest write failed")

        def run_work_part_design_episode(self, *_args, **_kwargs):
            self.provider_calls += 1
            raise AssertionError("provider must not run")

    async def exercise():
        backend, state, refreshes = Backend(), {}, []
        result = await _continue_agent_async(
            backend,
            {"key": "retry_agent", "target_work_id": "w", "part_job_id": "clamp", "target_run_id": "attempt_1", "recovery_mode": "new_attempt"},
            state, lambda: refreshes.append(True), "en",
        )
        assert result is None
        assert state["action_execution"]["status"] == "failed"
        assert state["action_execution"]["error_code"] == "OSError"
        assert backend.provider_calls == 0
        assert refreshes == [True]

    asyncio.run(exercise())


def test_frontier_is_durable_not_dependency_inferred_and_graph_overlays_two_attempts():
    parts = [
        {"part_job_id": "base", "name": "Base", "state": "design", "active_attempt_run_id": "base_1"},
        {"part_job_id": "cover", "name": "Cover", "state": "design", "active_attempt_run_id": "cover_1"},
    ]
    interaction = project_canonical_interaction(
        work_id="fixture", work_design={"status": "completed", "dependencies": [{"from": "base", "to": "cover"}]},
        parts=parts, current_result=None, recovery=None, language="en",
    )
    action = interaction["work"]["primary_action"]
    assert action["key"] == "design_runnable_parts"
    assert [item["part_job_id"] for item in action["part_targets"]] == ["base", "cover"]

    state: dict = {}
    for target in action["part_targets"]:
        scoped = {"key": "continue_agent", "target_work_id": "fixture", "part_job_id": target["part_job_id"], "target_run_id": target["target_run_id"]}
        _set_action_execution(state, ActionExecutionState.from_action(scoped), scoped)
    graph = workflow_graph_with_runtime({"nodes": [
        {"id": "attempt:base:base_1", "status": "not_started"},
        {"id": "attempt:cover:cover_1", "status": "not_started"},
    ], "current_attention": []}, state, "en")
    assert {node["status"] for node in graph["nodes"]} == {"running"}


def test_blocked_part_recovery_keeps_work_level_frontier_available():
    parts = [
        {"part_job_id": "base", "name": "Base", "state": "design", "active_attempt_run_id": "base_1"},
        {"part_job_id": "cover", "name": "Cover", "state": "design", "active_attempt_run_id": "cover_1", "attempt_blocked": True},
        {"part_job_id": "arm", "name": "Arm", "state": "design", "active_attempt_run_id": "arm_1"},
    ]

    interaction = project_canonical_interaction(
        work_id="fixture",
        work_design={"status": "completed"},
        parts=parts,
        current_result=None,
        recovery={
            "part_job_id": "cover",
            "run_id": "cover_1",
            "recommended_action": {"key": "retry_agent", "label": "Retry"},
        },
        language="en",
    )

    assert interaction["work"]["primary_action"]["key"] == "retry_agent"
    frontier = interaction["work"]["secondary_actions"][0]
    assert frontier["key"] == "design_runnable_parts"
    assert [item["part_job_id"] for item in frontier["part_targets"]] == ["arm", "base"]


def test_part_projection_marks_a_blocked_active_attempt_not_runnable():
    jobs = _workbench_part_jobs(
        {
            "part_jobs": [
                {
                    "part_job_id": "base",
                    "active_attempt_run_id": "base_1",
                    "attempts": [{"run_id": "base_1"}],
                }
            ]
        },
        {},
        [
            {
                "part_job_id": "base",
                "run_id": "base_1",
                "checkpoint": "product_design_routing",
                "validation_status": "blocked",
            }
        ],
        {},
        [],
        "en",
    )

    assert jobs[0]["attempt_blocked"] is True
    interaction = project_canonical_interaction(
        work_id="fixture",
        work_design={"status": "completed"},
        parts=[
            jobs[0],
            {"part_job_id": "cover", "state": "design", "active_attempt_run_id": "cover_1"},
            {"part_job_id": "arm", "state": "design", "active_attempt_run_id": "arm_1"},
        ],
        current_result=None,
        recovery=None,
        language="en",
    )
    assert [item["part_job_id"] for item in interaction["work"]["primary_action"]["part_targets"]] == ["arm", "cover"]


def test_dispatcher_reuses_attempts_limits_concurrency_and_isolates_failure():
    class Backend:
        def __init__(self):
            self.active = self.maximum = 0
            self.calls = []
            self.lock = threading.Lock()

        def run_work_part_design_episode(self, _work, part, *, request_id, attempt_run_id):
            with self.lock:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                self.calls.append((part, attempt_run_id, request_id))
            import time
            time.sleep(0.04)
            with self.lock:
                self.active -= 1
            if part == "cover":
                raise RuntimeError("cover provider failure")
            return {"episode": {"status": "completed", "stop_reason": "completed"}}

    async def exercise():
        backend, state, refreshes = Backend(), {}, []
        action = {
            "key": "design_runnable_parts", "target_work_id": "w", "request_fingerprint": "stable",
            "part_targets": [
                {"part_job_id": "base", "target_run_id": "base_1"},
                {"part_job_id": "cover", "target_run_id": "cover_1"},
                {"part_job_id": "bracket", "target_run_id": "bracket_1"},
            ],
        }
        result = await _design_runnable_parts_async(backend, action, state, lambda: refreshes.append(True), "en")
        assert backend.maximum == 2
        assert {(part, run) for part, run, _ in backend.calls} == {("base", "base_1"), ("cover", "cover_1"), ("bracket", "bracket_1")}
        assert result["parts"]["cover"]["ok"] is False
        assert result["parts"]["base"]["ok"] is True
        assert result["parts"]["bracket"]["ok"] is True
        assert len(refreshes) >= 4  # initial pending projection + every terminal Part

    asyncio.run(exercise())


def test_dispatcher_coalesces_same_frontier_request_across_ui_states():
    class Backend:
        def __init__(self):
            self.release = threading.Event()
            self.calls: list[tuple[str, str]] = []

        def run_work_part_design_episode(self, _work, part, *, request_id, attempt_run_id):
            self.calls.append((part, attempt_run_id))
            self.release.wait(timeout=2)
            return {"episode": {"status": "completed", "stop_reason": "completed"}}

    async def exercise():
        backend = Backend()
        action = {
            "key": "design_runnable_parts", "target_work_id": "w", "request_fingerprint": "same",
            "part_targets": [
                {"part_job_id": "base", "target_run_id": "base_1"},
                {"part_job_id": "cover", "target_run_id": "cover_1"},
            ],
        }
        first = asyncio.create_task(_design_runnable_parts_async(backend, action, {}, lambda: None, "en"))
        second = asyncio.create_task(_design_runnable_parts_async(backend, action, {}, lambda: None, "en"))
        await asyncio.sleep(0.03)
        assert sorted(backend.calls) == [("base", "base_1"), ("cover", "cover_1")]
        backend.release.set()
        await asyncio.gather(first, second)

    asyncio.run(exercise())


def test_parallel_limit_is_process_wide_across_distinct_frontier_requests():
    class Backend:
        def __init__(self):
            self.active = self.maximum = 0
            self.calls = 0
            self.lock = threading.Lock()

        def run_work_part_design_episode(self, *_args, **_kwargs):
            with self.lock:
                self.calls += 1
                self.active += 1
                self.maximum = max(self.maximum, self.active)
            import time
            time.sleep(0.03)
            with self.lock:
                self.active -= 1
            return {"episode": {"status": "completed", "stop_reason": "completed"}}

    async def exercise():
        backend = Backend()
        targets = [
            {"part_job_id": part, "target_run_id": f"{part}_1"}
            for part in ("a", "b", "c")
        ]
        actions = [
            {"key": "design_runnable_parts", "target_work_id": "w", "request_fingerprint": fingerprint, "part_targets": targets}
            for fingerprint in ("frontier_one", "frontier_two")
        ]
        await asyncio.gather(*(
            _design_runnable_parts_async(backend, action, {}, lambda: None, "en")
            for action in actions
        ))
        assert backend.maximum == 2
        assert backend.calls == 3

    asyncio.run(exercise())


def test_batch_and_individual_actions_coalesce_the_same_part_attempt():
    class Backend:
        def __init__(self):
            self.release = threading.Event()
            self.started = threading.Event()
            self.calls = 0
            self.manifest = {
                "accepted_part_results": {},
                "artifact_references": [],
                "part_jobs": [{
                    "part_job_id": "base", "active_attempt_run_id": "base_1",
                    "attempts": [{"run_id": "base_1"}],
                }],
            }

        def _read_work_manifest(self, _work_id):
            import copy
            return copy.deepcopy(self.manifest)

        def run_work_part_design_episode(self, *_args, **_kwargs):
            self.calls += 1
            self.started.set()
            self.release.wait(timeout=2)
            self.manifest["artifact_references"].append({"artifact_id": "route"})
            return {"episode": {"status": "completed", "stop_reason": "completed"}}

    async def exercise():
        backend = Backend()
        batch = asyncio.create_task(_design_runnable_parts_async(
            backend,
            {"key": "design_runnable_parts", "target_work_id": "w", "request_fingerprint": "batch", "part_targets": [{"part_job_id": "base", "target_run_id": "base_1"}]},
            {}, lambda: None, "en",
        ))
        await asyncio.to_thread(backend.started.wait, 1)
        individual = asyncio.create_task(_continue_agent_async(
            backend,
            {"key": "continue_agent", "target_work_id": "w", "part_job_id": "base", "target_run_id": "base_1"},
            {}, lambda: None, "en",
        ))
        await asyncio.sleep(0.08)
        assert backend.calls == 1
        backend.release.set()
        await asyncio.gather(batch, individual)
        assert backend.calls == 1

    asyncio.run(exercise())


def test_budget_copy_uses_exact_durable_diagnostic_or_historical_fallback():
    detailed = _budget_exhaustion_copy({"failure_diagnostic": {
        "reason_code": "budget_exhausted.wall_clock_seconds", "budget_kind": "wall_clock_seconds",
        "used": 61, "limit": 60, "agent_steps": 7,
    }}, "en")
    assert "wall-clock time budget was exhausted: used 61 of 60" in detailed["why"]
    assert detailed["budget_diagnostic"] == {
        "reason_code": "budget_exhausted.wall_clock_seconds", "budget_kind": "wall_clock_seconds",
        "used": 61, "limit": 60, "agent_steps": 7,
    }
    assert _budget_exhaustion_copy({}, "en")["why"] == (
        "CadFlow stopped safely at the declared resource budget."
    )
