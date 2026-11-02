"""Swarm Self-Healing: Deterministic homeostasis, sub-5s hot failover, preventive heat cooldown, and resource circuit breakers."""

from swarm_self_healing.circuit_breaker import ResourceCircuitBreaker
from swarm_self_healing.controller import HomeostasisController
from swarm_self_healing.exceptions import (
    CircuitBreakerTrippedError,
    GenAIQuotaExceededError,
    ProxyAffinityMismatchError,
    ProxyBandwidthExceededError,
    SmsBalanceExhaustedError,
    StandbyPoolExhaustedError,
    SwarmSelfHealingError,
)
from swarm_self_healing.models import (
    AffinityVerificationResult,
    AgentSurvivalProfile,
    CircuitBreakerState,
    HomeostasisTickSummary,
    NetworkFingerprint,
    ScoutState,
)
from swarm_self_healing.policies import HeatPolicy, NetworkAffinityGuard
from swarm_self_healing.protocols import ScoutProvisionerPort, SwarmLedgerPort

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AffinityVerificationResult",
    "AgentSurvivalProfile",
    "CircuitBreakerState",
    "CircuitBreakerTrippedError",
    "GenAIQuotaExceededError",
    "HeatPolicy",
    "HomeostasisController",
    "HomeostasisTickSummary",
    "NetworkAffinityGuard",
    "NetworkFingerprint",
    "ProxyAffinityMismatchError",
    "ProxyBandwidthExceededError",
    "ResourceCircuitBreaker",
    "ScoutProvisionerPort",
    "ScoutState",
    "SmsBalanceExhaustedError",
    "StandbyPoolExhaustedError",
    "SwarmLedgerPort",
    "SwarmSelfHealingError",
]
