/**
 * Personal MCP HTTP Server
 *
 * HTTP/SSE transport for Personal MCP, enabling Open WebUI integration.
 * Translates HTTP JSON-RPC requests to MCP protocol.
 *
 * Endpoints:
 * - GET /health - Health check
 * - POST /mcp - MCP JSON-RPC endpoint
 *
 * See docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md for design.
 */

import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import { IdentityManager, type IdentityManagerConfig } from './identity.js';
import type { IdentityTier, NostrEvent } from '../lib/providers/index.js';
import {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
} from '../lib/providers/index.js';

const VERSION = '0.1.0';

/**
 * MCP Tool definition (matches SDK types)
 */
interface Tool {
  name: string;
  description: string;
  inputSchema: {
    type: 'object';
    properties: Record<string, unknown>;
    required: string[];
  };
}

/**
 * JSON-RPC 2.0 request
 */
interface JsonRpcRequest {
  jsonrpc: '2.0';
  method: string;
  params?: Record<string, unknown>;
  id: string | number | null;
}

/**
 * JSON-RPC 2.0 response
 */
interface JsonRpcResponse {
  jsonrpc: '2.0';
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
  id: string | number | null;
}

/**
 * HTTP server configuration
 */
export interface HttpServerConfig {
  port?: number;
  corsOrigins?: string[];
  identityConfig?: IdentityManagerConfig;
}

/**
 * Personal MCP HTTP Server
 *
 * Exposes the Personal MCP tools via HTTP JSON-RPC.
 */
export class PersonalMCPHttpServer {
  private app: express.Application;
  private identityManager: IdentityManager;
  private config: HttpServerConfig;

  constructor(config: HttpServerConfig = {}) {
    this.config = {
      port: config.port ?? 8081,
      corsOrigins: config.corsOrigins ?? ['*'],
      ...config,
    };

    this.identityManager = new IdentityManager(config.identityConfig);
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
  }

