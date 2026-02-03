# Voice Widget MCP App - Implementation Sketch

**Status:** Scaffolded (apps/civicos-mcp-apps/)

## Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| Project scaffold | ✅ Done | `apps/civicos-mcp-apps/` |
| Server entry point | ✅ Done | `server.ts` |
| Jurisdiction client | ✅ Done | `src/lib/jurisdiction-client.ts` |
| Voice widget HTML | ✅ Done | `src/widgets/voice.html` |
| Widget registration | ✅ Done | `src/widgets/voice/register.ts` |
| Signing utilities | ✅ Done | `src/lib/signing.ts` |
| npm install | ⏳ Pending | Run `npm install` |
| Build widgets | ⏳ Pending | Run `npm run build` |
| Test locally | ⏳ Pending | Run `npm run dev` + cloudflared |
| Deploy to Modal | ⏳ Pending | Create modal_app.py |

### Next Steps

1. `cd apps/civicos-mcp-apps && npm install`
2. `npm run dev` (builds widgets + starts server)
3. `npm run tunnel` (exposes to Claude.ai)
4. Add cloudflared URL as custom connector in Claude.ai
5. Test: "Show me the voice interface for decision:city-san-rafael:2026-01-15:item-5a"

---

## Overview

An interactive voice-casting widget that renders directly in Claude.ai, ChatGPT, and other MCP Apps-enabled hosts. Users can support/oppose civic items without leaving the conversation.

```
┌─────────────────────────────────────────────────┐
│  Decision: Bike Lane on 4th Street              │
│  Meeting: Jan 15, 2026 City Council             │
│                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Support │  │ Oppose  │  │ Watch   │         │
│  │   47    │  │   12    │  │   89    │         │
│  └─────────┘  └─────────┘  └─────────┘         │
│                                                 │
│  ○ Anonymous  ● Verified (TouchID)              │
│                                                 │
│  [Cast Your Voice]                              │
└─────────────────────────────────────────────────┘
```

## Architecture

```
┌──────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│   AI Host        │     │  MCP Apps Server  │     │  CivicOS        │
│  (Claude.ai)     │     │  (TypeScript)     │     │  Backend        │
├──────────────────┤     ├───────────────────┤     ├─────────────────┤
│                  │     │                   │     │                 │
│  ┌────────────┐  │     │  voice_interface  │     │  Jurisdiction   │
│  │  Sandboxed │◄─┼─────┤  tool + resource  │◄────┤  MCP (Python)   │
│  │   iframe   │  │     │                   │     │                 │
│  └─────┬──────┘  │     │  Serves bundled   │     │  get_voice_     │
│        │         │     │  Vue HTML         │     │  counts()       │
│        │         │     │                   │     │                 │
│  postMessage     │     │  Proxies tool     │     │  broadcast_     │
│        │         │     │  calls to Python  │     │  voice()        │
│        ▼         │     │  backend          │     │                 │
│  [Support]       │     │                   │     │  Relay Node     │
│   clicked        │────►│  broadcast_voice  │────►│  (Nostr)        │
│                  │     │                   │     │                 │
└──────────────────┘     └───────────────────┘     └─────────────────┘
```

## Why TypeScript MCP Apps Layer?

The MCP Apps SDK (`@modelcontextprotocol/ext-apps`) is TypeScript-only currently. Options:

| Approach | Pros | Cons |
|----------|------|------|
| **TypeScript proxy** (recommended) | Uses official SDK, Vue templates, fast iteration | Additional service |
| **Python native** | Single service | Manual protocol implementation, no SDK support yet |
| **Hybrid** (TypeScript UI + Python tools) | Best of both | More complex routing |

**Recommended:** TypeScript MCP Apps server that:
1. Serves UI resources (bundled Vue HTML)
2. Proxies tool calls to existing Python Jurisdiction MCP
3. Handles identity/signing via Personal MCP patterns

---

## Implementation Plan

### Phase 1: Standalone MCP Apps Server

New directory: `apps/civicos-mcp-apps/`

```
apps/civicos-mcp-apps/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── server.ts              # MCP server with tool + resource registration
├── src/
│   ├── voice-widget.html  # Entry point
│   ├── voice-widget.ts    # App logic
│   └── components/
│       └── VoiceWidget.vue
├── lib/
│   ├── jurisdiction-client.ts  # Calls Python MCP backend
│   └── identity.ts             # Simplified identity for widget
└── dist/
    └── voice-widget.html  # Bundled single-file output
```

