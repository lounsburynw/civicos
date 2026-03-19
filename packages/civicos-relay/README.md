# civicos-relay

Federation-ready civic coordination relay for CivicOS.

## Overview

A relay is a server that:
- **Routes events** — agenda published, decision made, meeting scheduled
- **Manages subscriptions** — who wants to know about what
- **Counts voices** — public expressions of civic interest
- **Tracks provenance** — trust signals for voice quality
- **Syncs with peers** — federation-ready from day one

## Installation

```bash
pip install -e packages/civicos-relay
```

## Quick Start

### As Library (Integrated)

```python
from civicos_relay import VoiceService, KeyPair, Stance
from civicos_relay.storage import InMemoryStorage

# Create service
storage = InMemoryStorage()
voice_service = VoiceService(storage)

# Cast a voice
keypair = KeyPair.generate()
voice = voice_service.cast_voice(keypair, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

# Get counts
counts = voice_service.get_counts("agenda:2026-02-03:item-6a")
print(f"Support: {counts.support}, Oppose: {counts.oppose}")
```

### As Standalone Server

```bash
# Configure relay
export RELAY_ID="relay.example.org/san-rafael"
export RELAY_PRIVATE_KEY_PATH="/secrets/relay.key"
export DATABASE_URL="postgresql://..."

# Run server
civicos-relay --host 0.0.0.0 --port 8003
```

### With Peering (Federation)

```yaml
# relay.yaml
relay:
  id: "relay.civicos.org/san-rafael"
  private_key_path: "/secrets/relay.key"

  namespaces:
    - "city-san-rafael:*"

  peers:
    - url: "https://relay.marincounty.org"
      namespaces: ["county-marin:*"]
      sync_interval: 300
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Relay                                              │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Voice    │  │ Events   │  │ Sync     │         │
│  │ Service  │  │ Service  │  │ Service  │         │
│  └──────────┘  └──────────┘  └──────────┘         │
│       │             │             │                │
│  ┌──────────────────────────────────────┐         │
│  │           Storage Backend            │         │
│  └──────────────────────────────────────┘         │
│       │                                            │
│  ┌──────────┐  ┌──────────┐                       │
│  │ Identity │  │ Peering  │                       │
│  └──────────┘  └──────────┘                       │
└─────────────────────────────────────────────────────┘
        │                │
        ▼                ▼
   PostgreSQL      Peer Relays
```

## API Endpoints

### Voice Operations
- `POST /voice` — Cast a voice (signed)
- `GET /voice/counts/{entity}` — Get voice counts
- `GET /voice/{entity}` — List voices for entity

### Subscriptions
- `POST /subscribe` — Create subscription
- `DELETE /subscribe/{id}` — Unsubscribe
- `GET /subscriptions` — List own subscriptions

### Sync (Federation)
- `GET /sync/voices` — Export voices for peer sync
- `POST /sync/voices` — Import voices from peer
- `GET /sync/events` — Export events
- `POST /sync/events` — Receive events from peer

### Health
- `GET /health` — Relay health check
- `GET /metrics` — Prometheus metrics

## Documentation

- `docs/critical/COORDINATION_PROTOCOL.md` — Full protocol design

## Testing

```bash
python -m pytest packages/civicos-relay/tests/ -v
```

## License

PolyForm Noncommercial 1.0.0
