"""Tests for HeatPolicy: discrete deltas, [0.0, 1.0] saturation clamping, and thermal hysteresis."""

import pytest

from swarm_self_healing import HeatPolicy, ScoutState


def test_heat_policy_discrete_deltas() -> None:
    """Verify the four canonical discrete heat deltas (+0.14, +0.06, -0.05, -0.15)."""
    policy = HeatPolicy()
    heat = 0.0

    # External burst (+0.14)
    heat = policy.record_external_burst(heat)
    assert heat == pytest.approx(0.14)

    # External regular (+0.06)
    heat = policy.record_external_regular(heat)
    assert heat == pytest.approx(0.20)

    # Sandbox cooldown turn (-0.05)
    heat = policy.record_sandbox_cooldown(heat)
    assert heat == pytest.approx(0.15)

    # Full session rest (-0.15)
    heat = policy.record_session_rest(heat)
    assert heat == pytest.approx(0.0)


def test_heat_policy_saturation_bounds_zero_and_one() -> None:
    """Verify heat_score is strictly clamped within [0.0, 1.0] under extreme deltas."""
    policy = HeatPolicy()

    # Upper saturation at 1.0
    heat = 0.92
    heat = policy.record_external_burst(heat)
    assert heat == 1.0
    assert policy.apply_delta(0.95, 0.50) == 1.0

    # Lower saturation at 0.0
    low_heat = 0.08
    low_heat = policy.record_session_rest(low_heat)
    assert low_heat == 0.0
    assert policy.apply_delta(0.02, -0.40) == 0.0


def test_heat_policy_hysteresis_transitions() -> None:
    """Verify preventive rotation at >= 0.70 and standby graduation at <= 0.15 with hysteresis band."""
    policy = HeatPolicy(cooldown_threshold=0.70, standby_ready_threshold=0.15)

    # Active external scout below 0.70 remains ACTIVE_EXTERNAL
    assert not policy.requires_preventive_cooldown(0.69)
    assert (
        policy.evaluate_next_state(ScoutState.ACTIVE_EXTERNAL, 0.69)
        == ScoutState.ACTIVE_EXTERNAL
    )

    # Reaching 0.70 triggers rotation to SANDBOX_MATURING
    assert policy.requires_preventive_cooldown(0.70)
    assert (
        policy.evaluate_next_state(ScoutState.ACTIVE_EXTERNAL, 0.70)
        == ScoutState.SANDBOX_MATURING
    )

    # In SANDBOX_MATURING, intermediate heat (e.g. 0.40 or 0.16) stays in SANDBOX_MATURING (hysteresis)
    assert not policy.can_graduate_to_standby(0.40)
    assert (
        policy.evaluate_next_state(ScoutState.SANDBOX_MATURING, 0.40)
        == ScoutState.SANDBOX_MATURING
    )
    assert (
        policy.evaluate_next_state(ScoutState.SANDBOX_MATURING, 0.16)
        == ScoutState.SANDBOX_MATURING
    )

    # Cooling down to <= 0.15 unlocks graduation to STANDBY_READY
    assert policy.can_graduate_to_standby(0.15)
    assert (
        policy.evaluate_next_state(ScoutState.SANDBOX_MATURING, 0.15)
        == ScoutState.STANDBY_READY
    )
