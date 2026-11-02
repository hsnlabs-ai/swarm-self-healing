"""Asynchronous HomeostasisController for sub-5s hot failover, preventive cooldown, and population replenishment."""

import asyncio

from swarm_self_healing.circuit_breaker import ResourceCircuitBreaker
from swarm_self_healing.exceptions import (
    CircuitBreakerTrippedError,
    GenAIQuotaExceededError,
    ProxyBandwidthExceededError,
    SmsBalanceExhaustedError,
    StandbyPoolExhaustedError,
)
from swarm_self_healing.models import (
    AgentSurvivalProfile,
    CircuitBreakerState,
    HomeostasisTickSummary,
    ScoutState,
)
from swarm_self_healing.policies import HeatPolicy
from swarm_self_healing.protocols import ScoutProvisionerPort, SwarmLedgerPort


class HomeostasisController:
    """Pure asynchronous homeostasis controller operating over SwarmLedgerPort and ScoutProvisionerPort.

    Tick Loop Responsibilities:
    1. Identify ACTIVE_EXTERNAL scouts with heat_score >= cooldown_threshold (0.70) and rotate them
       preventively to SANDBOX_MATURING.
    2. For each mission requiring failover (quarantined or preventively cooled scout), atomically
       promote a STANDBY_READY reserve scout in under 5 seconds.
    3. If the healthy population (STANDBY_READY + SANDBOX_MATURING + ACTIVE_EXTERNAL) is below
       target_population and the ResourceCircuitBreaker is CLOSED, provision new scouts via
       ScoutProvisionerPort while catching quota exhaustion errors to trip the breaker without storms.
    """

    def __init__(
        self,
        ledger: SwarmLedgerPort,
        provisioner: ScoutProvisionerPort | None = None,
        *,
        target_population: int = 5,
        heat_policy: HeatPolicy | None = None,
        circuit_breaker: ResourceCircuitBreaker | None = None,
        failover_timeout_s: float = 5.0,
    ) -> None:
        self.ledger = ledger
        self.provisioner = provisioner
        self.target_population = max(1, int(target_population))
        self.heat_policy = heat_policy or HeatPolicy()
        self.circuit_breaker = circuit_breaker or ResourceCircuitBreaker()
        self.failover_timeout_s = failover_timeout_s
        self._tick_counter = 0

    @property
    def tick_counter(self) -> int:
        """Total number of homeostasis ticks executed."""
        return self._tick_counter

    async def execute_hot_failover(
        self,
        mission_id: str,
        *,
        failed_scout_id: str | None = None,
        reason: str = "Immediate homeostatic failover (<5s)",
        strict: bool = False,
    ) -> AgentSurvivalProfile | None:
        """Execute atomic sub-5s hot failover for mission_id from the STANDBY_READY reserve pool."""
        if failed_scout_id is not None:
            await self.ledger.transition_scout_state(
                scout_id=failed_scout_id,
                new_state=ScoutState.QUARANTINED,
                reason=reason,
            )

        replacement = await asyncio.wait_for(
            self.ledger.promote_standby_for_mission(mission_id),
            timeout=self.failover_timeout_s,
        )
        if replacement is None and strict:
            raise StandbyPoolExhaustedError(
                f"No STANDBY_READY scout available in reserve pool to take over mission '{mission_id}'."
            )
        return replacement

    async def run_tick(
        self,
        *,
        missions_needing_failover: list[str] | None = None,
        mission_assignments: dict[str, str] | None = None,
        target_override: int | None = None,
        strict_failover: bool = False,
    ) -> HomeostasisTickSummary:
        """Execute one deterministic homeostasis cycle:

        1. Rotate overheated ACTIVE_EXTERNAL scouts (heat_score >= 0.70) to SANDBOX_MATURING.
        2. Promote STANDBY_READY replacements (<5s) for affected or explicitly listed missions.
        3. Replenish population deficit via ScoutProvisionerPort if ResourceCircuitBreaker is CLOSED.
        """
        self._tick_counter += 1
        effective_target = (
            max(1, int(target_override))
            if target_override is not None
            else self.target_population
        )

        # 1. Preventive Cooldown Rotation for overheated ACTIVE_EXTERNAL scouts
        active_scouts = await self.ledger.get_scouts_by_state(
            [ScoutState.ACTIVE_EXTERNAL]
        )
        cooled_ids: list[str] = []
        for scout in active_scouts:
            if self.heat_policy.requires_preventive_cooldown(scout.heat_score):
                await self.ledger.transition_scout_state(
                    scout_id=scout.scout_id,
                    new_state=ScoutState.SANDBOX_MATURING,
                    reason=(
                        f"Preventive metabolic cooldown: heat_score={scout.heat_score:.2f} >= "
                        f"{self.heat_policy.cooldown_threshold:.2f}"
                    ),
                )
                cooled_ids.append(scout.scout_id)

        # 2. Determine missions requiring immediate standby promotion (<5s)
        failover_missions: list[str] = []
        if missions_needing_failover:
            for m_id in missions_needing_failover:
                if m_id not in failover_missions:
                    failover_missions.append(m_id)

        if mission_assignments:
            quarantined_scouts = await self.ledger.get_scouts_by_state(
                [ScoutState.QUARANTINED]
            )
            unavailable_ids = {s.scout_id for s in quarantined_scouts} | set(cooled_ids)
            for m_id, assigned_scout_id in mission_assignments.items():
                if assigned_scout_id in unavailable_ids and m_id not in failover_missions:
                    failover_missions.append(m_id)

        promoted_ids: list[str] = []
        for mission_id in failover_missions:
            promoted = await self.execute_hot_failover(
                mission_id,
                strict=strict_failover,
            )
            if promoted is not None:
                promoted_ids.append(promoted.scout_id)

        # 3. Population deficit check & circuit-breaker-guarded incubation
        healthy_scouts = await self.ledger.get_scouts_by_state(
            [
                ScoutState.STANDBY_READY,
                ScoutState.SANDBOX_MATURING,
                ScoutState.ACTIVE_EXTERNAL,
            ]
        )
        deficit = max(0, effective_target - len(healthy_scouts))
        incubated_count = 0

        if (
            deficit > 0
            and self.circuit_breaker.is_closed
            and self.provisioner is not None
        ):
            for _ in range(deficit):
                try:
                    self.circuit_breaker.check_before_provision()
                    await self.provisioner.provision_new_scout()
                    incubated_count += 1
                except CircuitBreakerTrippedError:
                    break
                except (
                    SmsBalanceExhaustedError,
                    ProxyBandwidthExceededError,
                    GenAIQuotaExceededError,
                ) as exc:
                    await self.circuit_breaker.trip_from_exception(exc)
                    break
                except Exception as exc:
                    mapped = self.circuit_breaker.map_exception_to_state(exc)
                    if mapped is not None:
                        await self.circuit_breaker.trip(mapped, reason=str(exc))
                        break
                    raise

        return HomeostasisTickSummary(
            tick_number=self._tick_counter,
            promoted_from_standby=len(promoted_ids),
            preventively_cooled=len(cooled_ids),
            newly_incubated=incubated_count,
            circuit_breaker_state=self.circuit_breaker.state,
            promoted_scout_ids=promoted_ids,
            cooled_scout_ids=cooled_ids,
        )