### Phase 2: Server Implementation

```typescript
// server.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import express from "express";
import cors from "cors";
import fs from "node:fs/promises";
import path from "node:path";

// Client to existing Python MCP backend
import { JurisdictionMCPClient } from "./lib/jurisdiction-client.js";

const server = new McpServer({
  name: "CivicOS Voice",
  version: "1.0.0",
});

const jurisdictionClient = new JurisdictionMCPClient(
  process.env.JURISDICTION_MCP_URL || "https://san-rafael.civicosproject.org/mcp"
);

// ─────────── Voice Interface Tool ───────────

const voiceResourceUri = "ui://civicos/voice";

registerAppTool(
  server,
  "voice_interface",
  {
    title: "Cast Voice on Civic Item",
    description: `
      Open an interactive voice-casting interface for a civic decision or initiative.
      Users can support, oppose, or watch items with real-time community counts.

      Use this when someone wants to:
      - Express support or opposition to a city council decision
      - See how many others have voiced on an item
      - Track a civic matter they care about
    `,
    inputSchema: {
      type: "object",
      properties: {
        entity_id: {
          type: "string",
          description: "Entity identifier (e.g., 'decision:city-san-rafael:2026-01-15:item-5a')",
        },
        context: {
          type: "string",
          description: "Optional context about what this item is (for display in widget)",
        },
      },
      required: ["entity_id"],
    },
    _meta: {
      ui: {
        resourceUri: voiceResourceUri,
        // Request no special permissions - widget is read/write via tool calls only
      }
    },
  },
  async (args) => {
    // Fetch current voice counts from jurisdiction MCP
    const counts = await jurisdictionClient.callTool("get_voice_counts", {
      entity: args.entity_id,
    });

    // Parse the response (jurisdiction MCP returns formatted text)
    const parsed = parseVoiceCounts(counts);

    // Return structured data for the widget
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({
            entity_id: args.entity_id,
            context: args.context || "",
            counts: parsed,
            relay_url: process.env.RELAY_URL || "https://api.civicosproject.org",
          }),
        },
      ],
    };
  }
);

// ─────────── Voice Resource (HTML Widget) ───────────

registerAppResource(
  server,
  voiceResourceUri,
  voiceResourceUri,
  { mimeType: RESOURCE_MIME_TYPE },
  async () => {
    const html = await fs.readFile(
      path.join(import.meta.dirname, "dist", "voice-widget.html"),
      "utf-8"
    );
    return {
      contents: [
        { uri: voiceResourceUri, mimeType: RESOURCE_MIME_TYPE, text: html },
      ],
    };
  }
);

// ─────────── Broadcast Voice Tool (called from widget) ───────────

registerAppTool(
  server,
  "broadcast_voice_signed",
  {
    title: "Broadcast Signed Voice",
    description: "Submit a cryptographically signed voice to the relay. Called by the voice widget after local signing.",
    inputSchema: {
      type: "object",
      properties: {
        entity: { type: "string" },
        stance: { type: "string", enum: ["support", "oppose", "watching"] },
        public_key: { type: "string" },
        signature: { type: "string" },
      },
      required: ["entity", "stance", "public_key", "signature"],
    },
    // No UI - this is called programmatically by the widget
  },
  async (args) => {
    // Forward to jurisdiction MCP
    const result = await jurisdictionClient.callTool("broadcast_voice", args);
    return { content: [{ type: "text", text: result }] };
  }
);

// ─────────── HTTP Server ───────────

const app = express();
app.use(cors());
app.use(express.json());

app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

const port = process.env.PORT || 3002;
app.listen(port, () => {
  console.log(`CivicOS Voice MCP Apps server listening on http://localhost:${port}/mcp`);
});

// ─────────── Helpers ───────────

