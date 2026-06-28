"""Workflow-first natural-language CAD pipeline.

The workflow is intentionally small for the MVP:

input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs

Only L0 is actively supported today. L1 returns a report scaffold so maker
checks can be filled in without changing the public workflow contract.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_native_cad.backends import CADBackend, CadQueryBackend, ModelArtifact
from ai_native_cad.requirements import CHECK_LEVELS, RequirementAgent, normalize_check_level
from ai_native_cad.validator import preflight_design_intent

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class WorkflowResult:
    """Paths and status produced by a workflow run."""

    status: str
    output_dir: Path
    requirement: dict[str, Any]
    plan_path: Path
    review_path: Path
    files: dict[str, str]
    elapsed: float
    error: str | None = None


class RequirementParser(RequirementAgent):
    """Parse natural-language input into a structured requirement.

    Compatibility alias for the requirement agent. The current implementation
    remains deterministic, but now records field policy, assumptions, missing
    information, and follow-up questions in ``requirement.json``.
    """

    pass


class DesignPlanner:
    """Create a human-readable model plan from structured requirements."""

    def create_plan(self, requirement: dict[str, Any]) -> str:
        dimensions = requirement.get("dimensions", {})
        features = requirement.get("features", {})
        lines = [
            f"# Design Plan: {requirement['part_type']}",
            "",
            f"- Unit: {requirement.get('unit', 'mm')}",
            f"- Check level: {requirement.get('check_level', 'L0')} ({CHECK_LEVELS[requirement.get('check_level', 'L0')]})",
            "- Backend target: selected by workflow backend adapter",
            "",
            "## Parameters",
            "",
        ]
        for key, value in dimensions.items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Feature Tree", ""])
        for name, feature in features.items():
            if isinstance(feature, dict):
                feature_type = feature.get("type", "custom")
                lines.append(f"- {name}: {feature_type}")
            else:
                lines.append(f"- {name}: {feature}")
        lines.extend([
            "",
            "## Modeling Order",
            "",
            "1. Establish datum at the part center on the XY plane.",
            "2. Build the primary solid from the main dimensions.",
            "3. Apply functional subtractive features such as holes or slots.",
            "4. Apply low-risk edge finishes after functional geometry is valid.",
            "5. Export exchange files and run the selected review level.",
        ])
        return "\n".join(lines) + "\n"


class CADGenerator:
    """Generate backend-native models through a CAD backend adapter."""

    def __init__(self, backend: CADBackend | None = None):
        self.backend = backend or CadQueryBackend()

    def build(self, requirement: dict[str, Any]) -> ModelArtifact:
        return self.backend.build_model(requirement)


class Reviewer:
    """Review generated models according to the requested check level."""

    def review(
        self,
        artifact: ModelArtifact,
        requirement: dict[str, Any],
        validation: dict[str, Any],
        files: dict[str, str],
    ) -> str:
        level = requirement.get("check_level", "L0")
        status = "PASS" if validation.get("valid") else "FAIL"
        sections = validation.get("sections", {})
        intent_match = sections.get("intent_match", {})
        lines = [
            f"# Review: {requirement['part_type']}",
            "",
            f"- Status: {status}",
            f"- Backend: {artifact.backend}",
            f"- Check level: {level} ({CHECK_LEVELS[level]})",
            "",
            "## Generation Loop",
            "",
            f"- Preflight: {_stage_status(sections.get('preflight'))}",
            f"- Geometry: {_stage_status(sections.get('geometry'))}",
            f"- Export: {_stage_status(sections.get('export'))}",
            f"- Intent match: {_stage_status(intent_match)}",
            "",
            "## L0 Playground Checks",
            "",
            f"- Model generated: {'yes' if artifact.model is not None else 'no'}",
            f"- Exported files: {', '.join(sorted(files)) if files else 'none'}",
            f"- Validation passed: {'yes' if validation.get('valid') else 'no'}",
        ]
        if level == "L1":
            lines.extend([
                "",
                "## L1 Maker Scaffold",
                "",
                "- Minimum wall thickness: not implemented yet",
                "- Overhang/support risk: not implemented yet",
                "- STL printability: not implemented yet",
            ])
        elif level not in {"L0", "L1"}:
            lines.extend(["", "## Reserved Checks", "", f"- {level} is reserved and not supported in the MVP."])

        warnings = validation.get("warnings", [])
        errors = validation.get("errors", [])
        if warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {item.get('code', 'warning')}: {item.get('message', item)}" for item in warnings)
        if errors:
            lines.extend(["", "## Errors", ""])
            lines.extend(f"- {item.get('code', 'error')}: {item.get('message', item)}" for item in errors)
        verified = intent_match.get("verified", [])
        assumed = intent_match.get("assumed", [])
        unverified = intent_match.get("unverified", [])
        lines.extend(["", "## Intent Match", ""])
        lines.append(f"- Verified items: {len(verified)}")
        lines.append(f"- Assumptions carried forward: {len(assumed)}")
        lines.append(f"- Unverified items: {len(unverified)}")
        if unverified:
            lines.extend(["", "### Unverified", ""])
            for item in unverified[:12]:
                name = item.get("name", "unknown")
                kind = item.get("kind", "item")
                reason = item.get("reason", "not verified")
                lines.append(f"- {kind}:{name} - {reason}")
        return "\n".join(lines) + "\n"


class Exporter:
    """Export workflow artifacts and keep the trace directory stable."""

    def __init__(self, backend: CADBackend):
        self.backend = backend

    def export(self, artifact: ModelArtifact, output_dir: Path, formats: list[str]) -> dict[str, str]:
        export_dir = output_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        return self.backend.export_model(artifact, export_dir, formats)


class CADWorkflow:
    """Run the MVP workflow and write traceable project outputs."""

    def __init__(self, backend: CADBackend | None = None):
        self.backend = backend or CadQueryBackend()
        self.parser = RequirementParser()
        self.planner = DesignPlanner()
        self.generator = CADGenerator(self.backend)
        self.exporter = Exporter(self.backend)
        self.reviewer = Reviewer()

    def run(
        self,
        input_text: str,
        output_dir: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        start = time.perf_counter()
        requirement = self.parser.parse(input_text, overrides)
        instance_name = requirement.get("instance_name", requirement["part_type"])
        root = Path(output_dir) if output_dir is not None else PROJECT_ROOT / "runs" / instance_name
        root.mkdir(parents=True, exist_ok=True)
        logs_dir = root / "logs"
        logs_dir.mkdir(exist_ok=True)

        (root / "input.md").write_text(input_text.strip() + "\n", encoding="utf-8")
        _write_json(root / "requirement.json", requirement)
        _write_json(root / "part_spec.json", _part_spec(requirement))
        plan = self.planner.create_plan(requirement)
        plan_path = root / "plan.md"
        plan_path.write_text(plan, encoding="utf-8")
        preflight = preflight_design_intent(requirement)

        try:
            artifact = self.generator.build(requirement)
            files = self.exporter.export(artifact, root, requirement.get("outputs", ["step", "stl"]))
            validation = self.backend.validate_model(artifact, root / "exports", requirement)
            review = self.reviewer.review(artifact, requirement, validation, files)
            review_path = root / "review.md"
            review_path.write_text(review, encoding="utf-8")
            _copy_source_model(requirement["part_type"], root / "model.py")
            log = {
                "timestamp": datetime.now().isoformat(),
                "status": "success" if validation.get("valid") else "failed",
                "backend": artifact.backend,
                "part_type": requirement["part_type"],
                "preflight": preflight,
                "generation_loop": {
                    "preflight": validation.get("sections", {}).get("preflight", preflight),
                    "geometry": validation.get("sections", {}).get("geometry", {}),
                    "export": validation.get("sections", {}).get("export", {}),
                    "intent_match": validation.get("sections", {}).get("intent_match", {}),
                },
                "files": files,
                "validation": validation,
            }
            _write_json(logs_dir / "run.json", log)
            _write_json(logs_dir / "generation.json", log)
            return WorkflowResult(
                status=log["status"],
                output_dir=root,
                requirement=requirement,
                plan_path=plan_path,
                review_path=review_path,
                files=files,
                elapsed=round(time.perf_counter() - start, 2),
            )
        except Exception as exc:
            message = str(exc)
            review_path = root / "review.md"
            review_path.write_text(f"# Review: {requirement['part_type']}\n\n- Status: ERROR\n- Error: {message}\n", encoding="utf-8")
            log = {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "part_type": requirement["part_type"],
                "preflight": preflight,
                "error": message,
            }
            _write_json(logs_dir / "run.json", log)
            _write_json(logs_dir / "generation.json", log)
            return WorkflowResult(
                status="error",
                output_dir=root,
                requirement=requirement,
                plan_path=plan_path,
                review_path=review_path,
                files={},
                elapsed=round(time.perf_counter() - start, 2),
                error=message,
            )


def run_workflow(
    input_text: str,
    output_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    backend: CADBackend | None = None,
) -> WorkflowResult:
    """Convenience entry point for the natural-language CAD workflow."""
    return CADWorkflow(backend=backend).run(input_text, output_dir=output_dir, overrides=overrides)


def _normalize_check_level(value: str) -> str:
    return normalize_check_level(value)


def _copy_source_model(part_type: str, destination: Path) -> None:
    sources = [
        PROJECT_ROOT / "examples" / "parts" / part_type / "model.py",
        PROJECT_ROOT / "examples" / part_type / "model.py",
    ]
    sources.extend((PROJECT_ROOT / "examples").glob(f"assemblies/*/parts/{part_type}/model.py"))
    source = next((candidate for candidate in sources if candidate.exists()), None)
    if source is not None:
        shutil.copyfile(source, destination)


def _part_spec(requirement: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "part_type",
        "unit",
        "dimensions",
        "features",
        "outputs",
        "check_level",
        "intent",
        "assumptions",
        "manufacturing",
        "assembly_role",
        "mating_faces",
    ]
    return {key: requirement[key] for key in keys if key in requirement}


def _stage_status(section: dict[str, Any] | None) -> str:
    if section is None:
        return "not run"
    return "pass" if section.get("valid") else "fail"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