  private setupMiddleware(): void {
    // CORS for Open WebUI
    this.app.use(cors({
      origin: this.config.corsOrigins,
      methods: ['GET', 'POST', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'Authorization'],
    }));

    // JSON body parser
    this.app.use(express.json());

    // Request logging
    this.app.use((req: Request, _res: Response, next: NextFunction) => {
      console.error(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
      next();
    });
  }

  private setupRoutes(): void {
    // Health check
    this.app.get('/health', (_req: Request, res: Response) => {
      res.json({
        status: 'healthy',
        server: 'civicos-personal-mcp',
        version: VERSION,
        transport: 'http',
        tools: this.getTools().length,
      });
    });

    // MCP JSON-RPC endpoint
    this.app.post('/mcp', async (req: Request, res: Response) => {
      try {
        const response = await this.handleJsonRpc(req.body as JsonRpcRequest);
        res.json(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Internal error';
        res.status(500).json({
          jsonrpc: '2.0',
          error: { code: -32603, message },
          id: null,
        });
      }
    });

    // 404 handler
    this.app.use((_req: Request, res: Response) => {
      res.status(404).json({ error: 'Not found' });
    });
  }

  private async handleJsonRpc(request: JsonRpcRequest): Promise<JsonRpcResponse> {
    const { method, params, id } = request;

    switch (method) {
      case 'initialize':
        return {
          jsonrpc: '2.0',
          result: {
            protocolVersion: '2024-11-05',
            capabilities: { tools: {} },
            serverInfo: {
              name: 'civicos-personal-mcp',
              version: VERSION,
            },
          },
          id,
        };

      case 'tools/list':
        return {
          jsonrpc: '2.0',
          result: { tools: this.getTools() },
          id,
        };

      case 'tools/call': {
        const toolParams = params as { name: string; arguments?: Record<string, unknown> } | undefined;
        if (!toolParams?.name) {
          return {
            jsonrpc: '2.0',
            error: { code: -32602, message: 'Missing tool name' },
            id,
          };
        }
        const result = await this.handleToolCall(toolParams.name, toolParams.arguments ?? {});
        return {
          jsonrpc: '2.0',
          result,
          id,
        };
      }

      case 'resources/list':
        return {
          jsonrpc: '2.0',
          result: { resources: [] },
          id,
        };

      case 'prompts/list':
        return {
          jsonrpc: '2.0',
          result: { prompts: [] },
          id,
        };

      default:
        return {
          jsonrpc: '2.0',
          error: { code: -32601, message: `Method not found: ${method}` },
          id,
        };
    }
  }

  private getTools(): Tool[] {
    return [
      {
        name: 'identity_status',
        description:
          'Check current identity status. Returns tier (easy/private/sovereign), public key, npub, and lock status.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      {
        name: 'identity_create',
        description:
          'Create a new identity. For "private" tier, returns a 12-word recovery phrase that MUST be shown to the user for backup. The identity is automatically unlocked after creation.',
        inputSchema: {
          type: 'object',
          properties: {
            tier: {
              type: 'string',
              enum: ['private'],
              description: 'Identity tier. Currently only "private" is supported.',
            },
            password: {
              type: 'string',
              description: 'Password to encrypt the identity (required for private tier)',
            },
          },
          required: ['tier', 'password'],
        },
      },
      {
        name: 'identity_import',
        description:
          'Import an existing identity from a 12-word recovery phrase. The identity is automatically unlocked after import.',
        inputSchema: {
          type: 'object',
          properties: {
            tier: {
              type: 'string',
              enum: ['private'],
              description: 'Identity tier. Currently only "private" is supported.',
            },
            password: {
              type: 'string',
              description: 'Password to encrypt the identity',
            },
            mnemonic: {
              type: 'string',
              description: '12-word recovery phrase',
            },
          },
          required: ['tier', 'password', 'mnemonic'],
        },
      },
      {
        name: 'identity_unlock',
        description: 'Unlock the identity with password. Required before signing.',
        inputSchema: {
          type: 'object',
          properties: {
            password: {
              type: 'string',
              description: 'Password to decrypt the identity',
            },
          },
          required: ['password'],
        },
      },
      {
        name: 'identity_lock',
        description: 'Lock the identity. Clears keys from memory.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      {
        name: 'sign_voice',
        description:
          'Sign a civic voice event (support/oppose/watching on a decision). Returns a signed Nostr event ready to broadcast.',
        inputSchema: {
          type: 'object',
          properties: {
            entity: {
              type: 'string',
              description:
                'Entity identifier (e.g., "decision:city-san-rafael:2026-01-15:item-6a")',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            stance: {
              type: 'string',
              enum: ['support', 'oppose', 'watching'],
              description: 'Your position on this entity',
            },
          },
          required: ['entity', 'jurisdiction', 'stance'],
        },
      },
      {
        name: 'sign_commitment',
        description:
          'Sign a commitment to take a civic action. Returns a signed Nostr event (kind 30801) ready to broadcast to the relay.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: {
              type: 'string',
              description:
                'Action identifier (e.g., "action:city-san-rafael:initiative-123:comment")',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
          },
          required: ['action_id', 'jurisdiction'],
        },
      },
      {
        name: 'sign_completion',
        description:
          'Sign a completion report for a civic action. Returns a signed Nostr event (kind 30802) ready to broadcast to the relay.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: {
              type: 'string',
              description:
                'Action identifier (e.g., "action:city-san-rafael:initiative-123:comment")',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            evidence_url: {
              type: 'string',
              description:
                'Optional URL to evidence of completion (e.g., link to submitted comment)',
            },
          },
          required: ['action_id', 'jurisdiction'],
        },
      },
      {
        name: 'sign_event',
        description:
          'Sign an arbitrary Nostr event. Use sign_voice, sign_commitment, or sign_completion for civic actions instead.',
        inputSchema: {
          type: 'object',
          properties: {
            kind: {
              type: 'number',
              description: 'Nostr event kind',
            },
            content: {
              type: 'string',
              description: 'Event content',
            },
            tags: {
              type: 'array',
              items: {
                type: 'array',
                items: { type: 'string' },
              },
              description: 'Event tags as array of arrays',
            },
          },
          required: ['kind', 'content'],
        },
      },
    ];
  }

  private async handleToolCall(
    name: string,
    args: Record<string, unknown>
  ): Promise<{ content: Array<{ type: 'text'; text: string }> }> {
    try {
      const result = await this.executeToolCall(name, args);
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      return {
        content: [{ type: 'text', text: JSON.stringify({ error: message }) }],
      };
    }
  }

  private async executeToolCall(
    name: string,
    args: Record<string, unknown>
  ): Promise<unknown> {
    switch (name) {
      case 'identity_status':
        return this.handleIdentityStatus();

      case 'identity_create':
        return this.handleIdentityCreate(
          args.tier as IdentityTier,
          args.password as string
        );

      case 'identity_import':
        return this.handleIdentityImport(
          args.tier as IdentityTier,
          args.password as string,
          args.mnemonic as string
        );

      case 'identity_unlock':
        return this.handleIdentityUnlock(args.password as string);

      case 'identity_lock':
        return this.handleIdentityLock();

      case 'sign_voice':
        return this.handleSignVoice(
          args.entity as string,
          args.jurisdiction as string,
          args.stance as 'support' | 'oppose' | 'watching'
        );

      case 'sign_commitment':
        return this.handleSignCommitment(
          args.action_id as string,
          args.jurisdiction as string
        );

      case 'sign_completion':
        return this.handleSignCompletion(
          args.action_id as string,
          args.jurisdiction as string,
          args.evidence_url as string | undefined
        );

      case 'sign_event':
        return this.handleSignEvent(
          args.kind as number,
          args.content as string,
          (args.tags as string[][]) ?? []
        );

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  }

  private async handleIdentityStatus(): Promise<unknown> {
    const provider = this.identityManager.getActiveProvider();
    if (!provider) {
      return {
        hasIdentity: false,
        message: 'No identity configured. Use identity_create or identity_import.',
      };
    }

    const identity = await provider.getIdentity();
    if (!identity) {
      return {
        hasIdentity: false,
        message: 'No identity configured. Use identity_create or identity_import.',
      };
    }

    return {
      hasIdentity: true,
      tier: identity.tier,
      publicKey: identity.publicKey,
      npub: identity.npub,
      isUnlocked: provider.isUnlocked(),
      createdAt: new Date(identity.createdAt).toISOString(),
    };
  }

  private async handleIdentityCreate(
    tier: IdentityTier,
    password: string
  ): Promise<unknown> {
    const result = await this.identityManager.createIdentity(tier, password);

    return {
      success: true,
      identity: {
        tier: result.identity.tier,
        publicKey: result.identity.publicKey,
        npub: result.identity.npub,
      },
      mnemonic: result.mnemonic,
      warning:
        'CRITICAL: Save this recovery phrase securely. It cannot be recovered if lost.',
    };
  }

  private async handleIdentityImport(
    tier: IdentityTier,
    password: string,
    mnemonic: string
  ): Promise<unknown> {
    const identity = await this.identityManager.importIdentity(tier, password, mnemonic);

    return {
      success: true,
      identity: {
        tier: identity.tier,
        publicKey: identity.publicKey,
        npub: identity.npub,
      },
    };
  }

  private async handleIdentityUnlock(password: string): Promise<unknown> {
    const success = await this.identityManager.unlock(password);

    if (success) {
      return { success: true, message: 'Identity unlocked' };
    } else {
      return { success: false, error: 'Incorrect password' };
    }
  }

  private handleIdentityLock(): unknown {
    this.identityManager.lock();
    return { success: true, message: 'Identity locked' };
  }

  private async handleSignVoice(
    entity: string,
    jurisdiction: string,
    stance: 'support' | 'oppose' | 'watching'
  ): Promise<unknown> {
    const timestamp = Math.floor(Date.now() / 1000);

    const event: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.VOICE,
      tags: createVoiceTags(entity, jurisdiction, stance),
      content: createVoiceContent(entity, stance, timestamp),
    };

    const result = await this.identityManager.signEvent(event);

    if (!result.success) {
      throw new Error(result.error ?? 'Signing failed');
    }

    return {
      success: true,
      event: result.event,
      message: `Voice signed: ${stance} on ${entity}`,
    };
  }

  private async handleSignCommitment(
    actionId: string,
    jurisdiction: string
  ): Promise<unknown> {
    const timestamp = Math.floor(Date.now() / 1000);

    const event: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.COMMITMENT,
      tags: createCommitmentTags(actionId, jurisdiction),
      content: createCommitmentContent(actionId, timestamp),
    };

    const result = await this.identityManager.signEvent(event);

    if (!result.success) {
      throw new Error(result.error ?? 'Signing failed');
    }

    return {
      success: true,
      event: result.event,
      message: `Commitment signed for action: ${actionId}`,
    };
  }

  private async handleSignCompletion(
    actionId: string,
    jurisdiction: string,
    evidenceUrl?: string
  ): Promise<unknown> {
    const timestamp = Math.floor(Date.now() / 1000);

    const event: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.COMPLETION,
      tags: createCompletionTags(actionId, jurisdiction, evidenceUrl),
      content: createCompletionContent(actionId, timestamp, evidenceUrl),
    };

    const result = await this.identityManager.signEvent(event);

    if (!result.success) {
      throw new Error(result.error ?? 'Signing failed');
    }

    return {
      success: true,
      event: result.event,
      message: `Completion signed for action: ${actionId}${evidenceUrl ? ` with evidence: ${evidenceUrl}` : ''}`,
    };
  }

  private async handleSignEvent(
    kind: number,
    content: string,
    tags: string[][]
  ): Promise<unknown> {
    const event: NostrEvent = {
      created_at: Math.floor(Date.now() / 1000),
      kind,
      tags,
      content,
    };

    const result = await this.identityManager.signEvent(event);

    if (!result.success) {
      throw new Error(result.error ?? 'Signing failed');
    }

    return {
      success: true,
      event: result.event,
    };
  }

  /**
   * Start the HTTP server.
   */
  async run(): Promise<void> {
    const port = this.config.port;
    this.app.listen(port, () => {
      console.error(`Personal MCP HTTP Server running on http://localhost:${port}`);
      console.error(`Health check: http://localhost:${port}/health`);
      console.error(`MCP endpoint: http://localhost:${port}/mcp`);
    });
  }

  /**
   * Get the Express app (for testing).
   */
  getApp(): express.Application {
    return this.app;
  }
}

// Main entry point for HTTP mode
if (process.argv[1]?.endsWith('http-server.js') || process.argv[1]?.endsWith('http-server.ts')) {
  const port = parseInt(process.env.PORT ?? '8081', 10);
  const server = new PersonalMCPHttpServer({ port });
  server.run().catch(console.error);
}
