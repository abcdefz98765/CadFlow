import json
from uuid import uuid4
from pathlib import Path

import pytest

from ai_native_cad.agents import DeterministicAgentAdapter
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS
from ai_native_cad.workflow_console import STATUS_CREATED, WORKFLOW_STATUS_VALUES, StageRunner, WorkflowConsoleBackend


def test_stage_runner_runs_requirement_and_planning_to_artifacts(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    output_dir = tmp_path / "outputs" / "console_requirement_planning"

    requirement_result = runner.run_requirement(
        "Generate an 80x40x5 mm mounting plate with four M4 holes in the corners.",
        {"output_dir": output_dir},
    )
    planning_result = runner.run_planning(requirement_result["requirement"], {"output_dir": output_dir})
    artifacts = runner.read_artifacts(output_dir)
    runtime = artifacts["logs/runtime.json"]["workflow_console"]

    assert requirement_result["stage"] == "requirement"
    assert requirement_result["stage_status"] == "completed"
    assert planning_result["stage"] == "planning"
    assert planning_result["stage_status"] == "completed"
    assert (output_dir / "prompt.txt").exists()
    assert artifacts["requirement.json"]["part_type"] == "mounting_plate"
    assert artifacts["planning_artifact.json"]["artifact_type"] == "planning"
    assert [stage["stage"] for stage in runtime["stages"]] == ["requirement", "planning"]
    assert runtime["latest_stage"]["stage"] == "planning"


def test_backend_reads_stage_status_from_runtime_without_report(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    output_dir = tmp_path / "outputs" / "console_requirement_only"

    runner.run_requirement("Make a mounting plate.", {"output_dir": output_dir})

    backend = WorkflowConsoleBackend(project_root=tmp_path, stage_runner=runner)
    metadata = backend.read_run_metadata(output_dir)
    runtime = backend.read_artifact(output_dir, "logs/runtime.json")

    assert metadata["status"]["status"] == "completed"
    assert metadata["status"]["stage"] == "requirement"
    assert runtime["content"]["workflow_console"]["latest_stage"]["stage"] == "requirement"


def test_backend_creates_run_without_executing_stages(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    created = backend.create_run("Make a mounting plate.", run_name="created_run")
    run_dir = Path(created["run"]["run_dir"])
    listed = backend.list_runs()

    assert created["result"]["status"] == "created"
    assert created["run"]["status"]["status"] == "created"
    assert created["run"]["status"]["stage"] == "created"
    assert [run["run_id"] for run in listed] == ["created_run"]
    assert (run_dir / "prompt.txt").exists()
    assert not (run_dir / "requirement.json").exists()

    requirement = backend.run_stage(run_dir, "requirement")
    assert requirement["result"]["stage"] == "requirement"
    assert (run_dir / "requirement.json").exists()


def test_backend_creates_run_by_safe_id_under_configured_root(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    created = backend.create_run_by_id("created_by_id", "Make a spacer.", root="runs")
    metadata = backend.read_run_metadata_by_id("created_by_id", root="runs")

    assert created["result"]["status"] == STATUS_CREATED
    assert created["run"]["run_id"] == "created_by_id"
    assert created["run"]["status"]["status"] in WORKFLOW_STATUS_VALUES
    assert Path(created["run"]["run_dir"]) == (tmp_path / "runs" / "created_by_id").resolve()
    assert metadata["status"]["stage"] == STATUS_CREATED
    assert (tmp_path / "runs" / "created_by_id" / "prompt.txt").read_text(encoding="utf-8") == "Make a spacer.\n"


def test_backend_create_run_by_id_rejects_unsafe_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.create_run_by_id("../outside", "Make a spacer.")


def test_backend_create_run_by_id_rejects_unconfigured_root(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run root is not configured"):
        backend.create_run_by_id("created_by_id", "Make a spacer.", root="tmp")


def test_backend_create_run_by_id_rejects_existing_run(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("created_by_id", "Make a spacer.")

    with pytest.raises(FileExistsError, match="workflow console run already exists"):
        backend.create_run_by_id("created_by_id", "Make another spacer.")


def test_backend_runs_stages_from_existing_run_artifacts(tmp_path):
    runner = StageRunner()
    backend = WorkflowConsoleBackend(stage_runner=runner)
    run_dir = Path.cwd() / "outputs" / f"pytest_console_stage_sequence_{uuid4().hex}"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.\n",
        encoding="utf-8",
    )

    requirement = backend.run_stage(run_dir, "requirement")
    planning = backend.run_stage(run_dir, "planning")
    modeling = backend.run_stage(run_dir, "part_modeling")
    runtime = backend.read_artifact(run_dir, "logs/runtime.json")["content"]["workflow_console"]

    assert requirement["result"]["stage"] == "requirement"
    assert planning["result"]["stage"] == "planning"
    assert modeling["result"]["status"] == "success"
    assert (run_dir / "input_ir.json").exists()
    assert (run_dir / "model.step").exists()
    assert [stage["stage"] for stage in runtime["stages"]] == ["requirement", "planning", "part_modeling"]


def test_workflow_console_backend_lists_status_artifacts_and_downloadables(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps({"status": "success", "success": True, "flow_decision": {"action": "proceed"}}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "agent_trace.json").write_text(
        json.dumps({"total_attempts": 1, "final_selected_candidate": "A"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    runs = backend.list_runs()
    metadata = backend.read_run_metadata(run_dir)
    report = backend.read_artifact(run_dir, "report.json")

    assert [run["run_id"] for run in runs] == ["console_run"]
    assert metadata["status"]["status"] == "success"
    assert metadata["status"]["attempts"] == 1
    assert [item["name"] for item in metadata["downloadables"]] == ["model.step"]
    assert report["content"]["flow_decision"]["action"] == "proceed"


def test_backend_resolves_metadata_by_safe_run_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = backend.read_run_metadata_by_id("console_run", root="outputs")

    assert metadata["run_id"] == "console_run"
    assert Path(metadata["run_dir"]) == run_dir.resolve()


def test_backend_rejects_path_traversal_run_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.read_run_metadata_by_id("../outside")


def test_backend_rejects_absolute_run_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.read_run_metadata_by_id(str(tmp_path / "outputs" / "console_run"))


def test_backend_unknown_run_id_raises_clear_error(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(FileNotFoundError, match="workflow console run not found: missing_run"):
        backend.read_run_metadata_by_id("missing_run")


def test_backend_rejects_artifact_path_traversal_by_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="artifact is not readable"):
        backend.read_artifact_by_id("console_run", "../report.json")


def test_backend_rejects_unsupported_stage_by_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="unsupported workflow console stage"):
        backend.run_stage_by_id("console_run", "shell")


def test_backend_downloadables_by_id_remain_whitelisted(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    for name in ["model.step", "model.stl", "preview.png", "model.py", "notes.txt", "report.md"]:
        (run_dir / name).write_text(f"{name}\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    assert [item["name"] for item in backend.list_downloadables_by_id("console_run")] == [
        "model.step",
        "model.stl",
        "preview.png",
        "model.py",
    ]


def test_backend_artifacts_by_id_remain_readable_artifact_whitelist(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "logs").mkdir()
    for name in READABLE_ARTIFACTS:
        artifact_path = run_dir / name
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        content = "{}\n" if artifact_path.suffix == ".json" else f"{name}\n"
        artifact_path.write_text(content, encoding="utf-8")
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")
    (run_dir / "extra.json").write_text("{}\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    assert {item["name"] for item in backend.list_artifacts_by_id("console_run")} == READABLE_ARTIFACTS
    with pytest.raises(ValueError, match="artifact is not readable"):
        backend.read_artifact_by_id("console_run", "extra.json")


def test_stage_runner_text_pipeline_and_deterministic_adapter_smoke():
    adapter = DeterministicAgentAdapter()
    requirement = adapter.parse_requirement("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")
    assert requirement["part_type"] == "spacer"

    output_dir = Path.cwd() / "outputs" / "pytest_stage_runner_text_pipeline_smoke"
    result = StageRunner().run_text_pipeline(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.",
        {"output_dir": output_dir},
    )
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert (output_dir / "model.step").exists()
    assert (output_dir / "report.json").exists()
    assert runtime["workflow_console"]["latest_stage"]["stage"] == "text_pipeline"
