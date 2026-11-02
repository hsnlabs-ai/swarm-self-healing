"""Pure domain policies for metabolic heat regulation and 3-tier residential proxy affinity."""

from swarm_self_healing.exceptions import ProxyAffinityMismatchError
from swarm_self_healing.models import (
    AffinityVerificationResult,
    AgentSurvivalProfile,
    NetworkFingerprint,
    ScoutState,
    _extract_ipv4_subnet_24,
)


class HeatPolicy:
    """Deterministic metabolic heat calculator with discrete deltas, [0.0, 1.0] saturation, and hysteresis.

    Discrete Deltas:
    - External burst turn: +0.14
    - External regular turn: +0.06
    - Sandbox cooldown turn: -0.05
    - Full session rest: -0.15

    Hysteresis Thresholds:
    - Preventive rotation trigger: heat_score >= 0.70 -> SANDBOX_MATURING
    - Standby readiness trigger: heat_score <= 0.15 -> STANDBY_READY
    """

    EXTERNAL_BURST_DELTA: float = 0.14
    EXTERNAL_REGULAR_DELTA: float = 0.06
    SANDBOX_COOLDOWN_DELTA: float = -0.05
    FULL_SESSION_REST_DELTA: float = -0.15

    def __init__(
        self,
        cooldown_threshold: float = 0.70,
        standby_ready_threshold: float = 0.15,
    ) -> None:
        if not (0.0 <= standby_ready_threshold < cooldown_threshold <= 1.0):
            raise ValueError(
                "Thresholds must satisfy 0.0 <= standby_ready_threshold < cooldown_threshold <= 1.0"
            )
        self.cooldown_threshold = cooldown_threshold
        self.standby_ready_threshold = standby_ready_threshold

    @staticmethod
    def clamp(value: float) -> float:
        """Clamp and round a heat score strictly within [0.0, 1.0]."""
        return min(1.0, max(0.0, round(float(value), 4)))

    def apply_delta(self, current_heat: float, delta: float) -> float:
        """Apply a discrete heat delta with mandatory saturation in [0.0, 1.0]."""
        return self.clamp(float(current_heat) + float(delta))

    def record_external_burst(self, current_heat: float) -> float:
        """Apply external burst turn delta (+0.14)."""
        return self.apply_delta(current_heat, self.EXTERNAL_BURST_DELTA)

    def record_external_regular(self, current_heat: float) -> float:
        """Apply regular external turn delta (+0.06)."""
        return self.apply_delta(current_heat, self.EXTERNAL_REGULAR_DELTA)

    def record_sandbox_cooldown(self, current_heat: float) -> float:
        """Apply sandbox cooldown turn delta (-0.05)."""
        return self.apply_delta(current_heat, self.SANDBOX_COOLDOWN_DELTA)

    def record_session_rest(self, current_heat: float) -> float:
        """Apply full session rest delta (-0.15)."""
        return self.apply_delta(current_heat, self.FULL_SESSION_REST_DELTA)

    def requires_preventive_cooldown(self, heat_score: float) -> bool:
        """Return True when heat_score reaches or exceeds the preventive rotation threshold (0.70)."""
        return round(float(heat_score), 4) >= self.cooldown_threshold

    def can_graduate_to_standby(self, heat_score: float) -> bool:
        """Return True when heat_score has cooled to or below the standby return threshold (0.15)."""
        return round(float(heat_score), 4) <= self.standby_ready_threshold

    def evaluate_next_state(
        self, current_state: ScoutState, heat_score: float
    ) -> ScoutState:
        """Evaluate state transition with thermal hysteresis between cooldown (0.70) and standby (0.15)."""
        if (
            current_state == ScoutState.ACTIVE_EXTERNAL
            and self.requires_preventive_cooldown(heat_score)
        ):
            return ScoutState.SANDBOX_MATURING
        if (
            current_state == ScoutState.SANDBOX_MATURING
            and self.can_graduate_to_standby(heat_score)
        ):
            return ScoutState.STANDBY_READY
        return current_state


class NetworkAffinityGuard:
    """Three-tier residential proxy network continuity guard (Exact -> DHCP /24 Renewal -> Mismatch)."""

    @staticmethod
    def extract_subnet_24(ip_address: str) -> str:
        """Extract the first three octets ('a.b.c') of a valid IPv4 address."""
        return _extract_ipv4_subnet_24(ip_address)

    def verify(
        self,
        expected_ip: str,
        expected_asn: str,
        current_ip: str,
        current_asn: str,
        *,
        scout_id: str = "scout",
        raise_on_mismatch: bool = True,
    ) -> AffinityVerificationResult:
        """Verify network continuity across 3 tiers:

        - Tier 1 (EXACT_MATCH): Same IP and same ASN.
        - Tier 2 (DHCP_SUBNET_RENEWED): Same ASN and same /24 IPv4 prefix.
        - Tier 3 (AFFINITY_MISMATCH): ASN change or /24 prefix change -> raises ProxyAffinityMismatchError.
        """
        exp_ip = expected_ip.strip()
        exp_asn = expected_asn.strip()
        cur_ip = current_ip.strip()
        cur_asn = current_asn.strip()

        # Tier 1: Exact IP & ASN match
        if cur_ip == exp_ip and cur_asn == exp_asn:
            return AffinityVerificationResult.EXACT_MATCH

        # Tier 2: Legitimate residential ISP DHCP renewal in the same ASN and /24 subnet
        exp_24 = self.extract_subnet_24(exp_ip)
        cur_24 = self.extract_subnet_24(cur_ip)
        if cur_asn == exp_asn and exp_24 and exp_24 == cur_24:
            return AffinityVerificationResult.DHCP_SUBNET_RENEWED

        # Tier 3: ASN mismatch or /24 subnet jump
        if raise_on_mismatch:
            raise ProxyAffinityMismatchError(
                f"Proxy affinity mismatch for {scout_id}: "
                f"expected ({exp_ip}, {exp_asn}), got ({cur_ip}, {cur_asn})"
            )
        return AffinityVerificationResult.AFFINITY_MISMATCH

    def verify_fingerprints(
        self,
        expected: NetworkFingerprint,
        current: NetworkFingerprint,
        *,
        scout_id: str = "scout",
        raise_on_mismatch: bool = True,
    ) -> AffinityVerificationResult:
        """Verify two NetworkFingerprint instances using 3-tier affinity rules."""
        return self.verify(
            expected_ip=expected.ip_address,
            expected_asn=expected.asn,
            current_ip=current.ip_address,
            current_asn=current.asn,
            scout_id=scout_id,
            raise_on_mismatch=raise_on_mismatch,
        )

    def verify_and_update_profile(
        self,
        profile: AgentSurvivalProfile,
        current_ip: str,
        current_asn: str,
    ) -> AffinityVerificationResult:
        """Verify network affinity for an AgentSurvivalProfile and update last_verified_ip on DHCP renewal."""
        if not profile.last_verified_ip or not profile.last_verified_asn:
            profile.last_verified_ip = current_ip.strip()
            profile.last_verified_asn = current_asn.strip()
            return AffinityVerificationResult.EXACT_MATCH

        result = self.verify(
            expected_ip=profile.last_verified_ip,
            expected_asn=profile.last_verified_asn,
            current_ip=current_ip,
            current_asn=current_asn,
            scout_id=profile.scout_id,
            raise_on_mismatch=True,
        )
        if result == AffinityVerificationResult.DHCP_SUBNET_RENEWED:
            profile.last_verified_ip = current_ip.strip()
        return result
