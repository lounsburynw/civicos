# Browser Extension Setup

The CivicOS browser extension is the primary user interface. It runs as a Chrome side panel showing civic data for your jurisdiction.

## Install (End Users)

The extension is currently distributed as a developer build. Install from source:

1. Clone the repository and build:
   ```bash
   cd apps/civicos-extension
   npm install
   npm run build
   ```

2. Open Chrome and go to `chrome://extensions`
3. Enable **Developer mode** (top right toggle)
4. Click **Load unpacked** and select `apps/civicos-extension/dist`
5. Click the CivicOS icon in your toolbar, then **Open City Pulse**

## What You'll See

The side panel shows collapsible sections:

- **Meetings** — Upcoming council meetings with dates, locations, and agendas
- **Agenda Items** — Current items with AI-enriched summaries, voice counts, and stance buttons
- **Decisions** — Past decisions with outcomes and vote records
- **Issue Map** — Community issues (311/SeeClickFix) plotted geographically
- **Budget** — Municipal budget breakdown by department
- **Initiatives** — Community-submitted initiatives with attestation badges

## Identity

The extension manages a local Nostr identity (secp256k1 Schnorr keys):

1. Click the extension icon and go to **Settings**
2. Under **Identity**, create a new identity or import from a recovery phrase (BIP-39 mnemonic)
3. Set a password to encrypt the key (stored in `chrome.storage.local`, never leaves your device)
4. Unlock at the start of each session — lock state clears when the browser closes

The extension also acts as a NIP-07 provider, injecting `window.nostr` for compatible websites.

## Voice (Stances)

On any agenda item, you can express:
- **Support** — you're in favor
- **Oppose** — you're against
- **Watching** — you're tracking but not taking a position

Stances are stored locally and submitted to the CivicOS relay with your Nostr signature.

## Settings

Access via the extension icon > Settings:

- **Jurisdiction** — Select your active city
- **AI Provider** — Choose from: CivicOS proxy (default, no key needed), Claude, OpenAI, Gemini, Ollama (local), or Chrome Nano (on-device)
- **Theme** — Light, dark, or auto
- **Civic Journal** — Local markdown notes that feed into AI context
- **Profile** — Name, neighborhood, interests (stored locally only)
- **Endpoints** — API server, relay URL, personal MCP server URL

## Attestation

If you receive a single-use attestation code from an administrator:

1. Go to Settings > Identity
2. Enter the code and click Redeem
3. The extension signs a Nostr attestation event and submits it to the relay
4. Your voice submissions will include the attestation proof
