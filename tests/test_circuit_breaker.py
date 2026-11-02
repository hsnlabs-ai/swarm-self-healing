"""Tests for ResourceCircuitBreaker: anti-storm alert deduplication, provisioning block, and unlock()."""

import pytest

from swarm_self_healing import (
    AgentSurvivalProfile,
    CircuitBreakerState,
    CircuitBreakerTrippedError,
    HomeostasisController,
    ResourceCircuitBreaker,
    ScoutProvisionerPort,
    ScoutState,
    SmsBalanceExhaustedError,
    SwarmLedgerPort,
)


class DummyLedger(SwarmLedgerPort):
    def __init__(self) -> None:
        self.scouts: list[AgentSurvivalProfile] = []

    async def get_scouts_by_state(
        self, states: list[ScoutState]
    ) -> list[AgentSurvivalProfile]:
        return [s for s in self.scouts if s.state in set(states)]

    async def transition_scout_state(
        self, scout_id: str, new_state: ScoutState, reason: str
    ) -> None:
        for s in self.scouts:
            if s.scout_id == scout_id:
                s.state = new_state

    async def promote_standby_for_mission(
        self, mission_id: str
    ) -> AgentSurvivalProfile | None:
        return None

    async def update_scout_heat(self, scout_id: str, heat_score: float) -> None:
        pass


class QuotaLimitedProvisioner(ScoutProvisionerPort):
    def __init__(self, ledger: DummyLedger, sms_quota: int) -> None:
        self.ledger = ledger
        self.sms_quota = sms_quota
        self.calls = 0

    async def provision_new_scout(self) -> AgentSurvivalProfile:
        self.calls += 1
        if self.sms_quota <= 0:
            raise SmsBalanceExhaustedError("SMS OTP balance exhausted.")
        self.sms_quota -= 1
        scout = AgentSurvivalProfile(
            scout_id=f"scout-{self.calls:02d}",
            state=ScoutState.SANDBOX_MATURING,
        )
        self.ledger.scouts.append(scout)
        return scout


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_provisioning_storm_and_resumes_after_unlock() -> None:
    """Verify breaker trips once on SMS exhaustion, blocks subsequent ticks without storm, and resets via unlock()."""
    emitted_alerts: list[tuple[CircuitBreakerState, str]] = []

    async def on_alert(state: CircuitBreakerState, reason: str) -> None:
        emitted_alerts.append((state, reason))

    breaker = ResourceCircuitBreaker(on_trip_alert=on_alert)
    ledger = DummyLedger()
    provisioner = QuotaLimitedProvisioner(ledger=ledger, sms_quota=2)
    controller = HomeostasisController(
        ledger=ledger,
        provisioner=provisioner,
        target_population=5,
        circuit_breaker=breaker,
    )

    # Tick 1: provisions 2 scouts, fails on 3rd, trips OPEN_SMS_EXHAUSTED once
    tick1 = await controller.run_tick()
    assert tick1.newly_incubated == 2
    assert tick1.circuit_breaker_state == CircuitBreakerState.OPEN_SMS_EXHAUSTED
    assert breaker.is_open
    assert len(emitted_alerts) == 1
    assert provisioner.calls == 3

    # Ticks 2 & 3 while OPEN: zero calls to provisioner, zero duplicate alerts
    tick2 = await controller.run_tick()
    tick3 = await controller.run_tick()
    assert tick2.newly_incubated == 0
    assert tick3.newly_incubated == 0
    assert provisioner.calls == 3
    assert len(emitted_alerts) == 1

    # Direct check_before_provision raises CircuitBreakerTrippedError while OPEN
    with pytest.raises(CircuitBreakerTrippedError) as exc_info:
        breaker.check_before_provision()
    assert exc_info.value.breaker_state == CircuitBreakerState.OPEN_SMS_EXHAUSTED

    # Replenish quota and unlock breaker
    provisioner.sms_quota = 10
    new_state = breaker.unlock()
    assert new_state == CircuitBreakerState.CLOSED
    assert breaker.is_closed

    # Tick 4: provisions the remaining 3 scouts to reach target_population=5
    tick4 = await controller.run_tick()
    assert tick4.newly_incubated == 3
    assert tick4.circuit_breaker_state == CircuitBreakerState.CLOSED
    assert len(ledger.scouts) == 5
