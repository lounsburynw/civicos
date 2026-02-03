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
import type { IdentityTier, NostrEvent, ContextStorage, StoredUserContext, FollowableEntityType } from '../lib/providers/index.js';
import {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
  LocalStorageContextStorage,
  createDefaultContext,
} from '../lib/providers/index.js';
import {
  JurisdictionMCPClient,
  type JurisdictionMCPClientConfig,
} from '../lib/jurisdiction-mcp-client.js';

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
  contextStorage?: ContextStorage;
  jurisdictionMCPConfig?: JurisdictionMCPClientConfig;
  jurisdictionMCPClient?: JurisdictionMCPClient;
}

/**
 * Personal MCP HTTP Server
 *
 * Exposes the Personal MCP tools via HTTP JSON-RPC.
 */
export class PersonalMCPHttpServer {
  private app: express.Application;
  private identityManager: IdentityManager;
  private contextStorage: ContextStorage;
  private jurisdictionClient: JurisdictionMCPClient;
  private config: HttpServerConfig;

  constructor(config: HttpServerConfig = {}) {
    this.config = {
      port: config.port ?? 8081,
      corsOrigins: config.corsOrigins ?? ['*'],
      ...config,
    };

    this.identityManager = new IdentityManager(config.identityConfig);
    this.contextStorage = config.contextStorage ?? new LocalStorageContextStorage();
    this.jurisdictionClient = config.jurisdictionMCPClient ?? new JurisdictionMCPClient(config.jurisdictionMCPConfig);
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
      // Context personalization tools
      {
        name: 'set_neighborhood',
        description:
          'Set your neighborhood location. Used for proximity-based filtering of civic information.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            neighborhood: {
              type: 'string',
              description: 'Neighborhood name (e.g., "Terra Linda", "Downtown")',
            },
            lat: {
              type: 'number',
              description: 'Optional latitude coordinate',
            },
            lng: {
              type: 'number',
              description: 'Optional longitude coordinate',
            },
          },
          required: ['jurisdiction', 'neighborhood'],
        },
      },
      {
        name: 'set_interests',
        description:
          'Set your civic interest topics. Used to filter and prioritize relevant information.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            interests: {
              type: 'array',
              items: { type: 'string' },
              description:
                'Topic interests (e.g., ["housing", "transportation", "parks"])',
            },
          },
          required: ['jurisdiction', 'interests'],
        },
      },
      {
        name: 'follow_item',
        description:
          'Follow a specific civic item to track updates. Can follow decisions, meetings, issues, or topics.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            entity_type: {
              type: 'string',
              enum: ['decision', 'meeting', 'issue', 'topic'],
              description: 'Type of item to follow',
            },
            entity_id: {
              type: 'string',
              description: 'Item identifier (e.g., "decision:2026-01-15:item-6a")',
            },
            label: {
              type: 'string',
              description: 'Optional human-readable label for the item',
            },
          },
          required: ['jurisdiction', 'entity_type', 'entity_id'],
        },
      },
      {
        name: 'unfollow_item',
        description: 'Stop following a civic item.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            entity_id: {
              type: 'string',
              description: 'Item identifier to unfollow',
            },
          },
          required: ['jurisdiction', 'entity_id'],
        },
      },
      {
        name: 'get_context',
        description:
          'Get your current civic context settings including neighborhood, interests, and followed items.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
          },
          required: ['jurisdiction'],
        },
      },
      // Personalized query tools
      {
        name: 'get_relevant_now',
        description:
          'Get civic items relevant to you right now, filtered by your interests and neighborhood. Returns upcoming meetings, recent decisions, and trending issues that match your personalization settings.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
          },
          required: ['jurisdiction'],
        },
      },
      {
        name: 'get_suggestions',
        description:
          'Get proactive civic recommendations based on your interests and followed items. Suggests opportunities for engagement, related issues, and upcoming events you might care about.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
          },
          required: ['jurisdiction'],
        },
      },
      {
        name: 'explain_relevance',
        description:
          'Explain why a specific civic item matters to you based on your interests, neighborhood, and followed items.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            item_id: {
              type: 'string',
              description: 'Item identifier (e.g., "decision:2026-01-15:item-6a")',
            },
            item_type: {
              type: 'string',
              enum: ['decision', 'meeting', 'issue'],
              description: 'Type of the item',
            },
            item_title: {
              type: 'string',
              description: 'Title or summary of the item',
            },
            item_topics: {
              type: 'array',
              items: { type: 'string' },
              description: 'Topics associated with the item',
            },
          },
          required: ['jurisdiction', 'item_id'],
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

      // Context personalization tools
      case 'set_neighborhood':
        return this.handleSetNeighborhood(
          args.jurisdiction as string,
          args.neighborhood as string,
          args.lat as number | undefined,
          args.lng as number | undefined
        );

      case 'set_interests':
        return this.handleSetInterests(
          args.jurisdiction as string,
          args.interests as string[]
        );

      case 'follow_item':
        return this.handleFollowItem(
          args.jurisdiction as string,
          args.entity_type as FollowableEntityType,
          args.entity_id as string,
          args.label as string | undefined
        );

      case 'unfollow_item':
        return this.handleUnfollowItem(
          args.jurisdiction as string,
          args.entity_id as string
        );

      case 'get_context':
        return this.handleGetContext(args.jurisdiction as string);

      // Personalized query tools
      case 'get_relevant_now':
        return this.handleGetRelevantNow(args.jurisdiction as string);

      case 'get_suggestions':
        return this.handleGetSuggestions(args.jurisdiction as string);

      case 'explain_relevance':
        return this.handleExplainRelevance(
          args.jurisdiction as string,
          args.item_id as string,
          args.item_type as 'decision' | 'meeting' | 'issue' | undefined,
          args.item_title as string | undefined,
          args.item_topics as string[] | undefined
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

  // Context personalization handlers

  private async handleSetNeighborhood(
    jurisdiction: string,
    neighborhood: string,
    lat?: number,
    lng?: number
  ): Promise<unknown> {
    let context = await this.contextStorage.load(jurisdiction);
    if (!context) {
      context = createDefaultContext(jurisdiction);
    }

    context.neighborhood = { neighborhood, lat, lng };
    context.updated_at = Date.now();

    await this.contextStorage.save(jurisdiction, context);

    return {
      success: true,
      message: `Neighborhood set to "${neighborhood}" for ${jurisdiction}`,
      neighborhood: context.neighborhood,
    };
  }

  private async handleSetInterests(
    jurisdiction: string,
    interests: string[]
  ): Promise<unknown> {
    let context = await this.contextStorage.load(jurisdiction);
    if (!context) {
      context = createDefaultContext(jurisdiction);
    }

    // Normalize interests: lowercase, trim, deduplicate
    const normalizedInterests = [...new Set(interests.map((i) => i.toLowerCase().trim()))];
    context.interests = normalizedInterests;
    context.updated_at = Date.now();

    await this.contextStorage.save(jurisdiction, context);

    return {
      success: true,
      message: `Interests updated for ${jurisdiction}`,
      interests: context.interests,
    };
  }

  private async handleFollowItem(
    jurisdiction: string,
    entityType: FollowableEntityType,
    entityId: string,
    label?: string
  ): Promise<unknown> {
    let context = await this.contextStorage.load(jurisdiction);
    if (!context) {
      context = createDefaultContext(jurisdiction);
    }

    // Check if already following
    const existingIndex = context.following_items.findIndex(
      (item) => item.entity_id === entityId
    );

    if (existingIndex >= 0) {
      // Update existing item
      context.following_items[existingIndex] = {
        entity_type: entityType,
        entity_id: entityId,
        label,
        followed_at: context.following_items[existingIndex].followed_at,
      };
    } else {
      // Add new item
      context.following_items.push({
        entity_type: entityType,
        entity_id: entityId,
        label,
        followed_at: Date.now(),
      });
    }

    context.updated_at = Date.now();
    await this.contextStorage.save(jurisdiction, context);

    return {
      success: true,
      message: `Now following ${entityType}: ${entityId}`,
      item: context.following_items.find((i) => i.entity_id === entityId),
      total_following: context.following_items.length,
    };
  }

  private async handleUnfollowItem(
    jurisdiction: string,
    entityId: string
  ): Promise<unknown> {
    const context = await this.contextStorage.load(jurisdiction);
    if (!context) {
      return {
        success: false,
        error: `No context found for ${jurisdiction}`,
      };
    }

    const initialLength = context.following_items.length;
    context.following_items = context.following_items.filter(
      (item) => item.entity_id !== entityId
    );

    if (context.following_items.length === initialLength) {
      return {
        success: false,
        error: `Item not found: ${entityId}`,
      };
    }

    context.updated_at = Date.now();
    await this.contextStorage.save(jurisdiction, context);

    return {
      success: true,
      message: `Unfollowed: ${entityId}`,
      total_following: context.following_items.length,
    };
  }

  private async handleGetContext(jurisdiction: string): Promise<unknown> {
    const context = await this.contextStorage.load(jurisdiction);

    if (!context) {
      return {
        jurisdiction,
        hasContext: false,
        message: `No context saved for ${jurisdiction}. Use set_neighborhood, set_interests, or follow_item to personalize.`,
      };
    }

    return {
      jurisdiction,
      hasContext: true,
      neighborhood: context.neighborhood,
      interests: context.interests,
      following_items: context.following_items,
      created_at: new Date(context.created_at).toISOString(),
      updated_at: new Date(context.updated_at).toISOString(),
    };
  }

  // Personalized query handlers

  private async handleGetRelevantNow(jurisdiction: string): Promise<unknown> {
    // Load user context
    const context = await this.contextStorage.load(jurisdiction);
    const hasContext = context && (context.interests.length > 0 || context.neighborhood);

    // Fetch city pulse from Jurisdiction MCP
    const pulse = await this.jurisdictionClient.getCityPulse(7, 30);

    if (!pulse) {
      return {
        success: false,
        error: 'Unable to connect to Jurisdiction MCP server. Make sure it is running.',
        suggestion: 'Start the API server with: ./scripts/dev.sh api',
      };
    }

    // If no personalization, return everything with a hint
    if (!hasContext) {
      return {
        success: true,
        personalized: false,
        message: 'Showing all items. Set interests and neighborhood to get personalized results.',
        upcoming_meetings: pulse.upcoming_meetings ?? [],
        recent_decisions: pulse.recent_decisions ?? [],
        trending_issues: pulse.trending_issues ?? [],
      };
    }

    // Apply personalization filters
    const interests = context.interests.map((i) => i.toLowerCase());
    const neighborhood = context.neighborhood?.neighborhood?.toLowerCase();

    // Filter meetings by agenda items matching interests
    const relevantMeetings = (pulse.upcoming_meetings ?? []).filter((meeting) => {
      if (!meeting.agenda_items || meeting.agenda_items.length === 0) return true;
      return meeting.agenda_items.some((item) =>
        interests.some((interest) => item.toLowerCase().includes(interest))
      );
    });

    // Filter decisions by topics matching interests
    const relevantDecisions = (pulse.recent_decisions ?? []).filter((decision) => {
      if (!decision.topics || decision.topics.length === 0) {
        // Check title for interest keywords
        return interests.some((interest) =>
          decision.title.toLowerCase().includes(interest)
        );
      }
      return decision.topics.some((topic) =>
        interests.some((interest) => topic.toLowerCase().includes(interest))
      );
    });

    // Filter issues by location (neighborhood) or type matching interests
    const relevantIssues = (pulse.trending_issues ?? []).filter((issue) => {
      const locationMatch = neighborhood && issue.location?.toLowerCase().includes(neighborhood);
      const typeMatch = interests.some((interest) =>
        issue.type.toLowerCase().includes(interest)
      );
      return locationMatch || typeMatch;
    });

    return {
      success: true,
      personalized: true,
      context_used: {
        interests: context.interests,
        neighborhood: context.neighborhood?.neighborhood,
      },
      upcoming_meetings: relevantMeetings,
      recent_decisions: relevantDecisions,
      trending_issues: relevantIssues,
      total_filtered: {
        meetings: `${relevantMeetings.length} of ${pulse.upcoming_meetings?.length ?? 0}`,
        decisions: `${relevantDecisions.length} of ${pulse.recent_decisions?.length ?? 0}`,
        issues: `${relevantIssues.length} of ${pulse.trending_issues?.length ?? 0}`,
      },
    };
  }

  private async handleGetSuggestions(jurisdiction: string): Promise<unknown> {
    // Load user context
    const context = await this.contextStorage.load(jurisdiction);

    if (!context || (context.interests.length === 0 && context.following_items.length === 0)) {
      return {
        success: true,
        suggestions: [],
        message: 'Set interests or follow items to get personalized suggestions.',
        setup_needed: true,
      };
    }

    const suggestions: Array<{
      type: 'opportunity' | 'trend' | 'follow_up' | 'related';
      title: string;
      reason: string;
      action?: string;
      item_id?: string;
    }> = [];

    // Generate suggestions based on interests
    for (const interest of context.interests.slice(0, 3)) {
      // Search for related meetings/decisions
      const history = await this.jurisdictionClient.searchMeetingHistory(interest, 3);

      if (history?.decisions && history.decisions.length > 0) {
        const latestDecision = history.decisions[0];
        suggestions.push({
          type: 'related',
          title: `Recent activity on "${interest}"`,
          reason: `Your interest in ${interest} matches: ${latestDecision.title}`,
          item_id: latestDecision.id,
          action: 'Review the decision and consider following for updates',
        });
      }

      // Search for related issues
      const issues = await this.jurisdictionClient.findSimilarIssues(interest, 5);

      if (issues?.issues && issues.issues.length > 0) {
        const openIssues = issues.issues.filter((i) => i.status === 'open');
        if (openIssues.length > 0) {
          suggestions.push({
            type: 'trend',
            title: `${openIssues.length} open issues related to "${interest}"`,
            reason: `Community members are reporting ${interest}-related issues`,
            action: 'View issues to understand community concerns',
          });
        }
      }
    }

    // Generate follow-up suggestions for followed items
    for (const followedItem of context.following_items.slice(0, 3)) {
      suggestions.push({
        type: 'follow_up',
        title: `Update on ${followedItem.label ?? followedItem.entity_id}`,
        reason: `You're following this ${followedItem.entity_type}`,
        item_id: followedItem.entity_id,
        action: 'Check for updates since you started following',
      });
    }

    // Check for upcoming meetings matching interests
    const meetings = await this.jurisdictionClient.getUpcomingMeetings(14);
    if (meetings && meetings.length > 0) {
      const interestKeywords = context.interests.map((i) => i.toLowerCase());
      for (const meeting of meetings.slice(0, 2)) {
        const agendaMatches = meeting.agenda_items?.some((item) =>
          interestKeywords.some((kw) => item.toLowerCase().includes(kw))
        );
        if (agendaMatches) {
          suggestions.push({
            type: 'opportunity',
            title: `Upcoming: ${meeting.title}`,
            reason: 'Agenda items match your interests',
            action: `Meeting on ${meeting.date} - consider attending or submitting comment`,
          });
        }
      }
    }

    return {
      success: true,
      suggestions: suggestions.slice(0, 5), // Limit to top 5 suggestions
      context_used: {
        interests: context.interests,
        following_count: context.following_items.length,
      },
    };
  }

  private async handleExplainRelevance(
    jurisdiction: string,
    itemId: string,
    itemType?: 'decision' | 'meeting' | 'issue',
    itemTitle?: string,
    itemTopics?: string[]
  ): Promise<unknown> {
    // Load user context
    const context = await this.contextStorage.load(jurisdiction);

    if (!context) {
      return {
        success: true,
        item_id: itemId,
        relevance_score: 0,
        explanations: [],
        message: 'No personalization context set. This item may still be relevant to you.',
      };
    }

    const explanations: string[] = [];
    let score = 0;

    const interests = context.interests.map((i) => i.toLowerCase());
    const neighborhood = context.neighborhood?.neighborhood?.toLowerCase();
    const followedIds = context.following_items.map((f) => f.entity_id);

    // Check if item is followed
    if (followedIds.includes(itemId)) {
      explanations.push('You are following this item');
      score += 0.4;
    }

    // Check topic matches
    if (itemTopics && itemTopics.length > 0) {
      const matchingTopics = itemTopics.filter((topic) =>
        interests.some((interest) => topic.toLowerCase().includes(interest))
      );
      if (matchingTopics.length > 0) {
        explanations.push(`Matches your interest in: ${matchingTopics.join(', ')}`);
        score += 0.3 * Math.min(matchingTopics.length, 3);
      }
    }

    // Check title for interest keywords
    if (itemTitle) {
      const titleLower = itemTitle.toLowerCase();
      const matchingInterests = interests.filter((interest) =>
        titleLower.includes(interest)
      );
      if (matchingInterests.length > 0 && explanations.length === 0) {
        explanations.push(`Title mentions your interests: ${matchingInterests.join(', ')}`);
        score += 0.2 * matchingInterests.length;
      }
    }

    // Check for neighborhood/location relevance (would need item location data)
    if (neighborhood && itemTitle?.toLowerCase().includes(neighborhood)) {
      explanations.push(`Located in your neighborhood: ${context.neighborhood?.neighborhood}`);
      score += 0.3;
    }

    // Check for followed items that might be related
    const relatedFollowed = context.following_items.filter((f) => {
      if (f.entity_type === itemType) return false; // Skip same type
      if (itemTopics && f.label) {
        return itemTopics.some((t) => f.label?.toLowerCase().includes(t.toLowerCase()));
      }
      return false;
    });

    if (relatedFollowed.length > 0) {
      explanations.push(
        `Related to items you follow: ${relatedFollowed.map((f) => f.label ?? f.entity_id).join(', ')}`
      );
      score += 0.1 * relatedFollowed.length;
    }

    // Cap score at 1.0
    score = Math.min(score, 1.0);

    return {
      success: true,
      item_id: itemId,
      item_type: itemType,
      relevance_score: Math.round(score * 100) / 100,
      explanations,
      context_used: {
        interests: context.interests,
        neighborhood: context.neighborhood?.neighborhood,
        following_count: context.following_items.length,
      },
      verdict:
        score >= 0.5
          ? 'Highly relevant to your interests'
          : score >= 0.2
            ? 'Somewhat relevant to your interests'
            : 'May not directly match your stated interests',
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
