"""Agent adapter contracts for CadFlow."""

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.deterministic import DeterministicAgentAdapter
from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter
from ai_native_cad.agents.json_contract import (
    JsonContractAgentAdapter,
    JsonContractClient,
    JsonContractProviderConfig,
    JsonContractProviderError,
)
from ai_native_cad.agents.provider_clients import (
    JsonProviderEndpoint,
    OpenAICompatibleJsonContractClient,
    OpenAIResponsesJsonContractClient,
    make_json_contract_adapter_from_env,
)
from ai_native_cad.agents.validation import validate_adapter_result

__all__ = [
    "AgentAdapter",
    "DesignPlannerFakeAgentAdapter",
    "DeterministicAgentAdapter",
    "JsonContractAgentAdapter",
    "JsonContractClient",
    "JsonContractProviderConfig",
    "JsonContractProviderError",
    "JsonProviderEndpoint",
    "OpenAICompatibleJsonContractClient",
    "OpenAIResponsesJsonContractClient",
    "make_json_contract_adapter_from_env",
    "validate_adapter_result",
]
