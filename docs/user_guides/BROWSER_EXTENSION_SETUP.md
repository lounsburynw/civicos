# Browser Extension Setup Guide

The CivicOS browser extension is the primary way to access civic data. It brings meeting history, upcoming decisions, community issues, and coordination tools directly into your Chrome browser. The extension runs your personal civic agent locally — your identity keys and preferences never leave your device.

---

## Installation

### From Chrome Web Store (Recommended)

1. Visit the [CivicOS Extension](https://chrome.google.com/webstore) on the Chrome Web Store
2. Click **Add to Chrome**
3. Pin the extension to your toolbar for easy access

### Sideload from Source (Developers)

For development or testing:

```bash
# Clone and build
git clone https://github.com/lounsburynw/civicos.git
cd civicos/apps/civicos-extension
npm install
npm run build
```

Then in Chrome:
1. Go to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `apps/civicos-extension/dist` directory

---

## First-Time Setup

### 1. Open the Side Panel

Click the CivicOS icon in your Chrome toolbar, then click **Open City Pulse**. The side panel appears alongside your current page.

### 2. Create Your Identity

Open Settings (click **Settings** in the popup, or right-click the extension icon and choose **Options**):

1. Under **Identity**, set a password and confirm it
2. Click **Create Identity**
3. **Save your recovery phrase** — this is the only way to restore your identity if you lose it. Write it down or store it securely.
4. Your Nostr-compatible `npub` identifier is now displayed — this is your civic identity

Your private key is encrypted with your password and stored only in Chrome's extension storage. It is never sent to any server.

### 3. Select Your Jurisdiction

Still in Settings:
1. Under **Jurisdiction**, select your city from the dropdown (e.g., San Rafael)
2. The extension fetches available jurisdictions from the CivicOS registry
3. Your selection is saved automatically

### 4. Sign In

After creating your identity, you need to unlock (sign in) each browser session:
1. Open Settings
2. Enter your password under the identity section
3. Click **Unlock**

When signed in, the popup shows a green "Signed in" status next to your truncated `npub`.

---

## Features

### City Pulse (Side Panel)

The side panel is your main interface, organized into collapsible sections:

- **Upcoming Meetings** — Council, commission, and board meetings from your jurisdiction's calendar, with dates and times
- **Voice Your Stance** — Active agenda items where you can register support, opposition, or indicate you are watching. Voice counts are shown in real time. Expand items to read and post public comments.
- **Decided** — Recent outcomes (approved, denied, continued) with expandable context
- **Issue Map** — Community-reported issues plotted on a neighborhood map (powered by Leaflet)
- **Budget** — City budget breakdown with interactive charts
- **Community Initiatives** — Resident-created initiatives with voice counts and coordination tools
- **Connected Services** — Health status of connected jurisdiction MCP servers and the relay

Use the **jurisdiction tabs** at the top to switch between your city, county, and state-level data when parent jurisdictions are available.

### Chat

The chat bar at the bottom of the side panel lets you ask natural language questions about civic data. It connects to your configured AI provider and uses CivicOS tools to answer questions like:

- "What happened at the last city council meeting?"
- "What's the city budget for parks?"
- "Are there any housing items on the next agenda?"

Chat responses can navigate you to relevant sections in City Pulse automatically.

### Civic Journal

In Settings, the **Civic Journal** is a personal markdown document where you describe your priorities, values, and civic history. The journal is stored locally and never sent to a server. When you use the chat feature, your journal provides context so AI responses are tailored to what matters to you.

A starter template is provided with sections like "What I care about," "What I support," "What frustrates me," and "My vision for the city." You can export and import your journal as a markdown file.

### Identity and Signing

- Sign public comments and voice stances with your Nostr identity (secp256k1 Schnorr signatures)
- Your signature proves authorship without revealing personal information
- Lock your identity when stepping away; unlock with your password to resume

### Attestation (Proof of Residency)

Attestation verifies you are a resident of your jurisdiction, unlocking features like weighted voice counts:

1. Obtain a single-use verification code from your city administrator
2. In Settings under **Attestation**, enter the code and click **Verify**
3. Once verified, your attestation badge appears in City Pulse next to your identity

See the [Attestation Guide](ATTESTATION_GUIDE.md) for the full workflow.

### Claude Bridge (AI Integration)

The extension includes a content script that integrates with claude.ai. When you visit claude.ai, the extension can inject your civic context into the conversation, making Claude aware of your local governance data without you having to paste it manually.

### NIP-07 Provider

The extension exposes a `window.nostr` provider (NIP-07 standard), allowing Nostr-compatible web apps to request signatures from your CivicOS identity.

---

## AI Provider Configuration

In Settings under **AI Provider**, you can choose how chat intelligence is powered:

| Provider | Description |
|----------|-------------|
| **CivicOS** | Default — uses the CivicOS-hosted AI endpoint, no API key needed |
| **Claude** | Uses your own Anthropic API key |
| **OpenAI** | Uses your own OpenAI API key |
| **Ollama** | Connects to a locally-running Ollama instance for fully private, offline AI |

For Ollama, configure the base URL (default `http://localhost:11434`) and select a model. This is the "sovereign intelligence" option — no data leaves your machine.

---

## Permissions Explained

### Required Permissions

| Permission | Why It's Needed |
|-----------|-----------------|
| `sidePanel` | Display the City Pulse panel alongside web pages |
| `storage` | Store your encrypted identity keys, preferences, and journal locally |
| `alarms` | Background checks for approaching deadlines and new civic data |

### Host Permissions

| Host | Why It's Needed |
|------|-----------------|
| `*.civicosproject.org` | Fetch civic data from jurisdiction MCP servers |
| `*.modal.run` | Connect to CivicOS cloud services |

### Optional Permissions (Granted on Request)

| Permission / Host | Why It's Needed |
|-------------------|-----------------|
| `identity` | Google OAuth for Gemini AI provider (if selected) |
| `localhost:8081` | Connect to a local Personal MCP server |
| `claude.ai`, `openai.com` | AI surface integration via content scripts |
| `api.anthropic.com`, `api.openai.com` | Direct API calls when using your own API key |

The extension does NOT:
- Track your browsing history
- Send your identity keys to any server
- Require any personal information to use

---

## Troubleshooting

### Extension does not appear in toolbar
1. Click the puzzle piece icon in Chrome's toolbar
2. Find CivicOS and click the pin icon

### Side panel is blank
1. Check your internet connection
2. Try closing and reopening the side panel
3. Check the browser console (F12, then Console tab) for errors

### Identity lost after clearing browser data
Your keys are stored in Chrome's extension storage. If cleared:
1. Open Settings
2. Click **Import Identity**
3. Enter your recovery phrase (mnemonic) and a new password
4. Your identity is restored with the same `npub`

If you did not save your recovery phrase, the identity cannot be recovered. You will need to create a new one.

### City Pulse shows no data
1. Confirm your jurisdiction is selected in Settings
2. Check the **Connected Services** section at the bottom of City Pulse for server health
3. If a server shows "offline," the jurisdiction MCP endpoint may be temporarily unavailable

### AI chat not responding
1. Open Settings and check your AI provider configuration
2. For CivicOS provider: verify internet connectivity
3. For Claude/OpenAI: verify your API key is entered correctly
4. For Ollama: verify Ollama is running (`curl http://localhost:11434/api/tags`)

### Endpoint overrides (Advanced)
In Settings under **Endpoints**, you can override the MCP and relay URLs. This is useful for local development:
- MCP: `http://localhost:8001` (local API server)
- Personal MCP: `http://localhost:8081` (local Personal MCP)

---

## Browser Compatibility

**Chrome** is the primary target. The extension uses Manifest V3 APIs including Side Panel, which is Chrome-specific.

**Brave** (Chromium-based) runs Chrome extensions natively and provides additional privacy at the browser level.

**Firefox** is not currently supported. Firefox uses a different sidebar API, though the core architecture is portable if demand warrants a port.

---

## For Developers

### Development Mode

```bash
cd apps/civicos-extension
npm run dev    # Watch mode — rebuilds on file changes
```

Then reload the extension in `chrome://extensions` after changes (or use the update button).

### Visual Testing

```bash
npm run test:visual           # Run Playwright visual regression tests
npm run test:visual:update    # Update baseline snapshots
```

### Architecture

See [Browser Extension Architecture](../critical/BROWSER_EXTENSION_ARCHITECTURE.md) for technical details on the extension's edge intelligence layers, MCP client integration, content script injection model, and identity system.

---

## Next Steps

- **[Getting Started](GETTING_STARTED.md)** — Learn what you can ask CivicOS
- **[Attestation Guide](ATTESTATION_GUIDE.md)** — Prove residency for coordination features
- **[FAQ](FAQ.md)** — Common questions and answers
