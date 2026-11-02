"""Tests for NetworkAffinityGuard: 3-tier validation (Exact, DHCP /24 renewal, and ASN/subnet mismatch)."""

import pytest

from swarm_self_healing import (
    AffinityVerificationResult,
    AgentSurvivalProfile,
    NetworkAffinityGuard,
    NetworkFingerprint,
    ProxyAffinityMismatchError,
    ScoutState,
)


def test_tier_1_exact_ip_and_asn_match() -> None:
    """Tier 1: Identical IP and ASN returns EXACT_MATCH without modifying profile."""
    guard = NetworkAffinityGuard()
    fp_expected = NetworkFingerprint(ip_address="177.84.120.15", asn="AS28573")
    fp_current = NetworkFingerprint(ip_address="177.84.120.15", asn="AS28573")

    assert fp_expected.subnet_24 == "177.84.120"
    result = guard.verify_fingerprints(fp_expected, fp_current, scout_id="scout-01")
    assert result == AffinityVerificationResult.EXACT_MATCH


def test_tier_2_dhcp_subnet_24_renewal_updates_profile_ip() -> None:
    """Tier 2: Same ASN and same /24 prefix accepts DHCP rotation and updates last_verified_ip."""
    guard = NetworkAffinityGuard()
    profile = AgentSurvivalProfile(
        scout_id="scout-dhcp-01",
        state=ScoutState.ACTIVE_EXTERNAL,
        last_verified_ip="177.84.120.15",
        last_verified_asn="AS28573",
    )

    result = guard.verify_and_update_profile(
        profile,
        current_ip="177.84.120.242",
        current_asn="AS28573",
    )
    assert result == AffinityVerificationResult.DHCP_SUBNET_RENEWED
    assert profile.last_verified_ip == "177.84.120.242"
    assert profile.last_verified_asn == "AS28573"


def test_tier_3_asn_or_subnet_mismatch_raises_error() -> None:
    """Tier 3: Different /24 subnet or different ASN raises ProxyAffinityMismatchError."""
    guard = NetworkAffinityGuard()

    # Different /24 subnet under the same ASN
    with pytest.raises(ProxyAffinityMismatchError):
        guard.verify(
            expected_ip="177.84.120.15",
            expected_asn="AS28573",
            current_ip="177.84.121.15",
            current_asn="AS28573",
            scout_id="scout-01",
        )

    # Same IP /24 prefix but different ASN
    with pytest.raises(ProxyAffinityMismatchError):
        guard.verify(
            expected_ip="177.84.120.15",
            expected_asn="AS28573",
            current_ip="177.84.120.15",
            current_asn="AS64496",
            scout_id="scout-01",
        )

    # Non-raising mode returns AFFINITY_MISMATCH enum
    res = guard.verify(
        expected_ip="177.84.120.15",
        expected_asn="AS28573",
        current_ip="203.0.113.5",
        current_asn="AS64496",
        raise_on_mismatch=False,
    )
    assert res == AffinityVerificationResult.AFFINITY_MISMATCH