function parseVoiceCounts(text: string): { support: number; oppose: number; watching: number } {
  // Parse the formatted text response from jurisdiction MCP
  // Example: "Support: 47 | Oppose: 12 | Watching: 89"
  const counts = { support: 0, oppose: 0, watching: 0 };
  const supportMatch = text.match(/support[:\s]+(\d+)/i);
  const opposeMatch = text.match(/oppose[:\s]+(\d+)/i);
  const watchingMatch = text.match(/watch(?:ing)?[:\s]+(\d+)/i);

  if (supportMatch) counts.support = parseInt(supportMatch[1], 10);
  if (opposeMatch) counts.oppose = parseInt(opposeMatch[1], 10);
  if (watchingMatch) counts.watching = parseInt(watchingMatch[1], 10);

  return counts;
}
```

### Phase 3: Vue Widget Implementation

```html
<!-- src/voice-widget.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CivicOS Voice</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      padding: 16px;
      background: #fafafa;
    }
    .voice-widget {
      max-width: 400px;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      padding: 20px;
    }
    .entity-info {
      margin-bottom: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid #eee;
    }
    .entity-title {
      font-size: 16px;
      font-weight: 600;
      color: #1a1a1a;
      margin-bottom: 4px;
    }
    .entity-context {
      font-size: 13px;
      color: #666;
    }
    .voice-buttons {
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
    }
    .voice-btn {
      flex: 1;
      padding: 16px 12px;
      border: 2px solid #e0e0e0;
      border-radius: 8px;
      background: white;
      cursor: pointer;
      transition: all 0.2s;
      text-align: center;
    }
    .voice-btn:hover {
      border-color: #999;
    }
    .voice-btn.selected {
      border-color: currentColor;
      background: currentColor;
    }
    .voice-btn.selected .btn-label,
    .voice-btn.selected .btn-count {
      color: white;
    }
    .voice-btn.support { color: #22c55e; }
    .voice-btn.oppose { color: #ef4444; }
    .voice-btn.watching { color: #3b82f6; }
    .btn-label {
      font-size: 14px;
      font-weight: 500;
      color: #333;
      margin-bottom: 4px;
    }
    .btn-count {
      font-size: 24px;
      font-weight: 700;
      color: #1a1a1a;
    }
    .identity-section {
      margin-bottom: 16px;
      padding: 12px;
      background: #f5f5f5;
      border-radius: 8px;
    }
    .identity-label {
      font-size: 12px;
      color: #666;
      margin-bottom: 8px;
    }
    .identity-options {
      display: flex;
      gap: 16px;
    }
    .identity-option {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-size: 13px;
    }
    .identity-option input {
      accent-color: #3b82f6;
    }
    .cast-btn {
      width: 100%;
      padding: 14px;
      background: #3b82f6;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .cast-btn:hover:not(:disabled) {
      background: #2563eb;
    }
    .cast-btn:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
    .status {
      margin-top: 12px;
      padding: 10px;
      border-radius: 6px;
      font-size: 13px;
      text-align: center;
    }
    .status.success {
      background: #dcfce7;
      color: #166534;
    }
    .status.error {
      background: #fee2e2;
      color: #991b1b;
    }
    .status.loading {
      background: #e0f2fe;
      color: #0369a1;
    }
  </style>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/voice-widget.ts"></script>
</body>
</html>
```

```typescript
// src/voice-widget.ts
import { App } from "@modelcontextprotocol/ext-apps";
import { createApp, ref, computed, onMounted } from "vue";

// Initialize MCP Apps connection
const mcpApp = new App({ name: "CivicOS Voice", version: "1.0.0" });

// Vue component
const VoiceWidget = {
  setup() {
    // State
    const entityId = ref("");
    const context = ref("");
    const counts = ref({ support: 0, oppose: 0, watching: 0 });
    const selectedStance = ref<"support" | "oppose" | "watching" | null>(null);
    const identityMode = ref<"anonymous" | "verified">("anonymous");
    const status = ref<{ type: "success" | "error" | "loading"; message: string } | null>(null);
    const isSubmitting = ref(false);

    // Computed
    const canCast = computed(() => selectedStance.value !== null && !isSubmitting.value);
    const buttonText = computed(() => {
      if (isSubmitting.value) return "Casting...";
      if (!selectedStance.value) return "Select a position";
      return `Cast ${selectedStance.value.charAt(0).toUpperCase() + selectedStance.value.slice(1)} Voice`;
    });

    // Handle initial tool result
    mcpApp.ontoolresult = (result) => {
      try {
        const data = JSON.parse(result.content?.find((c) => c.type === "text")?.text || "{}");
        entityId.value = data.entity_id || "";
        context.value = data.context || "";
        counts.value = data.counts || { support: 0, oppose: 0, watching: 0 };
      } catch (e) {
        console.error("Failed to parse tool result:", e);
        status.value = { type: "error", message: "Failed to load voice data" };
      }
    };

    // Cast voice
    const castVoice = async () => {
      if (!selectedStance.value || !entityId.value) return;

      isSubmitting.value = true;
      status.value = { type: "loading", message: "Signing and broadcasting..." };

      try {
        if (identityMode.value === "verified") {
          // Use WebAuthn/passkey for signing
          const { publicKey, signature } = await signWithPasskey(entityId.value, selectedStance.value);

          // Call broadcast tool
          const result = await mcpApp.callServerTool({
            name: "broadcast_voice_signed",
            arguments: {
              entity: entityId.value,
              stance: selectedStance.value,
              public_key: publicKey,
              signature: signature,
            },
          });

          // Update counts optimistically
          counts.value[selectedStance.value]++;
          status.value = { type: "success", message: "Voice cast successfully!" };
        } else {
          // Anonymous mode - still broadcast but with ephemeral key
          const { publicKey, signature } = await signWithEphemeralKey(entityId.value, selectedStance.value);

          await mcpApp.callServerTool({
            name: "broadcast_voice_signed",
            arguments: {
              entity: entityId.value,
              stance: selectedStance.value,
              public_key: publicKey,
              signature: signature,
            },
          });

          counts.value[selectedStance.value]++;
          status.value = { type: "success", message: "Anonymous voice cast!" };
        }
      } catch (error: any) {
        console.error("Failed to cast voice:", error);
        status.value = { type: "error", message: error.message || "Failed to cast voice" };
      } finally {
        isSubmitting.value = false;
      }
    };

    // Connect to host on mount
    onMounted(() => {
      mcpApp.connect();
    });

    return {
      entityId,
      context,
      counts,
      selectedStance,
      identityMode,
      status,
      canCast,
      buttonText,
      castVoice,
    };
  },

  template: `
    <div class="voice-widget">
      <div class="entity-info">
        <div class="entity-title">{{ entityId }}</div>
        <div class="entity-context" v-if="context">{{ context }}</div>
      </div>

      <div class="voice-buttons">
        <button
          class="voice-btn support"
          :class="{ selected: selectedStance === 'support' }"
          @click="selectedStance = 'support'"
        >
          <div class="btn-label">Support</div>
          <div class="btn-count">{{ counts.support }}</div>
        </button>

        <button
          class="voice-btn oppose"
          :class="{ selected: selectedStance === 'oppose' }"
          @click="selectedStance = 'oppose'"
        >
          <div class="btn-label">Oppose</div>
          <div class="btn-count">{{ counts.oppose }}</div>
        </button>

        <button
          class="voice-btn watching"
          :class="{ selected: selectedStance === 'watching' }"
          @click="selectedStance = 'watching'"
        >
          <div class="btn-label">Watch</div>
          <div class="btn-count">{{ counts.watching }}</div>
        </button>
      </div>

      <div class="identity-section">
        <div class="identity-label">Identity Mode</div>
        <div class="identity-options">
          <label class="identity-option">
            <input type="radio" v-model="identityMode" value="anonymous">
            Anonymous
          </label>
          <label class="identity-option">
            <input type="radio" v-model="identityMode" value="verified">
            Verified (TouchID/Passkey)
          </label>
        </div>
      </div>

      <button
        class="cast-btn"
        :disabled="!canCast"
        @click="castVoice"
      >
        {{ buttonText }}
      </button>

      <div v-if="status" class="status" :class="status.type">
        {{ status.message }}
      </div>
    </div>
  `,
};

// Signing helpers (simplified - full impl in personal-mcp)
async function signWithPasskey(entity: string, stance: string): Promise<{ publicKey: string; signature: string }> {
  // Use WebAuthn to sign
  const challenge = new TextEncoder().encode(`voice:${entity}:${stance}:${Date.now()}`);

  const credential = await navigator.credentials.get({
    publicKey: {
      challenge,
      rpId: window.location.hostname,
      userVerification: "required",
    },
  }) as PublicKeyCredential;

  const response = credential.response as AuthenticatorAssertionResponse;

  return {
    publicKey: bufferToHex(response.authenticatorData),
    signature: bufferToHex(response.signature),
  };
}

async function signWithEphemeralKey(entity: string, stance: string): Promise<{ publicKey: string; signature: string }> {
  // Generate ephemeral keypair for anonymous voice
  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    true,
    ["sign"]
  );

  const message = new TextEncoder().encode(`voice:${entity}:${stance}:${Date.now()}`);
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    keyPair.privateKey,
    message
  );

  const publicKeyRaw = await crypto.subtle.exportKey("raw", keyPair.publicKey);

  return {
    publicKey: bufferToHex(publicKeyRaw),
    signature: bufferToHex(signature),
  };
}

function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// Mount Vue app
createApp(VoiceWidget).mount("#app");
```

### Phase 4: Build Configuration

```json
// package.json
{
  "name": "civicos-mcp-apps",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "vite build",
    "serve": "tsx server.ts",
    "dev": "npm run build && npm run serve"
  },
  "dependencies": {
    "@modelcontextprotocol/ext-apps": "^1.0.0",
    "@modelcontextprotocol/sdk": "^1.0.0",
    "cors": "^2.8.5",
    "express": "^4.18.2",
    "vue": "^3.4.0"
  },
  "devDependencies": {
    "@types/cors": "^2.8.17",
    "@types/express": "^4.17.21",
    "@vitejs/plugin-vue": "^5.0.0",
    "tsx": "^4.7.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vite-plugin-singlefile": "^2.0.0"
  }
}
```

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  build: {
    outDir: "dist",
    rollupOptions: {
      input: "src/voice-widget.html",
    },
  },
});
```

