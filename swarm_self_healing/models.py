"""Domain data models and enums for the Swarm Self-Healing library."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _extract_ipv4_subnet_24(ip_addr: str) -> str:
    """Return the /24 prefix ('a.b.c') of an IPv4 address, or empty string if invalid."""
    parts = ip_addr.strip().split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return ".".join(parts[:3])
    return ""


class ScoutState(str, Enum):
    """Canonical lifecycle states of an autonomous Scout agent."""

    INCUBATING = "INCUBATING"
    STANDBY_READY = "STANDBY_READY"
    SANDBOX_MATURING = "SANDBOX_MATURING"
    ACTIVE_EXTERNAL = "ACTIVE_EXTERNAL"
    QUARANTINED = "QUARANTINED"
    RETIRED = "RETIRED"


class CircuitBreakerState(str, Enum):
    """Resource Circuit Breaker states safeguarding external quotas."""

    CLOSED = "CLOSED"
    OPEN_SMS_EXHAUSTED = "OPEN_SMS_EXHAUSTED"
    OPEN_PROXY_EXHAUSTED = "OPEN_PROXY_EXHAUSTED"
    OPEN_LLM_QUOTA = "OPEN_LLM_QUOTA"
    OPEN_MANUAL_PANIC = "OPEN_MANUAL_PANIC"


class AffinityVerificationResult(str, Enum):
    """Three-tier outcome of residential proxy IP/ASN affinity verification."""

    EXACT_MATCH = "EXACT_MATCH"
    DHCP_SUBNET_RENEWED = "DHCP_SUBNET_RENEWED"
    AFFINITY_MISMATCH = "AFFINITY_MISMATCH"


class NetworkFingerprint(BaseModel):
    """Immutable network identity fingerprint with IPv4 /24 prefix and ASN."""

    model_config = ConfigDict(frozen=True, validate_assignment=True)

    ip_address: str
    asn: str  # ex: "AS28573"
    subnet_24: str = ""  # ex: "198.51.100"

    @model_validator(mode="before")
    @classmethod
    def _populate_subnet_24(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ip_val = str(data.get("ip_address") or "")
            subnet_val = str(data.get("subnet_24") or "").strip()
            if not subnet_val and ip_val:
                data = dict(data)
                data["subnet_24"] = _extract_ipv4_subnet_24(ip_val)
        return data


class AgentSurvivalProfile(BaseModel):
    """Runtime survival state and metabolic telemetry of a Scout agent."""

    model_config = ConfigDict(validate_assignment=True)

    scout_id: str
    state: ScoutState
    heat_score: float = Field(default=0.0, ge=0.0, le=1.0)
    last_verified_ip: str | None = None
    last_verified_asn: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_interaction_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HomeostasisTickSummary(BaseModel):
    """Summary of actions taken during a single deterministic homeostasis tick."""

    tick_number: int
    promoted_from_standby: int = 0
    preventively_cooled: int = 0
    newly_incubated: int = 0
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    promoted_scout_ids: list[str] = Field(default_factory=list)
    cooled_scout_ids: list[str] = Field(default_factory=list)
