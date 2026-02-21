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
import type { PersonalStorage } from '../lib/storage/index.js';
import { createPersonalStorage } from '../lib/storage/index.js';
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
  // Action event helpers (30810/30811/30812)
  generateActionId,
  generateCommitmentId,
  generateCompletionId,
  generateActionRef,
  createActionEventContent,
  createActionEventTags,
  createActionCommitmentContent,
  createActionCommitmentTags,
  createActionCompletionContent,
  createActionCompletionTags,
  CIVIC_ACTION_TYPES,
  EVIDENCE_TYPES,
  sha256Hex,
} from '../lib/providers/index.js';
import type { CivicActionType, EvidenceType } from '../lib/providers/index.js';
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
  /** Optional PersonalStorage instance (creates default if not provided) */
  personalStorage?: PersonalStorage;
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
  private personalStorage: PersonalStorage | null;
  private jurisdictionClient: JurisdictionMCPClient;
  private config: HttpServerConfig;

  constructor(config: HttpServerConfig = {}) {
    this.config = {
      port: config.port ?? 8081,
      corsOrigins: config.corsOrigins ?? ['*'],
      ...config,
    };

    // If PersonalStorage is provided, use its delegates for identity and context
    this.personalStorage = config.personalStorage ?? null;

    if (this.personalStorage) {
      this.identityManager = new IdentityManager({
        ...config.identityConfig,
        storage: this.personalStorage.wallet,
        passkeyStorage: this.personalStorage.passkey,
      });
      this.contextStorage = config.contextStorage ?? this.personalStorage.context;
    } else {
      this.identityManager = new IdentityManager(config.identityConfig);
      this.contextStorage = config.contextStorage ?? new LocalStorageContextStorage();
    }

    this.jurisdictionClient = config.jurisdictionMCPClient ?? new JurisdictionMCPClient(config.jurisdictionMCPConfig);
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
  }

  private setupMiddleware(): void {
    // CORS for Open WebUI - set headers manually to ensure they're sent
    this.app.use((req: Request, res: Response, next: NextFunction) => {
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      res.setHeader('Access-Control-Allow-Credentials', 'true');

      // Handle preflight
      if (req.method === 'OPTIONS') {
        res.status(200).end();
        return;
      }
      next();
    });

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
        endpoints: {
          mcp: 'POST /mcp',
          health: 'GET /health',
          rest_api: '/api/*',
          openapi_spec: 'GET /openapi.json',
        },
      });
    });

    // OpenAPI spec endpoint
    this.app.get('/openapi.json', (_req: Request, res: Response) => {
      res.json(this.generateOpenAPISpec());
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

    // ─────────── REST API Endpoints for OpenAPI/Open WebUI ───────────

    // Identity endpoints
    this.app.get('/api/identity/status', async (_req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'identity_status', {});
    });

    this.app.post('/api/identity/create', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'identity_create', req.body);
    });

    this.app.post('/api/identity/import', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'identity_import', req.body);
    });

    this.app.post('/api/identity/unlock', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'identity_unlock', req.body);
    });

    this.app.post('/api/identity/lock', async (_req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'identity_lock', {});
    });

    // Signing endpoints
    this.app.post('/api/sign/voice', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'sign_voice', req.body);
    });

    this.app.post('/api/sign/commitment', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'sign_commitment', req.body);
    });

    this.app.post('/api/sign/completion', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'sign_completion', req.body);
    });

    this.app.post('/api/sign/event', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'sign_event', req.body);
    });

    // Context endpoints
    this.app.post('/api/context/neighborhood', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'set_neighborhood', req.body);
    });

    this.app.post('/api/context/interests', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'set_interests', req.body);
    });

    this.app.post('/api/context/follow', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'follow_item', req.body);
    });

    this.app.post('/api/context/unfollow', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'unfollow_item', req.body);
    });

    this.app.get('/api/context', async (req: Request, res: Response) => {
      const jurisdiction = (req.query.jurisdiction as string) || 'city-san-rafael';
      await this.handleRestEndpoint(res, 'get_context', { jurisdiction });
    });

    // Query endpoints
    this.app.get('/api/relevant-now', async (req: Request, res: Response) => {
      const jurisdiction = (req.query.jurisdiction as string) || 'city-san-rafael';
      await this.handleRestEndpoint(res, 'get_relevant_now', { jurisdiction });
    });

    this.app.get('/api/suggestions', async (req: Request, res: Response) => {
      const jurisdiction = (req.query.jurisdiction as string) || 'city-san-rafael';
      await this.handleRestEndpoint(res, 'get_suggestions', { jurisdiction });
    });

    this.app.post('/api/explain-relevance', async (req: Request, res: Response) => {
      await this.handleRestEndpoint(res, 'explain_relevance', req.body);
    });

    // 404 handler
    this.app.use((_req: Request, res: Response) => {
      res.status(404).json({ error: 'Not found' });
    });
  }

  private async handleRestEndpoint(
    res: Response,
    toolName: string,
    args: Record<string, unknown>
  ): Promise<void> {
    try {
      const result = await this.executeToolCall(toolName, args);
      res.json({ success: true, data: result, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      res.status(400).json({ success: false, data: null, error: message });
    }
  }

  private generateOpenAPISpec(): object {
    return {
      openapi: '3.1.0',
      info: {
        title: 'CivicOS Personal MCP',
        description: 'Personal civic identity and context management. Handles identity creation, signing civic actions, and personalization.',
        version: VERSION,
      },
      paths: {
        '/api/identity/status': {
          get: {
            tags: ['Identity'],
            summary: 'Get identity status',
            description: 'Check current identity status including tier, public key, and lock status.',
            operationId: 'identity_status',
            responses: { '200': { description: 'Identity status', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/identity/create': {
          post: {
            tags: ['Identity'],
            summary: 'Create identity',
            description: 'Create a new civic identity. For "easy" tier, uses passkeys. For "private" tier, uses password + recovery phrase.',
            operationId: 'identity_create',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/IdentityCreateRequest' } } }, required: true },
            responses: { '200': { description: 'Identity created', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/identity/unlock': {
          post: {
            tags: ['Identity'],
            summary: 'Unlock identity',
            description: 'Unlock identity for signing. Easy tier uses biometrics, private tier requires password.',
            operationId: 'identity_unlock',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/IdentityUnlockRequest' } } } },
            responses: { '200': { description: 'Identity unlocked', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/identity/lock': {
          post: {
            tags: ['Identity'],
            summary: 'Lock identity',
            description: 'Lock identity and clear keys from memory.',
            operationId: 'identity_lock',
            responses: { '200': { description: 'Identity locked', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/sign/voice': {
          post: {
            tags: ['Signing'],
            summary: 'Sign civic voice',
            description: 'Sign a civic voice event (support/oppose/watching on a decision).',
            operationId: 'sign_voice',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/SignVoiceRequest' } } }, required: true },
            responses: { '200': { description: 'Voice signed', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/sign/commitment': {
          post: {
            tags: ['Signing'],
            summary: 'Sign commitment',
            description: 'Sign a commitment to take a civic action.',
            operationId: 'sign_commitment',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/SignCommitmentRequest' } } }, required: true },
            responses: { '200': { description: 'Commitment signed', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/context/neighborhood': {
          post: {
            tags: ['Context'],
            summary: 'Set neighborhood',
            description: 'Set your neighborhood for proximity-based filtering.',
            operationId: 'set_neighborhood',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/SetNeighborhoodRequest' } } }, required: true },
            responses: { '200': { description: 'Neighborhood set', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/context/interests': {
          post: {
            tags: ['Context'],
            summary: 'Set interests',
            description: 'Set your civic interest topics for filtering.',
            operationId: 'set_interests',
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/SetInterestsRequest' } } }, required: true },
            responses: { '200': { description: 'Interests set', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/context': {
          get: {
            tags: ['Context'],
            summary: 'Get context',
            description: 'Get your current civic context settings.',
            operationId: 'get_context',
            parameters: [{ name: 'jurisdiction', in: 'query', schema: { type: 'string', default: 'city-san-rafael' } }],
            responses: { '200': { description: 'Context', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/relevant-now': {
          get: {
            tags: ['Queries'],
            summary: 'Get relevant items',
            description: 'Get civic items relevant to you right now, filtered by your interests.',
            operationId: 'get_relevant_now',
            parameters: [{ name: 'jurisdiction', in: 'query', schema: { type: 'string', default: 'city-san-rafael' } }],
            responses: { '200': { description: 'Relevant items', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
        '/api/suggestions': {
          get: {
            tags: ['Queries'],
            summary: 'Get suggestions',
            description: 'Get proactive civic recommendations based on your interests.',
            operationId: 'get_suggestions',
            parameters: [{ name: 'jurisdiction', in: 'query', schema: { type: 'string', default: 'city-san-rafael' } }],
            responses: { '200': { description: 'Suggestions', content: { 'application/json': { schema: { $ref: '#/components/schemas/ToolResponse' } } } } },
          },
        },
      },
      components: {
        schemas: {
          ToolResponse: {
            type: 'object',
            properties: {
              success: { type: 'boolean' },
              data: { type: 'object' },
              error: { type: 'string', nullable: true },
            },
          },
          IdentityCreateRequest: {
            type: 'object',
            properties: {
              tier: { type: 'string', enum: ['easy', 'private'], description: 'Identity tier' },
              password: { type: 'string', description: 'Password for private tier' },
              email: { type: 'string', description: 'Email for easy tier' },
            },
            required: ['tier'],
          },
          IdentityUnlockRequest: {
            type: 'object',
            properties: {
              password: { type: 'string', description: 'Password for private tier' },
            },
          },
          SignVoiceRequest: {
            type: 'object',
            properties: {
              entity: { type: 'string', description: 'Entity identifier' },
              jurisdiction: { type: 'string', description: 'Jurisdiction identifier' },
              stance: { type: 'string', enum: ['support', 'oppose', 'watching'] },
            },
            required: ['entity', 'jurisdiction', 'stance'],
          },
          SignCommitmentRequest: {
            type: 'object',
            properties: {
              action_id: { type: 'string', description: 'Action identifier' },
              jurisdiction: { type: 'string', description: 'Jurisdiction identifier' },
            },
            required: ['action_id', 'jurisdiction'],
          },
          SetNeighborhoodRequest: {
            type: 'object',
            properties: {
              jurisdiction: { type: 'string' },
              neighborhood: { type: 'string' },
              lat: { type: 'number' },
              lng: { type: 'number' },
            },
            required: ['jurisdiction', 'neighborhood'],
          },
          SetInterestsRequest: {
            type: 'object',
            properties: {
              jurisdiction: { type: 'string' },
              interests: { type: 'array', items: { type: 'string' } },
            },
            required: ['jurisdiction', 'interests'],
          },
        },
      },
    };
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
          'Create a new identity. For "private" tier, returns a 12-word recovery phrase that MUST be shown to the user for backup. For "easy" tier, uses TouchID/FaceID via WebAuthn passkeys. The identity is automatically unlocked after creation.',
        inputSchema: {
          type: 'object',
          properties: {
            tier: {
              type: 'string',
              enum: ['easy', 'private'],
              description:
                'Identity tier. "easy" uses TouchID/FaceID (lowest friction), "private" uses password + recovery phrase.',
            },
            password: {
              type: 'string',
              description: 'Password to encrypt the identity (required for private tier, ignored for easy)',
            },
            email: {
              type: 'string',
              description: 'Email address for identity recovery (required for easy tier, ignored for private)',
            },
          },
          required: ['tier'],
        },
      },
      {
        name: 'identity_import',
        description:
          'Import an existing identity. For "private" tier, requires 12-word recovery phrase. For "easy" tier, recovers via synced passkey + email. The identity is automatically unlocked after import.',
        inputSchema: {
          type: 'object',
          properties: {
            tier: {
              type: 'string',
              enum: ['easy', 'private'],
              description:
                'Identity tier. "easy" recovers via synced passkey + email, "private" requires mnemonic.',
            },
            password: {
              type: 'string',
              description: 'Password to encrypt the identity (required for private tier)',
            },
            email: {
              type: 'string',
              description: 'Email address used during creation (required for easy tier)',
            },
            mnemonic: {
              type: 'string',
              description: '12-word recovery phrase (required for private tier)',
            },
          },
          required: ['tier'],
        },
      },
      {
        name: 'identity_unlock',
        description:
          'Unlock the identity. For "private" tier, requires password. For "easy" tier, triggers biometric auth (no password needed). Required before signing.',
        inputSchema: {
          type: 'object',
          properties: {
            password: {
              type: 'string',
              description: 'Password to decrypt the identity (required for private tier, ignored for easy)',
            },
          },
          required: [],
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
      // Action event preparation tools (kinds 30810, 30811, 30812)
      {
        name: 'prepare_action_event',
        description:
          'Prepare an unsigned civic action event (kind 30810). Defines a civic action that users can commit to and complete. Returns an unsigned Nostr event — use sign_event to sign it.',
        inputSchema: {
          type: 'object',
          properties: {
            initiative_id: { type: 'string', description: 'Initiative this action belongs to' },
            action_type: { type: 'string', enum: ['written_comment', 'attend_meeting', 'public_comment', 'contact_official', 'signature', 'share', 'custom'], description: 'Type of civic action' },
            description: { type: 'string', description: 'Human-readable description of the action' },
            jurisdiction: { type: 'string', description: 'Jurisdiction identifier' },
            target: { type: 'string', description: 'Target of the action (email, URL, etc.)' },
            deadline: { type: 'string', description: 'ISO 8601 deadline' },
            template: { type: 'string', description: 'Template text for the action' },
            target_count: { type: 'number', description: 'Target number of completions needed' },
          },
          required: ['initiative_id', 'action_type', 'description', 'jurisdiction'],
        },
      },
      {
        name: 'prepare_commitment',
        description:
          'Prepare an unsigned commitment event (kind 30811). Records commitment to a civic action. Returns an unsigned Nostr event — use sign_event to sign it.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: { type: 'string', description: 'Action event ID (d-tag of the 30810 event)' },
            action_creator_pubkey: { type: 'string', description: 'Public key (hex) of the action creator' },
            jurisdiction: { type: 'string', description: 'Jurisdiction identifier' },
          },
          required: ['action_id', 'action_creator_pubkey', 'jurisdiction'],
        },
      },
      {
        name: 'prepare_completion',
        description:
          'Prepare an unsigned completion event (kind 30812). Records that a civic action was completed with evidence. Returns an unsigned Nostr event — use sign_event to sign it.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: { type: 'string', description: 'Action event ID (d-tag of the 30810 event)' },
            action_creator_pubkey: { type: 'string', description: 'Public key (hex) of the action creator' },
            evidence_type: { type: 'string', enum: ['self_report', 'email_confirmation', 'attendance_check', 'verified'], description: 'Type of evidence' },
            jurisdiction: { type: 'string', description: 'Jurisdiction identifier' },
            evidence_content: { type: 'string', description: 'Evidence content (URL, confirmation code)' },
          },
          required: ['action_id', 'action_creator_pubkey', 'evidence_type', 'jurisdiction'],
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
      {
        name: 'get_storage_info',
        description:
          'Get information about the storage backend: type (filesystem/memory), location, version.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      // ================================================================
      // Profile, Preferences, and Jurisdictions Management Tools
      // ================================================================
      {
        name: 'get_profile',
        description:
          'Get the user\'s civic profile (name, email, neighborhood, coordinates, interests). In filesystem mode, reads from ~/.civicos/profile.md.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      {
        name: 'set_profile',
        description:
          'Update the user\'s civic profile. Only provided fields are updated — omitted fields keep their current values. In filesystem mode, writes human-readable ~/.civicos/profile.md.',
        inputSchema: {
          type: 'object',
          properties: {
            name: {
              type: 'string',
              description: 'Display name',
            },
            email: {
              type: 'string',
              description: 'Email address',
            },
            neighborhood: {
              type: 'string',
              description: 'Neighborhood name (e.g., "Terra Linda")',
            },
            latitude: {
              type: 'number',
              description: 'Latitude coordinate',
            },
            longitude: {
              type: 'number',
              description: 'Longitude coordinate',
            },
            interests: {
              type: 'array',
              items: { type: 'string' },
              description: 'Civic interest topics (e.g., ["Housing", "Transportation"]). Replaces existing interests.',
            },
          },
          required: [],
        },
      },
      {
        name: 'get_preferences',
        description:
          'Get the user\'s notification and display preferences. In filesystem mode, reads from ~/.civicos/preferences.md.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      {
        name: 'set_preferences',
        description:
          'Update the user\'s preferences. Merges with existing — only provided keys are updated. In filesystem mode, writes human-readable ~/.civicos/preferences.md.',
        inputSchema: {
          type: 'object',
          properties: {
            notifications: {
              type: 'object',
              description: 'Notification preferences (e.g., {"Email Digest": "weekly", "Meeting Reminders": "true"})',
            },
            display: {
              type: 'object',
              description: 'Display preferences (e.g., {"Theme": "dark", "Language": "en"})',
            },
          },
          required: [],
        },
      },
      {
        name: 'get_jurisdictions',
        description:
          'Get the user\'s ordered list of jurisdictions. In filesystem mode, reads from ~/.civicos/jurisdictions.md.',
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      },
      {
        name: 'set_jurisdictions',
        description:
          'Set the user\'s ordered list of jurisdictions. Replaces the existing list. In filesystem mode, writes human-readable ~/.civicos/jurisdictions.md.',
        inputSchema: {
          type: 'object',
          properties: {
            jurisdictions: {
              type: 'array',
              items: { type: 'string' },
              description: 'Ordered list of jurisdiction IDs (e.g., ["city-san-rafael", "county-marin"])',
            },
          },
          required: ['jurisdictions'],
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
          args.password as string | undefined,
          args.email as string | undefined
        );

      case 'identity_import':
        return this.handleIdentityImport(
          args.tier as IdentityTier,
          args.password as string | undefined,
          args.mnemonic as string | undefined,
          args.email as string | undefined
        );

      case 'identity_unlock':
        return this.handleIdentityUnlock(args.password as string | undefined);

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

      // Action event preparation tools
      case 'prepare_action_event':
        return this.handlePrepareActionEvent(
          args.initiative_id as string,
          args.action_type as CivicActionType,
          args.description as string,
          args.jurisdiction as string,
          {
            target: args.target as string | undefined,
            deadline: args.deadline as string | undefined,
            template: args.template as string | undefined,
            targetCount: args.target_count as number | undefined,
          }
        );

      case 'prepare_commitment':
        return this.handlePrepareCommitment(
          args.action_id as string,
          args.action_creator_pubkey as string,
          args.jurisdiction as string
        );

      case 'prepare_completion':
        return this.handlePrepareCompletion(
          args.action_id as string,
          args.action_creator_pubkey as string,
          args.evidence_type as EvidenceType,
          args.jurisdiction as string,
          args.evidence_content as string | undefined
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

      case 'get_storage_info':
        return this.handleGetStorageInfo();

      // Profile, preferences, jurisdictions
      case 'get_profile':
        return this.handleGetProfile();

      case 'set_profile':
        return this.handleSetProfile(args as Record<string, unknown>);

      case 'get_preferences':
        return this.handleGetPreferences();

      case 'set_preferences':
        return this.handleSetPreferences(
          args.notifications as Record<string, string> | undefined,
          args.display as Record<string, string> | undefined
        );

      case 'get_jurisdictions':
        return this.handleGetJurisdictions();

      case 'set_jurisdictions':
        return this.handleSetJurisdictions(args.jurisdictions as string[]);

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
    password?: string,
    email?: string
  ): Promise<unknown> {
    // Validate required parameters based on tier
    if (tier === 'easy' && !email) {
      throw new Error('Email is required for easy tier');
    }
    if (tier === 'private' && !password) {
      throw new Error('Password is required for private tier');
    }

    // Use email for easy tier, password for private tier
    const passwordOrEmail = tier === 'easy' ? email! : password!;
    const result = await this.identityManager.createIdentity(tier, passwordOrEmail);

    const response: Record<string, unknown> = {
      success: true,
      identity: {
        tier: result.identity.tier,
        publicKey: result.identity.publicKey,
        npub: result.identity.npub,
      },
    };

    // Only include mnemonic for private tier
    if (result.mnemonic) {
      response.mnemonic = result.mnemonic;
      response.warning =
        'CRITICAL: Save this recovery phrase securely. It cannot be recovered if lost.';
    }

    // Advice for easy tier
    if (tier === 'easy') {
      response.note =
        'Your identity is derived from your passkey. Same email + same passkey = same identity on any device.';
    }

    return response;
  }

  private async handleIdentityImport(
    tier: IdentityTier,
    password?: string,
    mnemonic?: string,
    email?: string
  ): Promise<unknown> {
    // Validate required parameters based on tier
    if (tier === 'easy' && !email) {
      throw new Error('Email is required to recover easy tier identity');
    }
    if (tier === 'private' && (!password || !mnemonic)) {
      throw new Error('Password and mnemonic are required for private tier');
    }

    // Use email for easy tier, password for private tier
    const passwordOrEmail = tier === 'easy' ? email! : password!;
    const identity = await this.identityManager.importIdentity(
      tier,
      passwordOrEmail,
      mnemonic
    );

    return {
      success: true,
      identity: {
        tier: identity.tier,
        publicKey: identity.publicKey,
        npub: identity.npub,
      },
    };
  }

  private async handleIdentityUnlock(password?: string): Promise<unknown> {
    // Get current identity to check tier
    const identity = await this.identityManager.getIdentity();
    if (!identity) {
      throw new Error('No identity found. Create or import one first.');
    }

    // Easy tier doesn't need password (uses biometric)
    if (identity.tier === 'easy') {
      // For easy tier, unlock triggers WebAuthn prompt
      const success = await this.identityManager.unlock(''); // Empty password, triggers passkey auth
      return success
        ? { success: true, message: 'Identity unlocked via passkey' }
        : { success: false, error: 'Passkey authentication failed or was canceled' };
    }

    // Private tier requires password
    if (!password) {
      throw new Error('Password is required to unlock private tier identity');
    }

    const success = await this.identityManager.unlock(password);
    return success
      ? { success: true, message: 'Identity unlocked' }
      : { success: false, error: 'Incorrect password' };
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

  // Action event preparation handlers

  private async handlePrepareActionEvent(
    initiativeId: string,
    actionType: CivicActionType,
    description: string,
    jurisdiction: string,
    options: {
      target?: string;
      deadline?: string;
      template?: string;
      targetCount?: number;
    }
  ): Promise<unknown> {
    if (!CIVIC_ACTION_TYPES.includes(actionType)) {
      throw new Error(`Invalid action_type: "${actionType}". Must be one of: ${CIVIC_ACTION_TYPES.join(', ')}`);
    }
    if (options.deadline && isNaN(Date.parse(options.deadline))) {
      throw new Error(`Invalid deadline format: "${options.deadline}". Use ISO 8601.`);
    }

    const descHashFull = sha256Hex(description);
    const actionId = generateActionId(initiativeId, actionType, descHashFull.slice(0, 8));
    const timestamp = Math.floor(Date.now() / 1000);

    const content = createActionEventContent(actionId, actionType, descHashFull.slice(0, 16), timestamp);
    const tags = createActionEventTags(actionId, initiativeId, actionType, jurisdiction, {
      description,
      target: options.target,
      deadline: options.deadline,
      template: options.template,
      targetCount: options.targetCount,
    });

    return {
      action_id: actionId,
      unsigned_event: { created_at: timestamp, kind: CivicEventKinds.ACTION_EVENT, tags, content },
      metadata: { initiative_id: initiativeId, action_type: actionType, description, jurisdiction, target: options.target ?? null, deadline: options.deadline ?? null, template: options.template ?? null, target_count: options.targetCount ?? null },
      instructions: 'This event is unsigned. Call sign_event with the kind, content, and tags to sign it, then broadcast to the relay.',
    };
  }

  private async handlePrepareCommitment(
    actionId: string,
    actionCreatorPubkey: string,
    jurisdiction: string
  ): Promise<unknown> {
    const pubkey = await this.identityManager.getPublicKey();
    if (!pubkey) {
      throw new Error('No identity found. Create or import one first, then unlock it.');
    }

    const commitmentId = generateCommitmentId(pubkey.slice(0, 16), actionId);
    const actionRef = generateActionRef(actionCreatorPubkey, actionId);
    const timestamp = Math.floor(Date.now() / 1000);

    const content = createActionCommitmentContent(commitmentId, actionRef);
    const tags = createActionCommitmentTags(commitmentId, actionRef, jurisdiction);

    return {
      commitment_id: commitmentId,
      action_ref: actionRef,
      unsigned_event: { created_at: timestamp, kind: CivicEventKinds.ACTION_COMMITMENT, tags, content },
      metadata: { action_id: actionId, action_creator_pubkey: actionCreatorPubkey, jurisdiction, committer_pubkey: pubkey },
      instructions: 'This event is unsigned. Call sign_event with the kind, content, and tags to sign it, then broadcast to the relay.',
    };
  }

  private async handlePrepareCompletion(
    actionId: string,
    actionCreatorPubkey: string,
    evidenceType: EvidenceType,
    jurisdiction: string,
    evidenceContent?: string
  ): Promise<unknown> {
    if (!EVIDENCE_TYPES.includes(evidenceType)) {
      throw new Error(`Invalid evidence_type: "${evidenceType}". Must be one of: ${EVIDENCE_TYPES.join(', ')}`);
    }

    const pubkey = await this.identityManager.getPublicKey();
    if (!pubkey) {
      throw new Error('No identity found. Create or import one first, then unlock it.');
    }

    const completionId = generateCompletionId(pubkey.slice(0, 16), actionId);
    const actionRef = generateActionRef(actionCreatorPubkey, actionId);
    const timestamp = Math.floor(Date.now() / 1000);

    const content = createActionCompletionContent(completionId, actionRef, evidenceType);
    const tags = createActionCompletionTags(completionId, actionRef, jurisdiction, evidenceType, evidenceContent);

    return {
      completion_id: completionId,
      action_ref: actionRef,
      unsigned_event: { created_at: timestamp, kind: CivicEventKinds.ACTION_COMPLETION, tags, content },
      metadata: { action_id: actionId, action_creator_pubkey: actionCreatorPubkey, evidence_type: evidenceType, evidence_content: evidenceContent ?? null, jurisdiction, completer_pubkey: pubkey },
      instructions: 'This event is unsigned. Call sign_event with the kind, content, and tags to sign it, then broadcast to the relay.',
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

    // Merge profile.md data if PersonalStorage is available
    let profileDefaults: { neighborhood?: string; interests?: string[] } = {};
    if (this.personalStorage) {
      const profile = await this.personalStorage.getProfile();
      if (profile.neighborhood || profile.interests.length > 0) {
        profileDefaults = {
          neighborhood: profile.neighborhood,
          interests: profile.interests,
        };
      }
    }

    if (!context) {
      // If we have profile data but no context, return profile defaults
      if (profileDefaults.interests?.length || profileDefaults.neighborhood) {
        return {
          jurisdiction,
          hasContext: true,
          source: 'profile.md',
          neighborhood: profileDefaults.neighborhood ? { neighborhood: profileDefaults.neighborhood } : undefined,
          interests: profileDefaults.interests ?? [],
          following_items: [],
          message: 'Context loaded from profile.md. Use set_interests to override per jurisdiction.',
        };
      }

      return {
        jurisdiction,
        hasContext: false,
        message: `No context saved for ${jurisdiction}. Use set_neighborhood, set_interests, or follow_item to personalize.`,
      };
    }

    // Context overrides profile — profile provides defaults
    const mergedInterests = context.interests.length > 0
      ? context.interests
      : (profileDefaults.interests ?? []);

    const mergedNeighborhood = context.neighborhood ?? (profileDefaults.neighborhood
      ? { neighborhood: profileDefaults.neighborhood }
      : undefined);

    return {
      jurisdiction,
      hasContext: true,
      neighborhood: mergedNeighborhood,
      interests: mergedInterests,
      following_items: context.following_items,
      created_at: new Date(context.created_at).toISOString(),
      updated_at: new Date(context.updated_at).toISOString(),
    };
  }

  // Personalized query handlers

  private async handleGetRelevantNow(jurisdiction: string): Promise<unknown> {
    // Load user context
    const context = await this.contextStorage.load(jurisdiction);

    // Merge profile defaults if context is empty
    let effectiveInterests = context?.interests ?? [];
    let effectiveNeighborhood = context?.neighborhood?.neighborhood;
    if (this.personalStorage && effectiveInterests.length === 0 && !effectiveNeighborhood) {
      const profile = await this.personalStorage.getProfile();
      if (profile.interests.length > 0) effectiveInterests = profile.interests;
      if (profile.neighborhood) effectiveNeighborhood = profile.neighborhood;
    }

    const hasContext = effectiveInterests.length > 0 || effectiveNeighborhood;

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
    const interests = effectiveInterests.map((i: string) => i.toLowerCase());
    const neighborhood = effectiveNeighborhood?.toLowerCase();

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
        interests: effectiveInterests,
        neighborhood: effectiveNeighborhood,
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

    // Merge profile defaults if context is empty
    let effectiveInterests = context?.interests ?? [];
    if (this.personalStorage && effectiveInterests.length === 0) {
      const profile = await this.personalStorage.getProfile();
      if (profile.interests.length > 0) effectiveInterests = profile.interests;
    }

    const followingItems = context?.following_items ?? [];

    if (effectiveInterests.length === 0 && followingItems.length === 0) {
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
    for (const interest of effectiveInterests.slice(0, 3)) {
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
    for (const followedItem of followingItems.slice(0, 3)) {
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
      const interestKeywords = effectiveInterests.map((i: string) => i.toLowerCase());
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
        interests: effectiveInterests,
        following_count: followingItems.length,
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

  // ================================================================
  // Profile, Preferences, and Jurisdictions Handlers
  // ================================================================

  private async handleGetProfile(): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Profile management requires file-based or memory storage.',
      };
    }

    const profile = await this.personalStorage.getProfile();
    return {
      success: true,
      profile,
    };
  }

  private async handleSetProfile(args: Record<string, unknown>): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Profile management requires file-based or memory storage.',
      };
    }

    // Merge with existing profile — only update provided fields
    const existing = await this.personalStorage.getProfile();

    if (args.name !== undefined) existing.name = args.name as string;
    if (args.email !== undefined) existing.email = args.email as string;
    if (args.neighborhood !== undefined) existing.neighborhood = args.neighborhood as string;
    if (args.latitude !== undefined) existing.latitude = args.latitude as number;
    if (args.longitude !== undefined) existing.longitude = args.longitude as number;
    if (args.interests !== undefined) existing.interests = args.interests as string[];

    await this.personalStorage.saveProfile(existing);

    return {
      success: true,
      profile: existing,
      message: 'Profile updated.',
    };
  }

  private async handleGetPreferences(): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Preferences management requires file-based or memory storage.',
      };
    }

    const prefs = await this.personalStorage.getPreferences();
    return {
      success: true,
      preferences: prefs,
    };
  }

  private async handleSetPreferences(
    notifications?: Record<string, string>,
    display?: Record<string, string>
  ): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Preferences management requires file-based or memory storage.',
      };
    }

    // Merge with existing preferences
    const existing = await this.personalStorage.getPreferences();

    if (notifications) {
      existing.notifications = { ...existing.notifications, ...notifications };
    }
    if (display) {
      existing.display = { ...existing.display, ...display };
    }

    await this.personalStorage.savePreferences(existing);

    return {
      success: true,
      preferences: existing,
      message: 'Preferences updated.',
    };
  }

  private async handleGetJurisdictions(): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Jurisdiction management requires file-based or memory storage.',
      };
    }

    const jurisdictions = await this.personalStorage.getJurisdictions();
    return {
      success: true,
      jurisdictions,
      count: jurisdictions.length,
    };
  }

  private async handleSetJurisdictions(jurisdictions: string[]): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        success: false,
        error: 'No PersonalStorage configured. Jurisdiction management requires file-based or memory storage.',
      };
    }

    if (!Array.isArray(jurisdictions)) {
      throw new Error('jurisdictions must be an array of strings');
    }

    await this.personalStorage.saveJurisdictions(jurisdictions);

    return {
      success: true,
      jurisdictions,
      count: jurisdictions.length,
      message: 'Jurisdictions updated.',
    };
  }

  private async handleGetStorageInfo(): Promise<unknown> {
    if (!this.personalStorage) {
      return {
        type: 'legacy',
        message: 'No PersonalStorage configured. Using legacy ContextStorage/IdentityManager defaults.',
      };
    }

    return this.personalStorage.getStorageInfo();
  }

  /**
   * Start the HTTP server.
   */
  async run(): Promise<void> {
    // Initialize persistent storage if available
    if (this.personalStorage) {
      await this.personalStorage.initialize();
      // Auto-unlock from env var if available
      await this.identityManager.autoUnlockFromEnv();
    }

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
