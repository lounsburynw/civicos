# Architecture Deep Dives

Self-contained documents for understanding the CivicOS architecture from first principles. Each module can be pasted into NotebookLM or Claude.ai as context for interactive exploration.

## Modules

| Module | Topic | Prerequisites | Best For |
|--------|-------|---------------|----------|
| [01 — Cryptographic Foundations](01_CRYPTOGRAPHIC_FOUNDATIONS.md) | Keys, signatures, hashing, why self-sovereign identity matters | None | Understanding the trust layer |
| [02 — Nostr and the Relay](02_NOSTR_AND_THE_RELAY.md) | Events, relays, federation, how CivicOS extends Nostr | Module 1 | Understanding the protocol layer |
| [03 — Attestation and the Full System](03_ATTESTATION_AND_THE_FULL_SYSTEM.md) | Gated attestation, edge intelligence, design decisions, the complete architecture | Modules 1 + 2 | Understanding the full system and its motivations |
| [04 — Relay Trust and Integrity](04_RELAY_TRUST_AND_INTEGRITY.md) | Relay cardinality, data robustness, adversary analysis (government, capital, institutional capture) | Modules 1-3 | Understanding the trust and threat model |
| [05 — Economic Model and Sustainability](06_ECONOMIC_MODEL_AND_SUSTAINABILITY.md) | Costs, revenue models, customer segments, the moat, why previous civic tech failed, anti-revenue constraints | Modules 1-4 | Understanding the business model |
| [06 — Jurisdiction Scope and Attestation Rollup](05_JURISDICTION_SCOPE_AND_ATTESTATION_ROLLUP.md) | Relay scope, attestation across government levels, special districts, operational deployment | Modules 1-5 | Understanding multi-jurisdiction design |

## Choose Your Path

| You are a... | Start with | Then explore |
|--------------|-----------|--------------|
| **Curious resident** | [Module 1](01_CRYPTOGRAPHIC_FOUNDATIONS.md) → [Module 3](03_ATTESTATION_AND_THE_FULL_SYSTEM.md) | FAQ, Getting Started |
| **Developer** | [Module 1](01_CRYPTOGRAPHIC_FOUNDATIONS.md) → all modules in order | CLAUDE.md, architecture docs |
| **Civic leader / funder** | [Module 3](03_ATTESTATION_AND_THE_FULL_SYSTEM.md) → [Module 5](06_ECONOMIC_MODEL_AND_SUSTAINABILITY.md) | Sustainability model, relay docs |
| **Security researcher** | [Module 1](01_CRYPTOGRAPHIC_FOUNDATIONS.md) → [Module 4](04_RELAY_TRUST_AND_INTEGRITY.md) | Coordination protocol, relay trust model |

## How to Use

**NotebookLM:** Upload all six as sources. Ask it to generate an audio overview, or quiz you on specific topics.

**Claude.ai:** Paste a module into a conversation and ask follow-up questions. The "Questions to Explore" sections in Modules 3-6 have good starting prompts.

**Reading order:** 1 → 2 → 3 → 4 → 5 → 6. Each builds on the previous. Modules 1-3 cover the system. Module 4 covers trust. Module 5 covers sustainability. Module 6 covers multi-jurisdiction operations.

## See Also

The [Relay documentation](../relay/overview.md) covers the same topics as Modules 3-5 in operational reference form. The learning modules teach from first principles with analogies and design rationale; the relay docs are concise reference for implementers.
