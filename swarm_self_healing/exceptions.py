"""Typed survival and resource exhaustion exceptions for Swarm Self-Healing."""

from swarm_self_healing.models import CircuitBreakerState


class SwarmSelfHealingError(Exception):
    """Base exception for all swarm self-healing and homeostasis errors."""


class StandbyPoolExhaustedError(SwarmSelfHealingError):
    """Raised when no STANDBY_READY agents are available to execute hot failover."""


class CircuitBreakerTrippedError(SwarmSelfHealingError):
    """Raised when attempting to provision agents while the ResourceCircuitBreaker is OPEN."""

    def __init__(
        self,
        breaker_state: CircuitBreakerState = CircuitBreakerState.OPEN_MANUAL_PANIC,
        reason: str = "Resource circuit breaker is currently open.",
    ) -> None:
        self.breaker_state = breaker_state
        self.reason = reason
        super().__init__(f"[{breaker_state.value}] {reason}")


class ProxyAffinityMismatchError(SwarmSelfHealingError):
    """Raised when the current egress IP (/24 subnet) or ASN does not match the bound identity."""


class SmsBalanceExhaustedError(SwarmSelfHealingError):
    """Raised when the SMS OTP provider rejects activation due to insufficient balance."""


class ProxyBandwidthExceededError(SwarmSelfHealingError):
    """Raised when the residential proxy provider quota or bandwidth is exhausted."""


class GenAIQuotaExceededError(SwarmSelfHealingError):
    """Raised when foundational LLM / GenAI quota or billing limit is reached."""
