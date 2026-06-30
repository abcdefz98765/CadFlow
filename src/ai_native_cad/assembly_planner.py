"""Backend-neutral assembly planning helpers.

The planner creates traceable assembly intent before any CAD assembly backend is
asked to build native files. It is intentionally conservative and deterministic
for the current L0/L1 workflow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.workflow_control import assembly_plan_decision


HIGH_RISK_TOPICS = {
    "switch": ["switch", "tactile", "button"],
    "sensor": ["sensor"],
    "wire_exit": ["wire", "cable", "harness", "线束", "出线"],
    "fastening": ["fastener", "screw", "bolt", "snap", "螺丝", "卡扣"],
}

REQUIRED_CONFIRMATION_FIELDS = {
    "switch": ["switch_envelope", "cap_travel"],
    "sensor": ["sensor_envelope"],
    "wire_exit": ["wire_exit"],
    "fastening": ["fastening_method"],
}


def create_assembly_plan(
    requirement: dict[str, Any],
    parts: list[dict[str, Any]],
    *,
    assembly_name: str | None = None,
    check_level: str | None = None,
) -> dict[str, Any]:
    """Create a traceable assembly plan and high-risk confirmation gate."""
    name = assembly_name or requirement.get("name") or requirement.get("part_type") or "assembly"
    level = check_level or requirement.get("check_level", "L0")
    intent_text = _intent_text(requirement, parts)
    provided = _provided_fields(requirement)
    high_risk = _detect_high_risk_topics(intent_text)
    unresolved = _unresolved_questions(high_risk, provided)
    status = "confirmation_needed" if unresolved else "ready_for_assembly_config"

    planned_parts = [_plan_part(part) for part in parts]
    required_contacts = _required_contacts(planned_parts)
    required_clearances = _required_clearances(high_risk, planned_parts)
    allowed_overlaps = _allowed_overlaps(planned_parts)

    plan = {
        "name": name,
        "check_level": level,
        "status": status,
        "confirmation_gate": {
            "policy": "pause_only_for_high_risk_topology",
            "needs_user_confirmation": bool(unresolved),
            "high_risk_topics": high_risk,
            "unresolved_questions": unresolved,
        },
        "manufactured_parts": [p for p in planned_parts if p["kind"] == "manufactured"],
        "reference_components": [p for p in planned_parts if p["kind"] == "reference"],
        "placement_intent": [
            {
                "part": p["name"],
                "role": p["assembly_role"],
                "datum": p["datum"],
                "intent": p["placement_intent"],
            }
            for p in planned_parts
        ],
        "required_contacts": required_contacts,
        "required_clearances": required_clearances,
        "allowed_overlaps": allowed_overlaps,
        "serviceability": _serviceability_notes(high_risk),
        "assumptions": requirement.get("assumptions", []),
        "risk_level": "high" if unresolved else "low",
    }
    plan["flow_decision"] = assembly_plan_decision(plan)
    return plan


def write_assembly_plan(plan: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write assembly_plan.json and assembly_plan.md."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "assembly_plan.json"
    md_path = output / "assembly_plan.md"
    json_path.write_text(json.dumps(plan, indent=2))
    md_path.write_text(render_assembly_plan_markdown(plan))
    return {"assembly_plan_json": str(json_path), "assembly_plan_md": str(md_path)}


def render_assembly_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# {plan['name']} Assembly Plan",
        "",
        f"**Status:** {plan['status']}",
        f"**Check level:** {plan['check_level']}",
        f"**Risk level:** {plan['risk_level']}",
        "",
        "## Confirmation Gate",
        "",
        f"- Policy: {plan['confirmation_gate']['policy']}",
        f"- Needs user confirmation: {plan['confirmation_gate']['needs_user_confirmation']}",
    ]
    for question in plan["confirmation_gate"]["unresolved_questions"] or ["None"]:
        lines.append(f"- Question: {question}")

    lines.extend(["", "## Parts", ""])
    for part in plan["manufactured_parts"]:
        lines.append(f"- {part['name']}: manufactured, role={part['assembly_role']}")
    for part in plan["reference_components"]:
        lines.append(f"- {part['name']}: reference, role={part['assembly_role']}")

    lines.extend(["", "## Placement Intent", ""])
    for item in plan["placement_intent"]:
        lines.append(f"- {item['part']}: {item['intent']} (datum={item['datum']})")

    lines.extend(["", "## Required Contacts", ""])
    lines.extend(_items(plan["required_contacts"], lambda item: f"{item['part1']} <-> {item['part2']}: {item['intent']}"))
    lines.extend(["", "## Required Clearances", ""])
    lines.extend(_items(plan["required_clearances"], lambda item: f"{item['part1']} <-> {item['part2']}: {item['clearance_mm']}mm, {item['intent']}"))
    lines.extend(["", "## Allowed Overlaps", ""])
    lines.extend(_items(plan["allowed_overlaps"], lambda item: f"{item['part1']} <-> {item['part2']}: {item['reason']}"))
    lines.extend(["", "## Serviceability", ""])
    lines.extend(f"- {note}" for note in plan["serviceability"] or ["None"])
    return "\n".join(lines) + "\n"


def create_assembly_configs(plan: dict[str, Any], part_steps: list[dict[str, Any]], output_dir: str | Path) -> dict[str, Any]:
    """Create backend-neutral absolute placement and lightweight constraint configs."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    assembly_parts = []
    constraints = []
    z_offset = 0.0
    for index, part in enumerate(part_steps):
        name = part["name"]
        position = part.get("position", [0, 0, z_offset])
        rotation = part.get("rotation", [0, 0, 0])
        assembly_parts.append({"step": part["step"], "name": name, "position": position, "rotation": rotation})
        constraints.append({"name": f"place_{name}", "type": "fixed", "part1": name, "position": position, "rotation": rotation})
        z_offset += float(part.get("stack_height", 0))

    validation = {
        "anchors": [assembly_parts[0]["name"]] if assembly_parts else [],
        "required_contacts": plan.get("required_contacts", []),
        "allowed_bbox_overlaps": plan.get("allowed_overlaps", []),
    }
    assembly = {
        "name": plan["name"],
        "output_dir": str(output),
        "validation": validation,
        "parts": assembly_parts,
    }
    constraint_assembly = {
        "name": f"{plan['name']}_constraints",
        "output_dir": str(output / "constraint_assembly"),
        "check_interference": False,
        "parts": [{"step": part["step"], "name": part["name"]} for part in assembly_parts],
        "constraints": constraints,
    }
    (output / "assembly.json").write_text(json.dumps(assembly, indent=2))
    (output / "constraint_assembly.json").write_text(json.dumps(constraint_assembly, indent=2))
    return {"assembly": assembly, "constraint_assembly": constraint_assembly}


