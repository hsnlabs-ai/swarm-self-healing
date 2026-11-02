"""Tests for HomeostasisController: sub-5s hot failover, preventive cooldown, and empty standby pool handling."""

import time

import pytest

from swarm_self_healing import (
    AgentSurvivalProfile,
    HomeostasisController,
    ScoutProvisionerPort,
    ScoutState,
    StandbyPoolExhaustedError,
    SwarmLedgerPort,
)


class InMemorySwarmLedger(SwarmLedgerPort):
    """In-memory implementation of SwarmLedgerPort for deterministic unit testing."""

    def __init__(self, scouts: list[AgentSurvivalProfile] | None = None) -> None:
        self.scouts: dict[str, AgentSurvivalProfile] = {
            s.scout_id: s for s in (scouts or [])
        }
        self.mission_assignments: dict[str, str] = {}
        self.transition_history: list[tuple[str, ScoutState, str]] = []

    async def get_scouts_by_state(
        self, states: list[ScoutState]
    ) -> list[AgentSurvivalProfile]:
        target_set = set(states)
        return [s for s in self.scouts.values() if s.state in target_set]

    async def transition_scout_state(
        self, scout_id: str, new_state: ScoutState, reason: str
    ) -> None:
        profile = self.scouts[scout_id]
        profile.state = new_state
        self.transition_history.append((scout_id, new_state, reason))

    async def promote_standby_for_mission(
        self, mission_id: str
    ) -> AgentSurvivalProfile | None:
        standby_candidates = sorted(
            (s for s in self.scouts.values() if s.state == ScoutState.STANDBY_READY),
            key=lambda s: (s.heat_score, s.created_at),
        )
        if not standby_candidates:
            return None
        chosen = standby_candidates[0]
        chosen.state = ScoutState.ACTIVE_EXTERNAL
        self.mission_assignments[mission_id] = chosen.scout_id
        self.transition_history.append(
            (chosen.scout_id, ScoutState.ACTIVE_EXTERNAL, f"Promoted for {mission_id}")
        )
        return chosen

    async def update_scout_heat(self, scout_id: str, heat_score: float) -> None:
        self.scouts[scout_id].heat_score = heat_score


class InMemoryScoutProvisioner(ScoutProvisionerPort):
    """In-memory implementation of ScoutProvisionerPort."""

    def __init__(self, ledger: InMemorySwarmLedger) -> None:
        self.ledger = ledger
        self.counter = 0

    async def provision_new_scout(self) -> AgentSurvivalProfile:
        self.counter += 1
        profile = AgentSurvivalProfile(
            scout_id=f"scout-new-{self.counter:02d}",
            state=ScoutState.SANDBOX_MATURING,
            heat_score=0.0,
            last_verified_ip=f"177.84.10.{self.counter + 10}",
            last_verified_asn="AS28573",
        )
        self.ledger.scouts[profile.scout_id] = profile
        return profile


@pytest.mark.asyncio
async def test_hot_failover_promotes_standby_in_under_5_seconds() -> None:
    """Verify atomic hot failover replaces a quarantined scout in < 5 seconds and replenishes deficit."""
    s_active = AgentSurvivalProfile(
        scout_id="scout-active-01",
        state=ScoutState.ACTIVE_EXTERNAL,
        heat_score=0.20,
    )
    s_standby = AgentSurvivalProfile(
        scout_id="scout-standby-02",
        state=ScoutState.STANDBY_READY,
        heat_score=0.05,
    )
    ledger = InMemorySwarmLedger([s_active, s_standby])
    ledger.mission_assignments["mission-alpha"] = "scout-active-01"
    provisioner = InMemoryScoutProvisioner(ledger)

    controller = HomeostasisController(
        ledger=ledger,
        provisioner=provisioner,
        target_population=3,
    )

    t0 = time.perf_counter()
    promoted = await controller.execute_hot_failover(
        "mission-alpha",
        failed_scout_id="scout-active-01",
        reason="Simulated HTTP 403 block on external surface",
        strict=True,
    )
    elapsed_s = time.perf_counter() - t0

    assert elapsed_s < 5.0
    assert promoted is not None
    assert promoted.scout_id == "scout-standby-02"
    assert promoted.state == ScoutState.ACTIVE_EXTERNAL
    assert ledger.scouts["scout-active-01"].state == ScoutState.QUARANTINED
    assert ledger.mission_assignments["mission-alpha"] == "scout-standby-02"


@pytest.mark.asyncio
async def test_run_tick_rotates_overheated_scout_promotes_reserve_and_incubates() -> None:
    """Verify run_tick cools overheated scouts (>= 0.70), promotes standby for their mission, and spawns replacements."""
    s_hot = AgentSurvivalProfile(
        scout_id="scout-hot-01",
        state=ScoutState.ACTIVE_EXTERNAL,
        heat_score=0.76,
    )
    s_reserve = AgentSurvivalProfile(
        scout_id="scout-reserve-02",
        state=ScoutState.STANDBY_READY,
        heat_score=0.04,
    )
    ledger = InMemorySwarmLedger([s_hot, s_reserve])
    ledger.mission_assignments["mission-audit-01"] = "scout-hot-01"
    provisioner = InMemoryScoutProvisioner(ledger)

    controller = HomeostasisController(
        ledger=ledger,
        provisioner=provisioner,
        target_population=4,
    )

    t0 = time.perf_counter()
    summary = await controller.run_tick(
        mission_assignments=dict(ledger.mission_assignments)
    )
    elapsed_s = time.perf_counter() - t0

    assert elapsed_s < 5.0
    assert summary.tick_number == 1
    assert summary.preventively_cooled == 1
    assert summary.promoted_from_standby == 1
    assert summary.newly_incubated == 2
    assert ledger.scouts["scout-hot-01"].state == ScoutState.SANDBOX_MATURING
    assert ledger.scouts["scout-reserve-02"].state == ScoutState.ACTIVE_EXTERNAL
    assert ledger.mission_assignments["mission-audit-01"] == "scout-reserve-02"


@pytest.mark.asyncio
async def test_hot_failover_strict_raises_when_standby_pool_exhausted() -> None:
    """Verify StandbyPoolExhaustedError is raised in strict mode when no STANDBY_READY agents exist."""
    s_active = AgentSurvivalProfile(
        scout_id="scout-only-01",
        state=ScoutState.ACTIVE_EXTERNAL,
        heat_score=0.10,
    )
    ledger = InMemorySwarmLedger([s_active])
    controller = HomeostasisController(ledger=ledger, target_population=2)

    with pytest.raises(StandbyPoolExhaustedError):
        await controller.execute_hot_failover(
            "mission-orphan",
            failed_scout_id="scout-only-01",
            strict=True,
        )
