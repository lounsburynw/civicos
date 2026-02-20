# CivicOS Learning Modules

Self-contained documents for learning the CivicOS architecture from first principles. Each module can be pasted into NotebookLM or Claude.ai as context for interactive learning.

## Modules

| Module | Topic | Prerequisites | Best For |
|--------|-------|---------------|----------|
| [01 — Cryptographic Foundations](01_CRYPTOGRAPHIC_FOUNDATIONS.md) | Keys, signatures, hashing, why self-sovereign identity matters | None | Understanding the trust layer |
| [02 — Nostr and the Relay](02_NOSTR_AND_THE_RELAY.md) | Events, relays, federation, how CivicOS extends Nostr | Module 1 | Understanding the protocol layer |
| [03 — Attestation and the Full System](03_ATTESTATION_AND_THE_FULL_SYSTEM.md) | Gated attestation, edge intelligence, design decisions, the complete architecture | Modules 1 + 2 | Understanding the full system and its motivations |
| [04 — Relay Trust and Integrity](04_RELAY_TRUST_AND_INTEGRITY.md) | Relay cardinality, data robustness, adversary analysis (government, capital, institutional capture) | Modules 1-3 | Understanding the trust and threat model |
| [05 — Jurisdiction Scope and Attestation Rollup](05_JURISDICTION_SCOPE_AND_ATTESTATION_ROLLUP.md) | Relay scope, attestation across government levels, special districts, operational deployment | Modules 1-4 | Understanding multi-jurisdiction design |

## How to Use

**NotebookLM:** Upload all five as sources. Ask it to generate an audio overview, or quiz you on specific topics.

**Claude.ai:** Paste a module into a conversation and ask follow-up questions. The "Questions to Explore" sections in Modules 3-5 have good starting prompts.

**Reading order:** 1 → 2 → 3 → 4 → 5. Each builds on the previous. Module 3 ties the system together. Modules 4 and 5 explore trust and multi-jurisdiction design.
