"""Canonical registered-Skill request compilation for JSON providers.

Legacy requirement/planning/compiler prompts deliberately live elsewhere.
"""

from __future__ import annotations

import json
from typing import Any

from ai_native_cad.agents.provider_sanitization import sanitize_provider_payload
from ai_native_cad.agents.registry import RUNTIME_SKILL_REGISTRY


def compile_registered_skill_action_request(
    state: dict[str, Any], skill_manifest: dict[str, Any]
) -> dict[str, Any]:
    skill_id = skill_manifest.get("skill_id")
    if not isinstance(skill_id, str):
        raise ValueError("design action request requires a registered skill id")
    skill = RUNTIME_SKILL_REGISTRY.skill(skill_id)
    if skill_manifest.get("version") != skill.version:
        raise ValueError("design action request does not match the registry skill")
    safe_state = sanitize_provider_payload(state)
    safe_manifest = {
        "skill_id": skill.skill_id,
        "version": skill.version,
        "allowed_actions": sorted(skill.allowed_actions),
        "allowed_context_keys": sorted(skill.allowed_context_keys),
        "allowed_tools": sorted(skill.allowed_tools),
        "output_contract_types": sorted(skill.output_contract_types),
        "stop_reasons": sorted(skill.stop_reasons),
        "delegated_skills": [
            {
                "skill_id": delegated.skill_id,
                "version": delegated.version,
                "allowed_actions": sorted(delegated.allowed_actions),
                "allowed_tools": sorted(delegated.allowed_tools),
                "output_contract_types": sorted(delegated.output_contract_types),
                "prohibited_side_effects": list(delegated.prohibited_side_effects),
            }
            for delegated in (
                RUNTIME_SKILL_REGISTRY.skill(item)
                for item in skill.delegated_skill_ids
            )
        ],
        "knowledge": [
            {
                "id": item.knowledge_id,
                "scope": item.scope,
                "source": item.source,
                "content": item.load_content(),
            }
            for item in RUNTIME_SKILL_REGISTRY.knowledge_for_skill(skill.skill_id)
        ],
    }
    return {
        "operation": f"{skill.skill_id}_action",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": skill.compile_system_prompt()},
            {"role": "system", "content": skill.compile_action_contract()},
            {"role": "system", "content": "Registered capability: " + json.dumps(safe_manifest, sort_keys=True)},
            {"role": "user", "content": json.dumps(safe_state, sort_keys=True)},
        ],
        "skill": safe_manifest,
        "state": safe_state,
        "payload_shape": {
            "kind": "agent_episode_state",
            "top_level_keys": sorted(str(key) for key in safe_state if isinstance(key, str)),
        },
    }


__all__ = ["compile_registered_skill_action_request"]
