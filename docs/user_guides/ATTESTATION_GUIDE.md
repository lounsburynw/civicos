# Attestation Guide

Attestation proves you're a real person in a specific community. It's required to voice or comment on civic items — this is how CivicOS prevents spam from bots and automated agents while keeping participation inclusive.

**How it works:** A volunteer distributes single-use codes at an in-person event (community meeting, farmer's market, library pop-up). You enter the code in the CivicOS extension. The code binds permanently to your identity, producing a cryptographic proof that accompanies every voice and comment you submit.

No government ID required. Physical presence + a volunteer's judgment is sufficient.

---

## For Residents

### Redeeming Your Code

1. **Get a code** from a CivicOS volunteer at a local event. It looks like: `SR-2026-02-A7K9`
2. **Open the CivicOS extension** in your browser
3. **Go to Options** (click the gear icon)
4. **Find the "Attestation" section** below Identity
5. **Enter your code** and click "Verify Code"
6. **Done.** You'll see a green "Attested for San Rafael" badge

Your attestation is permanent as long as you keep the same identity. If you reset your identity (create a new key), you'll need a new code.

### What Attestation Means

- Attestation is **required** to voice or comment on civic items
- Without attestation, you can still browse civic data, read meeting info, and subscribe to notifications
- Each code required showing up in person — this makes automated spam uneconomical
- The attestation proof is embedded on every voice and comment you submit, so any relay can verify it independently

### FAQ

**Do I need attestation to use CivicOS?**
You need attestation to voice or comment. You can still browse all civic data (meetings, decisions, agendas, legislation) and subscribe to notifications without attestation. To get attested, attend any community event where codes are being distributed.

**Can I get multiple codes?**
Each code can only be used once, and each identity can only be attested once per city. If a volunteer has already given you a code, they'll recognize you.

**What if I lose my identity key?**
If you reset your identity, your attestation is lost. You'll need to attend another event to get a new code. This prevents people from creating many attested identities.

**Does attestation expire?**
Codes can have expiration dates (they return a 410 error if redeemed after expiry). Once redeemed, your attestation persists.

---

## For Administrators

### Generating Codes

Use the code generation script to create a batch of codes before an event:

```bash
source civicos-env/bin/activate

# Generate 50 codes for a San Rafael event
python3 scripts/generate_attestation_codes.py \
  --jurisdiction city-san-rafael \
  --count 50 \
  --batch "pilot-launch-2026"

# Dry run (preview without inserting into DB)
python3 scripts/generate_attestation_codes.py \
  --jurisdiction city-san-rafael \
  --count 50 \
  --batch "pilot-launch-2026" \
  --dry-run

# With expiration date
python3 scripts/generate_attestation_codes.py \
  --jurisdiction city-san-rafael \
  --count 50 \
  --batch "pilot-launch-2026" \
  --expires 2026-06-01
```

Codes are output to stdout (one per line) for easy printing. Redirect to a file:

```bash
python3 scripts/generate_attestation_codes.py \
  --jurisdiction city-san-rafael \
  --count 50 \
  --batch "pilot-launch-2026" > codes.txt
```

### Code Format

Codes follow the pattern: `{PREFIX}-{YYYY}-{MM}-{RANDOM4}`

| Jurisdiction | Prefix | Example |
|---|---|---|
| city-san-rafael | SR | SR-2026-02-A7K9 |
| city-berkeley | BK | BK-2026-03-X2M1 |
| city-oakland | OK | OK-2026-03-P8R3 |

### Printing Codes

The output is one code per line, ready for:
- **Label printer**: Import into Avery or similar label template
- **Cut sheets**: Print on paper, cut into strips
- **Cards**: Print on business card stock (one code per card)

Each code should be visually distinct and easy to type. Include brief instructions on the card:

```
Your CivicOS Attestation Code:
SR-2026-02-A7K9

Enter this code in CivicOS Extension > Options > Attestation
This code can only be used once.
```

### Distribution Guidelines

**Who distributes:**
- CivicOS volunteers or project organizers
- City staff at public events (optional)

**Where to distribute:**
- City council meetings
- Community events, farmer's markets
- Library or community center pop-ups
- Neighborhood association meetings

**How to distribute:**
- One code per person
- Use human judgment for dedup ("I already gave you one")
- No government ID required
- Brief verbal explanation: "This proves you're a real San Rafael resident when you participate online"

**What NOT to do:**
- Don't leave codes unattended (pile of cards anyone can grab)
- Don't distribute electronically (email, text) — defeats the physical presence requirement
- Don't ask for ID or personal information

### Monitoring

Check attestation stats via the API:

```bash
# Stats for a jurisdiction
curl https://civicos--civicos-relay-relayserver-relay-endpoint.modal.run/coordination/attestation/stats/city-san-rafael
```

Returns:
```json
{
  "total_attested": 3,
  "total_codes_issued": 5,
  "total_codes_redeemed": 3
}
```

Check a specific user's attestation:

```bash
curl "https://civicos--civicos-relay-relayserver-relay-endpoint.modal.run/coordination/attestation/{pubkey_hex}?jurisdiction=city-san-rafael"
```

### Database Queries (Advanced)

For deeper analysis, query the relay database directly:

```sql
-- Codes by batch
SELECT batch_id, count(*) as total,
       count(redeemed_by) as redeemed,
       count(*) - count(redeemed_by) as remaining
FROM coordination_attestation_codes
WHERE jurisdiction = 'city-san-rafael'
GROUP BY batch_id;

-- Recent redemptions
SELECT code, redeemed_by, redeemed_at
FROM coordination_attestation_codes
WHERE redeemed_by IS NOT NULL
ORDER BY redeemed_at DESC
LIMIT 10;
```

### Security Model

**What attestation prevents:**
- Autonomous agents generating unlimited synthetic identities to flood participation
- One person creating 50 fake identities to game voice counts (Sybil attack)
- Automated bots submitting voices or comments (hard-rejected by relay with 403)
- Forged or tampered attestation proofs (cryptographically verified, rejected with 400)

**What attestation does NOT prevent:**
- A motivated person getting 3-4 codes across multiple events (noise, not manipulation)
- Someone giving their code to another real person (still a real person)

**Design trade-offs:**
- No ID check = inclusive (undocumented residents can participate)
- Physical presence = friction that scales poorly for attackers
- Hard gate = no unattested voices means cleaner signal for council and public

---

## Technical Reference

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/coordination/attest` | POST | Redeem a code (requires Nostr-signed request) |
| `/coordination/attestation/{pubkey}` | GET | Check attestation status |
| `/coordination/attestation/stats/{jurisdiction}` | GET | Jurisdiction-wide stats |

All endpoints live on the relay server.

### Nostr Event

Attestation produces a **kind 30850** Nostr event signed by the CivicOS attestation issuer keypair:

```json
{
  "kind": 30850,
  "tags": [
    ["d", "attest:city-san-rafael:{subject_pubkey}"],
    ["p", "{subject_pubkey}"],
    ["j", "city-san-rafael"],
    ["type", "physical"]
  ],
  "content": "civicos:attestation:v1:city-san-rafael:physical:{timestamp}"
}
```

The `d` tag makes it an addressable/replaceable event per NIP-33, allowing one attestation per pubkey per jurisdiction.

### Database Tables

- `coordination_attestation_codes` — Single-use codes with batch tracking
- `coordination_attestations` — Bound attestation records with kind-30850 events

Both tables have RLS enabled (service_role access only).
