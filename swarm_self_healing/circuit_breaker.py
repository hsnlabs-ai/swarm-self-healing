"""Resource Circuit Breaker with anti-storm alert deduplication and explicit unlock."""

import inspect
from collections.abc import Awaitable, Callable

from swarm_self_healing.exceptions import (
    CircuitBreakerTrippedError,
    GenAIQuotaExceededError,
    ProxyBandwidthExceededError,
    SmsBalanceExhaustedError,
)
from swarm_self_healing.models import CircuitBreakerState

AlertCallback = Callable[[CircuitBreakerState, str], Awaitable[None] | None]


class ResourceCircuitBreaker:
    """Protects external SMS OTP, residential proxy, and LLM quotas against provisioning storms.

    - Starts in CLOSED state.
    - Transitions to OPEN_* upon resource exhaustion or manual panic.
    - Blocks provisioning while OPEN_* and emits at most one alert per state until unlock().
    - Resets to CLOSED only via explicit unlock().
    """

    def __init__(
        self,
        initial_state: CircuitBreakerState = CircuitBreakerState.CLOSED,
        on_trip_alert: AlertCallback | None = None,
    ) -> None:
        self._state: CircuitBreakerState = initial_state
        self._last_reason: str = ""
        self._alerted_states: set[CircuitBreakerState] = set()
        self._alert_count: int = 0
        self._on_trip_alert = on_trip_alert

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        return self._state

    @property
    def last_reason(self) -> str:
        """Reason recorded when the circuit breaker was last tripped."""
        return self._last_reason

    @property
    def is_closed(self) -> bool:
        """Return True if the circuit breaker is CLOSED and allows provisioning."""
        return self._state == CircuitBreakerState.CLOSED

    @property
    def is_open(self) -> bool:
        """Return True if the circuit breaker is in any OPEN_* state."""
        return self._state != CircuitBreakerState.CLOSED

    @property
    def alert_count(self) -> int:
        """Total number of unique trip alerts emitted since initialization or last unlock."""
        return self._alert_count

    def check_before_provision(self) -> None:
        """Raise CircuitBreakerTrippedError if the breaker is not CLOSED."""
        if not self.is_closed:
            raise CircuitBreakerTrippedError(
                breaker_state=self._state,
                reason=self._last_reason or f"Circuit breaker is open ({self._state.value}).",
            )

    async def trip(
        self,
        new_state: CircuitBreakerState,
        reason: str = "",
    ) -> bool:
        """Trip the circuit breaker to new_state and emit a single alert without storms.

        Returns True if a new alert was emitted for this state, or False if suppressed.
        """
        if new_state == CircuitBreakerState.CLOSED:
            self.unlock()
            return False

        self._state = new_state
        self._last_reason = reason
        if new_state not in self._alerted_states:
            self._alerted_states.add(new_state)
            self._alert_count += 1
            if self._on_trip_alert is not None:
                res = self._on_trip_alert(new_state, reason)
                if inspect.isawaitable(res):
                    await res
            return True
        return False

    def trip_sync(
        self,
        new_state: CircuitBreakerState,
        reason: str = "",
    ) -> bool:
        """Synchronously trip the circuit breaker and return True if this is the first alert."""
        if new_state == CircuitBreakerState.CLOSED:
            self.unlock()
            return False

        self._state = new_state
        self._last_reason = reason
        if new_state not in self._alerted_states:
            self._alerted_states.add(new_state)
            self._alert_count += 1
            if self._on_trip_alert is not None:
                res = self._on_trip_alert(new_state, reason)
                if inspect.isawaitable(res):
                    # Close coroutine if called synchronously to avoid RuntimeWarning
                    res.close()  # type: ignore[union-attr]
            return True
        return False

    @staticmethod
    def map_exception_to_state(exc: BaseException) -> CircuitBreakerState | None:
        """Map a resource exhaustion exception to its canonical CircuitBreakerState."""
        if isinstance(exc, SmsBalanceExhaustedError) or exc.__class__.__name__ == "SmsBalanceExhaustedError":
            return CircuitBreakerState.OPEN_SMS_EXHAUSTED
        if isinstance(exc, ProxyBandwidthExceededError) or exc.__class__.__name__ == "ProxyBandwidthExceededError":
            return CircuitBreakerState.OPEN_PROXY_EXHAUSTED
        if isinstance(exc, GenAIQuotaExceededError) or exc.__class__.__name__ == "GenAIQuotaExceededError":
            return CircuitBreakerState.OPEN_LLM_QUOTA
        return None

    async def trip_from_exception(
        self, exc: BaseException
    ) -> tuple[CircuitBreakerState, bool]:
        """Map an exception to a CircuitBreakerState, trip the breaker, and return (state, first_alert)."""
        mapped = self.map_exception_to_state(exc)
        if mapped is None:
            raise exc
        first_alert = await self.trip(mapped, reason=str(exc))
        return mapped, first_alert

    def unlock(self) -> CircuitBreakerState:
        """Reset the circuit breaker to CLOSED and clear anti-storm alert latches."""
        self._state = CircuitBreakerState.CLOSED
        self._last_reason = ""
        self._alerted_states.clear()
        self._alert_count = 0
        return self._state
