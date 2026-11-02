# Swarm Self-Healing (`v1.0.0`)

**Deterministic Homeostasis, Sub-5s Hot Failover & Anti-Ban Survival Engine for Autonomous Agent Swarms**  
Maintained by **hsnlabs** (`https://hsnlabs.ai`) · Released under the **MIT License**

- **Official Website (`hsnlabs.ai`):** [`https://hsnlabs.ai/en/products/swarm-self-healing/`](https://hsnlabs.ai/en/products/swarm-self-healing/) ([PT-BR](https://hsnlabs.ai/produtos/swarm-self-healing/))
- **Public GitHub Repository:** [`https://github.com/hsnlabs-ai/swarm-self-healing`](https://github.com/hsnlabs-ai/swarm-self-healing)
- **Technical Specification:** [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md)
- **Automated Test Suite:** [`tests/`](tests/)

---

## Why Swarm Self-Healing?

Unlike conventional multi-agent frameworks that treat agents as ephemeral, disposable processes, surface-auditing and conversational swarms operating on real channels (WhatsApp, Signal, RCS, Web Chat) depend on scarce, high-friction operational assets: E.164 identities, Double Ratchet cryptographic sessions, SMS OTP budgets, and sticky residential proxy reputations.

**Swarm Self-Healing** isolates the four core survival primitives of **Agents Swarm** into a pure, zero-network-coupling Python library operating over Hexagonal Architecture ports (`SwarmLedgerPort`, `ScoutProvisionerPort`):

1. **Sub-5s Deterministic Hot Failover (`HomeostasisController`):**
   Continuously reconciles active agent populations against target levels, atomically promoting warm `STANDBY_READY` reserves in `<5s` upon quarantine or preventive thermal rotation.
2. **Discrete Metabolic Exposure Cooldown (`HeatPolicy`):**
   Computes agent thermal stress using deterministic discrete deltas (`+0.14` burst, `+0.06` regular, `-0.05` sandbox cooldown, `-0.15` rest), mandatory `[0.0, 1.0]` saturation, and hysteresis (`>= 0.70` preventive rotation to `SANDBOX_MATURING`, `<= 0.15` graduation to `STANDBY_READY`).
3. **3-Tier Residential Proxy & DHCP `/24` Continuity (`NetworkAffinityGuard`):**
   Validates ASN consistency and regional IPv4 `/24` subnet pinning (`EXACT_MATCH`, `DHCP_SUBNET_RENEWED`, `AFFINITY_MISMATCH`), seamlessly accepting legitimate ISP DHCP renewals while blocking anomalous IP/ASN jumps before a single packet is sent.
4. **Anti-Storm Resource Circuit Breaker (`ResourceCircuitBreaker`):**
   Protects SMS OTP balances, residential proxy bandwidth, and LLM token quotas (`CLOSED`, `OPEN_SMS_EXHAUSTED`, `OPEN_PROXY_EXHAUSTED`, `OPEN_LLM_QUOTA`, `OPEN_MANUAL_PANIC`) by halting replenishment loops and deduplicating alerts until explicit operator `unlock()`.

---

## Installation

```bash
pip install swarm-self-healing
```

Or with `uv`:

```bash
uv add swarm-self-healing
```

---

## Quickstart

```python
import asyncio
from swarm_self_healing import (
    AgentSurvivalProfile,
    HeatPolicy,
    HomeostasisController,
    NetworkAffinityGuard,
    ResourceCircuitBreaker,
    ScoutState,
)


async def main() -> None:
    # 1. Metabolic Heat & Hysteresis Policy
    heat_policy = HeatPolicy(cooldown_threshold=0.70, standby_ready_threshold=0.15)
    heat = heat_policy.record_external_burst(0.60)  # -> 0.74 (clamped in [0.0, 1.0])
    assert heat_policy.requires_preventive_cooldown(heat) is True

    # 2. 3-Tier Residential Proxy & DHCP /24 Guard
    guard = NetworkAffinityGuard()
    scout = AgentSurvivalProfile(
        scout_id="scout-01",
        state=ScoutState.ACTIVE_EXTERNAL,
        last_verified_ip="177.55.120.14",
        last_verified_asn="AS28573",
    )
    # Legitimate ISP DHCP renewal within 177.55.120.0/24 on AS28573:
    result = guard.verify_and_update(
        scout,
        current_ip="177.55.120.209",
        current_asn="AS28573",
    )
    assert result.value == "DHCP_SUBNET_RENEWED"
    assert scout.last_verified_ip == "177.55.120.209"

    # 3. Anti-Storm Resource Circuit Breaker
    breaker = ResourceCircuitBreaker()
    assert breaker.is_closed is True


asyncio.run(main())
```

---

## Running the Test Suite

```bash
uv run pytest tests -v
```

---

## License

MIT © 2026 **hsnlabs** (`https://hsnlabs.ai`)
