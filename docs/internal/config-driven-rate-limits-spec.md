# Config-Driven Rate Limits Spec

**Status:** Done
**Date:** 2026-03-11
**Launch.json item:** `config_driven_rate_limits`

## Problem

The relay acceptance policy has a hardcoded `DEFAULT_POLICY` dict at module level in `acceptance.py`:

```python
DEFAULT_POLICY = {
    "voice": {"max_per_day": 50, "pow_difficulty": 16},
    "comment": {"max_per_day": 100, "pow_difficulty": 16},
    ...
}
```

Every relay instance uses identical limits regardless of jurisdiction. When onboarding Mill Valley, San Anselmo, and Berkeley, each city may need different rate limits based on population, meeting frequency, and expected traffic. Changing limits currently requires a code deployment.

## Design Principles

1. **Per-jurisdiction configuration** — each jurisdiction can have its own rate limits and PoW difficulty.
2. **Sensible defaults** — cities that don't specify a policy inherit reasonable defaults.
3. **No DB dependency for policy** — policy should load at startup, not on every request. Config file or registry entry, not a database table.
4. **Operator override** — a self-hosted relay operator can set their own policy without forking code.

## Decisions Required

### 1. Where Policy Lives

**Option A: Extend `config/registry.json`**

```json
{
  "city-san-rafael": {
    "domain": "san-rafael.civicosproject.org",
    "relay_policy": {
      "voice": {"max_per_day": 50, "pow_difficulty": 20},
      "comment": {"max_per_day": 100, "pow_difficulty": 16}
    }
  }
}
```

- Pro: Single source of truth for jurisdiction config. Already loaded at startup.
- Con: Registry is shared across services. Relay-specific config in a shared file feels wrong.

**Option B: Separate `config/relay_policies.json`**

```json
{
  "default": {
    "voice": {"max_per_day": 50, "pow_difficulty": 20},
    "comment": {"max_per_day": 100, "pow_difficulty": 16}
  },
  "city-berkeley": {
    "voice": {"max_per_day": 200, "pow_difficulty": 16},
    "comment": {"max_per_day": 500, "pow_difficulty": 12}
  }
}
```

- Pro: Clean separation. Relay-only concern in relay-only file.
- Con: Another config file to manage and deploy.

**Option C: Environment variable override**

```
RELAY_POLICY_FILE=/path/to/policy.json
```

- Pro: Operator-friendly. Self-hosted relay operators set one env var.
- Con: Needs fallback logic.

**Recommendation:** Option B with Option C as override. `config/relay_policies.json` is the default, `RELAY_POLICY_FILE` env var overrides for operators. Both fall back to the current `DEFAULT_POLICY` if neither exists.

### 2. Policy Resolution Order

```
RELAY_POLICY_FILE env var (operator override)
  → config/relay_policies.json[jurisdiction_id] (per-jurisdiction)
    → config/relay_policies.json["default"] (defaults)
      → DEFAULT_POLICY constant (hardcoded fallback)
```

Each level merges with the next — a jurisdiction can override `voice.max_per_day` without specifying every event type.

### 3. AcceptancePolicy Constructor Change

Current:
```python
class AcceptancePolicy:
    def __init__(self, rate_limiter, policy=None):
        self.policy = policy or DEFAULT_POLICY
```

Proposed:
```python
class AcceptancePolicy:
    def __init__(self, rate_limiter, jurisdiction_id: str, policy=None):
        self.policy = policy or load_policy(jurisdiction_id)
```

Where `load_policy()` implements the resolution order above.

## Implementation

1. Create `config/relay_policies.json` with current defaults + San Rafael overrides
2. Add `load_policy(jurisdiction_id)` function to acceptance.py
3. Update `AcceptancePolicy.__init__` to accept `jurisdiction_id`
4. Update `app.py` lifespan to pass jurisdiction_id when creating policy
5. Add `RELAY_POLICY_FILE` env var support
6. Update testbed relay deployments with per-city policies

## Test Strategy

- Unit test: policy resolution order (override > per-jurisdiction > default > hardcoded)
- Unit test: partial override merges correctly (only override voice, inherit comment)
- Integration test: two relays with different policies enforce different limits