---

## Deployment

### Option 1: Separate Modal App

```python
# modal_app.py
import modal

app = modal.App("civicos-mcp-apps")

@app.function(
    image=modal.Image.debian_slim().pip_install("nodejs"),
    secrets=[modal.Secret.from_name("civicos-env")],
)
@modal.web_endpoint(method="POST")
async def mcp_endpoint(request):
    # Run Node.js server
    pass
```

### Option 2: Add to Existing Cloudflare Worker

Route `/mcp-apps/*` to the TypeScript MCP Apps server while keeping `/mcp` for the Python jurisdiction MCP.

### Option 3: Unified Deployment (Recommended for Pilot)

Add MCP Apps server as a separate Modal function alongside the existing Python MCP:

```
san-rafael.civicosproject.org/mcp      → Python Jurisdiction MCP (existing)
san-rafael.civicosproject.org/apps     → TypeScript MCP Apps (new)
```

---

## Integration with Personal MCP

For full identity management, the widget can delegate to Personal MCP:

```typescript
// Instead of local signing, call Personal MCP
const result = await mcpApp.callServerTool({
  name: "sign_and_broadcast_voice",  // Personal MCP tool
  arguments: {
    entity: entityId.value,
    stance: selectedStance.value,
  },
});
```

This keeps the signing flow in Personal MCP where the identity provider lives.

