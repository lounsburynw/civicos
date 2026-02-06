/**
 * Personal MCP Server
 *
 * User's edge agent for personalized civic participation.
 * Handles identity, signing, context, and personalization.
 *
 * Architecture:
 * - Queries Jurisdiction MCP for civic data (read-only)
 * - Stores user context locally (never sent to server)
 * - Signs actions with user's keys (client-side only)
 * - Explains why something is relevant to this user
 *
 * See docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md for full design.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { IdentityManager } from './identity.js';
import type { SigningProvider, NostrEvent, IdentityTier } from '../lib/providers/index.js';
import {
  LocalWalletProvider,
  IndexedDBStorage,
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
  verifyNostrEvent,
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

/**
 * Personal MCP Server configuration.
 */
interface PersonalMCPConfig {
  /** Jurisdiction MCP endpoint for civic data queries */
  jurisdictionMcpUrl?: string;
  /** Default jurisdiction for queries */
  defaultJurisdiction?: string;
}

/**
 * Personal MCP Server
 *
 * Tools provided:
 * - identity_status: Check current identity status
 * - identity_create: Create a new identity
 * - identity_import: Import existing identity from mnemonic
 * - identity_unlock: Unlock identity with password
 * - identity_lock: Lock identity
 * - sign_voice: Sign a civic voice event
 * - sign_event: Sign an arbitrary Nostr event
 * - prepare_action_event: Prepare unsigned kind 30810 action event
 * - prepare_commitment: Prepare unsigned kind 30811 commitment
 * - prepare_completion: Prepare unsigned kind 30812 completion
 */
export class PersonalMCPServer {
  private server: Server;
  private identityManager: IdentityManager;
  private config: PersonalMCPConfig;

