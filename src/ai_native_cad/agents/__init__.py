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
from ai_native_cad.agents.episode import (
    ALLOWLISTED_ACTIONS,
    CONTEXT_KEYS,
    AgentAction,
    AgentCapabilities,
    AgentEpisodeResult,
    AgentObjective,
    ContextBroker,
    ContextEnvelope,
    EpisodeBudget,
    EpisodeOrchestrator,
    StopReason,
    build_create_part_ir_context,
    run_create_part_ir_episode,
)

__all__ = [
    "AgentAdapter",
    "AgentAction",
    "AgentCapabilities",
    "AgentEpisodeResult",
    "AgentObjective",
    "ALLOWLISTED_ACTIONS",
    "CONTEXT_KEYS",
    "ContextBroker",
    "ContextEnvelope",
    "DesignPlannerFakeAgentAdapter",
    "DeterministicAgentAdapter",
    "EpisodeBudget",
    "EpisodeOrchestrator",
    "JsonContractAgentAdapter",
    "JsonContractClient",
    "JsonContractProviderConfig",
    "JsonContractProviderError",
    "JsonProviderEndpoint",
    "OpenAICompatibleJsonContractClient",
    "OpenAIResponsesJsonContractClient",
    "StopReason",
    "build_create_part_ir_context",
    "make_json_contract_adapter_from_env",
    "run_create_part_ir_episode",
    "validate_adapter_result",
]