---

## Testing

### Local Development

```bash
cd apps/civicos-mcp-apps
npm install
npm run dev

# In another terminal, expose via cloudflared
npx cloudflared tunnel --url http://localhost:3002
```

### Test with basic-host

```bash
git clone https://github.com/modelcontextprotocol/ext-apps
cd ext-apps/examples/basic-host
SERVERS='["http://localhost:3002/mcp"]' npm start
# Open http://localhost:8080
```

### Test with Claude.ai

1. Add cloudflared URL as custom connector in Claude settings
2. Start new conversation: "Show me the voice interface for decision:city-san-rafael:2026-01-15:item-5a"
3. Widget should render inline

---

## Next Steps

1. **Scaffold project** - Create `apps/civicos-mcp-apps/` directory structure
2. **Implement server** - TypeScript MCP server with voice tools
3. **Build widget** - Vue component with signing
4. **Test locally** - basic-host + cloudflared
5. **Deploy** - Modal or Cloudflare Worker
6. **Integrate** - Connect to Personal MCP for verified identity

---

## Future Widgets

Once the pattern is established, additional widgets:

| Widget | Tool | Use Case |
|--------|------|----------|
| Meeting Prep | `meeting_prep_interface` | Interactive agenda with decision history |
| Issue Card | `issue_detail_interface` | Follow button, map, similar issues |
| Initiative Dashboard | `initiative_interface` | Create/track initiatives |
| Budget Explorer | `budget_interface` | Interactive budget visualization |
| Public Comment | `comment_interface` | Draft + submit public comments |

Each follows the same pattern: tool with `_meta.ui.resourceUri`, bundled HTML resource, bidirectional communication.