  constructor(config: PersonalMCPConfig = {}) {
    this.config = config;
    this.identityManager = new IdentityManager();

    this.server = new Server(
      {
        name: 'civicos-personal-mcp',
        version: '0.1.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupHandlers();
  }

  private setupHandlers(): void {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: this.getTools(),
    }));

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      return this.handleToolCall(name, args ?? {});
    });
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
      // ================================================================
      // Action Event Preparation Tools (kinds 30810, 30811, 30812)
      // ================================================================
      {
        name: 'prepare_action_event',
        description:
          'Prepare an unsigned civic action event (kind 30810). Defines a civic action that users can commit to and complete. Returns an unsigned Nostr event — use sign_event to sign it before broadcasting. Valid action types: written_comment, attend_meeting, public_comment, contact_official, signature, share, custom.',
        inputSchema: {
          type: 'object',
          properties: {
            initiative_id: {
              type: 'string',
              description:
                'Initiative this action belongs to (e.g., "city-san-rafael:housing-element-2026")',
            },
            action_type: {
              type: 'string',
              enum: [
                'written_comment',
                'attend_meeting',
                'public_comment',
                'contact_official',
                'signature',
                'share',
                'custom',
              ],
              description: 'Type of civic action',
            },
            description: {
              type: 'string',
              description:
                'Human-readable description of the action (e.g., "Submit a written comment supporting the Housing Element Update")',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            target: {
              type: 'string',
              description:
                'Target of the action (e.g., email address, meeting room, submission URL)',
            },
            deadline: {
              type: 'string',
              description: 'ISO 8601 deadline for completing the action (e.g., "2026-02-15T17:00:00Z")',
            },
            template: {
              type: 'string',
              description:
                'Template text for the action (e.g., a comment template the user can customize)',
            },
            target_count: {
              type: 'number',
              description: 'Target number of completions needed (e.g., 10 comments)',
            },
          },
          required: ['initiative_id', 'action_type', 'description', 'jurisdiction'],
        },
      },
      {
        name: 'prepare_commitment',
        description:
          'Prepare an unsigned commitment event (kind 30811). Records a user\'s commitment to take a civic action defined by a 30810 event. Returns an unsigned Nostr event — use sign_event to sign it before broadcasting.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: {
              type: 'string',
              description:
                'Action event ID (d-tag of the 30810 event, e.g., "action:city-san-rafael:housing-element-2026:written_comment:a1b2c3d4")',
            },
            action_creator_pubkey: {
              type: 'string',
              description: 'Public key (hex) of the action event creator, needed for the a-tag reference',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
          },
          required: ['action_id', 'action_creator_pubkey', 'jurisdiction'],
        },
      },
      {
        name: 'prepare_completion',
        description:
          'Prepare an unsigned completion event (kind 30812). Records that a user completed a civic action with evidence. Returns an unsigned Nostr event — use sign_event to sign it before broadcasting.',
        inputSchema: {
          type: 'object',
          properties: {
            action_id: {
              type: 'string',
              description:
                'Action event ID (d-tag of the 30810 event)',
            },
            action_creator_pubkey: {
              type: 'string',
              description: 'Public key (hex) of the action event creator',
            },
            evidence_type: {
              type: 'string',
              enum: ['self_report', 'email_confirmation', 'attendance_check', 'verified'],
              description: 'Type of evidence provided for completion',
            },
            jurisdiction: {
              type: 'string',
              description: 'Jurisdiction identifier (e.g., "city-san-rafael")',
            },
            evidence_content: {
              type: 'string',
              description:
                'Evidence content (e.g., URL to submitted comment, confirmation code, screenshot link)',
            },
          },
          required: ['action_id', 'action_creator_pubkey', 'evidence_type', 'jurisdiction'],
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

  // ================================================================
  // Action Event Preparation Handlers (kinds 30810, 30811, 30812)
  // ================================================================

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
    // Validate action type
    if (!CIVIC_ACTION_TYPES.includes(actionType)) {
      throw new Error(
        `Invalid action_type: "${actionType}". Must be one of: ${CIVIC_ACTION_TYPES.join(', ')}`
      );
    }

    // Validate deadline format if provided
    if (options.deadline) {
      const parsed = Date.parse(options.deadline);
      if (isNaN(parsed)) {
        throw new Error(`Invalid deadline format: "${options.deadline}". Use ISO 8601 (e.g., "2026-02-15T17:00:00Z")`);
      }
    }

    // Generate deterministic action ID (matches Python CivicActionService)
    const descHashFull = sha256Hex(description);
    const descHashForId = descHashFull.slice(0, 8);
    const descHashForContent = descHashFull.slice(0, 16);
    const actionId = generateActionId(initiativeId, actionType, descHashForId);

    const timestamp = Math.floor(Date.now() / 1000);

    // Build unsigned Nostr event
    const content = createActionEventContent(actionId, actionType, descHashForContent, timestamp);
    const tags = createActionEventTags(actionId, initiativeId, actionType, jurisdiction, {
      description,
      target: options.target,
      deadline: options.deadline,
      template: options.template,
      targetCount: options.targetCount,
    });

    const unsignedEvent: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.ACTION_EVENT,
      tags,
      content,
    };

    return {
      action_id: actionId,
      unsigned_event: unsignedEvent,
      metadata: {
        initiative_id: initiativeId,
        action_type: actionType,
        description,
        jurisdiction,
        target: options.target ?? null,
        deadline: options.deadline ?? null,
        template: options.template ?? null,
        target_count: options.targetCount ?? null,
      },
      instructions: 'This event is unsigned. Call sign_event with the kind, content, and tags to sign it, then broadcast to the relay.',
    };
  }

  private async handlePrepareCommitment(
    actionId: string,
    actionCreatorPubkey: string,
    jurisdiction: string
  ): Promise<unknown> {
    // Get user's public key for commitment ID
    const pubkey = await this.identityManager.getPublicKey();
    if (!pubkey) {
      throw new Error('No identity found. Create or import one first, then unlock it.');
    }

    // Generate commitment ID and action reference
    const publicKeyPrefix = pubkey.slice(0, 16);
    const commitmentId = generateCommitmentId(publicKeyPrefix, actionId);
    const actionRef = generateActionRef(actionCreatorPubkey, actionId);

    const timestamp = Math.floor(Date.now() / 1000);

    // Build unsigned Nostr event
    const content = createActionCommitmentContent(commitmentId, actionRef);
    const tags = createActionCommitmentTags(commitmentId, actionRef, jurisdiction);

    const unsignedEvent: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.ACTION_COMMITMENT,
      tags,
      content,
    };

    return {
      commitment_id: commitmentId,
      action_ref: actionRef,
      unsigned_event: unsignedEvent,
      metadata: {
        action_id: actionId,
        action_creator_pubkey: actionCreatorPubkey,
        jurisdiction,
        committer_pubkey: pubkey,
      },
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
    // Validate evidence type
    if (!EVIDENCE_TYPES.includes(evidenceType)) {
      throw new Error(
        `Invalid evidence_type: "${evidenceType}". Must be one of: ${EVIDENCE_TYPES.join(', ')}`
      );
    }

    // Get user's public key for completion ID
    const pubkey = await this.identityManager.getPublicKey();
    if (!pubkey) {
      throw new Error('No identity found. Create or import one first, then unlock it.');
    }

    // Generate completion ID and action reference
    const publicKeyPrefix = pubkey.slice(0, 16);
    const completionId = generateCompletionId(publicKeyPrefix, actionId);
    const actionRef = generateActionRef(actionCreatorPubkey, actionId);

    const timestamp = Math.floor(Date.now() / 1000);

    // Build unsigned Nostr event
    const content = createActionCompletionContent(completionId, actionRef, evidenceType);
    const tags = createActionCompletionTags(
      completionId,
      actionRef,
      jurisdiction,
      evidenceType,
      evidenceContent
    );

    const unsignedEvent: NostrEvent = {
      created_at: timestamp,
      kind: CivicEventKinds.ACTION_COMPLETION,
      tags,
      content,
    };

    return {
      completion_id: completionId,
      action_ref: actionRef,
      unsigned_event: unsignedEvent,
      metadata: {
        action_id: actionId,
        action_creator_pubkey: actionCreatorPubkey,
        evidence_type: evidenceType,
        evidence_content: evidenceContent ?? null,
        jurisdiction,
        completer_pubkey: pubkey,
      },
      instructions: 'This event is unsigned. Call sign_event with the kind, content, and tags to sign it, then broadcast to the relay.',
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

  async run(): Promise<void> {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Personal MCP Server running on stdio');
  }
}

// Main entry point
const server = new PersonalMCPServer();
server.run().catch(console.error);