def _intent_text(requirement: dict[str, Any], parts: list[dict[str, Any]]) -> str:
    chunks = [json.dumps(requirement, ensure_ascii=False)]
    chunks.extend(json.dumps(part, ensure_ascii=False) for part in parts)
    return " ".join(chunks).lower()


def _provided_fields(requirement: dict[str, Any]) -> set[str]:
    fields = set(requirement)
    fields.update(requirement.get("features", {}).keys())
    fields.update(requirement.get("assembly", {}).keys())
    fields.update(requirement.get("interfaces", {}).keys())
    return fields


def _detect_high_risk_topics(text: str) -> list[str]:
    return [topic for topic, tokens in HIGH_RISK_TOPICS.items() if any(token in text for token in tokens)]


def _unresolved_questions(topics: list[str], provided: set[str]) -> list[str]:
    questions = []
    for topic in topics:
        missing = [field for field in REQUIRED_CONFIRMATION_FIELDS[topic] if field not in provided]
        if missing:
            questions.append(f"Confirm {topic} topology fields: {', '.join(missing)}.")
    return questions


def _plan_part(part: dict[str, Any]) -> dict[str, Any]:
    name = part.get("name") or part.get("part_type") or "part"
    role = part.get("assembly_role") or _role_from_name(name)
    kind = part.get("kind") or ("reference" if any(token in name for token in ["switch", "sensor", "reference"]) else "manufactured")
    return {
        "name": name,
        "kind": kind,
        "assembly_role": role,
        "datum": part.get("datum", "bottom_z"),
        "mating_faces": part.get("mating_faces", []),
        "placement_intent": part.get("placement_intent", f"Place {name} according to its {role} role."),
    }


def _role_from_name(name: str) -> str:
    lowered = name.lower()
    if "base" in lowered:
        return "base"
    if "cap" in lowered or "button" in lowered:
        return "moving_actuator"
    if "switch" in lowered:
        return "switch_reference"
    if "plate" in lowered or "carrier" in lowered:
        return "carrier"
    return "component"


def _required_contacts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {part["assembly_role"]: part["name"] for part in parts}
    contacts = []
    if "carrier" in names and "switch_reference" in names:
        contacts.append({
            "part1": names["carrier"],
            "part2": names["switch_reference"],
            "axis": "z",
            "intent": "switch reference body is seated on the carrier",
        })
    return contacts


def _required_clearances(topics: list[str], parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if "wire_exit" not in topics:
        return []
    base = next((p["name"] for p in parts if p["assembly_role"] == "base"), "base")
    return [{"part1": base, "part2": "wire_harness", "clearance_mm": 0.5, "intent": "wire outlet keeps routing clearance"}]


def _allowed_overlaps(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = next((p["name"] for p in parts if p["assembly_role"] == "base"), None)
    if not base:
        return []
    rules = []
    for part in parts:
        if part["name"] == base:
            continue
        if part["assembly_role"] in {"moving_actuator", "carrier", "switch_reference"}:
            rules.append({"part1": base, "part2": part["name"], "reason": f"{part['name']} is intentionally installed inside or through the base envelope"})
    return rules


def _serviceability_notes(topics: list[str]) -> list[str]:
    notes = []
    if "switch" in topics or "sensor" in topics:
        notes.append("Keep the switch or sensor reachable until the design explicitly chooses a sealed assembly.")
    if "wire_exit" in topics:
        notes.append("Keep the wire exit direction and bend relief traceable in the assembly plan.")
    return notes


def _items(items: list[dict[str, Any]], formatter) -> list[str]:
    if not items:
        return ["- None"]
    return [f"- {formatter(item)}" for item in items]
