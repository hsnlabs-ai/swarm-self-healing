# Swarm Self-Healing — Formal Architecture Specification

* **Author:** Hugo S. Nascimento (`@hugosnascimento`) — Founder & CPTO, hsnlabs
* **Status:** Production / Stable (`v1.0.0`)
* **Package:** `swarm-self-healing`
* **License:** MIT

---

## 1. Overview

**Swarm Self-Healing** (`swarm-self-healing`) is a standalone Python library maintained by **hsnlabs** that isolates deterministic self-healing, population homeostasis, preventive metabolic heat rotation, 3-tier residential proxy affinity guards, and anti-storm resource circuit breakers for long-horizon autonomous agent swarms.

Unlike conventional agent frameworks that treat agents as stateless, disposable functions, surface-auditing and conversational swarms operating on real messaging networks (WhatsApp, Signal, RCS, Web Chat) depend on scarce physical and cryptographic assets:
1. Authenticated E.164 identities with aged reputation.
2. Persistent Signal Double Ratchet cryptographic sessions.
3. Metered SMS OTP provisioning budgets.
4. Sticky residential proxy sessions bound to a regional ASN and IPv4 `/24` subnet.

`swarm-self-healing` decouples these survival invariants from any specific messaging driver or database engine using Hexagonal Architecture (`SwarmLedgerPort` and `ScoutProvisionerPort`).

---

## 2. Hexagonal Architecture & Ports

```
+-----------------------------------------------------------------------------------+
|                        SWARM SELF-HEALING ARCHITECTURE                            |
+-----------------------------------------------------------------------------------+
                                          |
       +----------------------------------+----------------------------------+
       |                                  |                                  |
       v                                  v                                  v
+-----------------------+      +-----------------------+      +-----------------------+
| HomeostasisController |      |      HeatPolicy       |      | NetworkAffinityGuard  |
| - Sub-5s hot failover |      | - Discrete deltas     |      | - ASN consistency     |
| - Target population   |      | - [0.0, 1.0] clamping |      | - Tier 2 DHCP /24     |
| - Standby promotion   |      | - Rotation >= 0.70    |      | - Jump quarantine     |
+-----------------------+      +-----------------------+      +-----------------------+
       |                                  |                                  |
       +----------------------------------+----------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           RESOURCE CIRCUIT BREAKER                                |
| - States: CLOSED, OPEN_SMS_EXHAUSTED, OPEN_PROXY_EXHAUSTED, OPEN_LLM_QUOTA        |
| - Anti-storm alert deduplication (single alert per trip, zero replenishment loops)|
| - Explicit operator reset via unlock()                                            |
+-----------------------------------------------------------------------------------+
                                          |
                                          v  [Injected Ports]
+-----------------------------------------------------------------------------------+
|  SwarmLedgerPort: get_scouts_by_state(), transition_scout_state(),                |
|                   promote_standby_for_mission(), update_heat_score()              |
|  ScoutProvisionerPort: provision_new_scout()                                      |
+-----------------------------------------------------------------------------------+
```

---

## 3. Core Survival Engines

### 3.1. `HeatPolicy` (`swarm_self_healing.policies`)
* **Preventive Rotation Trigger:** `heat_score >= 0.70` transitions an `ACTIVE_EXTERNAL` agent to `SANDBOX_MATURING` before triggering external platform rate-limits.
* **Standby Readiness Trigger:** `heat_score <= 0.15` graduates a cooled `SANDBOX_MATURING` agent back to `STANDBY_READY`.
* **Discrete Deltas:**
  - External burst turn: `+0.14`
  - External regular turn: `+0.06`
  - Sandbox cooldown turn: `-0.05`
  - Full session rest: `-0.15`
* **Mandatory Saturation:** `heat_score = min(1.0, max(0.0, current_heat + delta))`.

### 3.2. `NetworkAffinityGuard` (`swarm_self_healing.policies`)
* **Tier 1 (`EXACT_MATCH`):** Identical IPv4 and identical ASN -> approved without mutation.
* **Tier 2 (`DHCP_SUBNET_RENEWED`):** Identical ASN and identical IPv4 `/24` prefix (first 3 octets) -> approved as a legitimate residential ISP DHCP renewal, updating `last_verified_ip`.
* **Tier 3 (`AFFINITY_MISMATCH`):** ASN mismatch or `/24` subnet jump -> immediately raises `ProxyAffinityMismatchError` to block connection before leaking identity reputation.

### 3.3. `ResourceCircuitBreaker` (`swarm_self_healing.circuit_breaker`)
* **State Machine:** `CLOSED` -> `OPEN_SMS_EXHAUSTED` | `OPEN_PROXY_EXHAUSTED` | `OPEN_LLM_QUOTA` | `OPEN_MANUAL_PANIC`.
* **Anti-Storm Guarantee:** Emits at most one alert callback per tripped state and blocks all subsequent `ScoutProvisionerPort.provision_new_scout()` calls until `unlock()` is invoked.

### 3.4. `HomeostasisController` (`swarm_self_healing.controller`)
* **Deterministic Tick Loop (`run_tick`):**
  1. Rotates overheated `ACTIVE_EXTERNAL` agents (`heat_score >= 0.70`) to `SANDBOX_MATURING`.
  2. Executes atomic `<5s` standby failover (`execute_hot_failover`) for missions whose assigned agent was quarantined or preventively cooled.
  3. Computes healthy population deficit (`target - healthy_count`) and provisions replacements via `ScoutProvisionerPort` if `ResourceCircuitBreaker` is `CLOSED`.
