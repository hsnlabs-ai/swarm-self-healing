"""Hexagonal Architecture Ports (Protocols) for Swarm Self-Healing."""

from typing import Protocol, runtime_checkable

from swarm_self_healing.models import AgentSurvivalProfile, ScoutState


@runtime_checkable
class SwarmLedgerPort(Protocol):
    """Port interface for reading and mutating swarm agent states and mission promotions."""

    async def get_scouts_by_state(
        self, states: list[ScoutState]
    ) -> list[AgentSurvivalProfile]:
        """Return all scouts currently in any of the specified lifecycle states."""
        ...

    async def transition_scout_state(
        self, scout_id: str, new_state: ScoutState, reason: str
    ) -> None:
        """Atomically transition a scout to a new lifecycle state."""
        ...

    async def promote_standby_for_mission(
        self, mission_id: str
    ) -> AgentSurvivalProfile | None:
        """Atomically select and promote the healthiest STANDBY_READY scout to take over mission_id."""
        ...

    async def update_scout_heat(self, scout_id: str, heat_score: float) -> None:
        """Persist the updated saturated heat_score [0.0, 1.0] for scout_id."""
        ...


@runtime_checkable
class ScoutProvisionerPort(Protocol):
    """Port interface for incubating and provisioning new agent identities."""

    async def provision_new_scout(self) -> AgentSurvivalProfile:
        """Provision a new scout identity and return its initial survival profile."""
        ...
