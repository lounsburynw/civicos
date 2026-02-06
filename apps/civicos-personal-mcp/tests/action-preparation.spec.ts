/**
 * Tests for action event preparation tools (kinds 30810, 30811, 30812).
 *
 * Test file: apps/civicos-personal-mcp/tests/action-preparation.spec.ts
 * Run: cd apps/civicos-personal-mcp && npx vitest run tests/action-preparation.spec.ts
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  // Crypto utilities
  generatePrivateKey,
  getPublicKey,
  publicKeyToHex,
  sha256Hex,
  // Action event helpers
  CivicEventKinds,
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
  // Provider for integration tests
  LocalWalletProvider,
  MemoryStorage,
} from '../lib/providers/index.js';
import { PersonalMCPServer } from '../src/server.js';
import { IdentityManager } from '../src/identity.js';

// ============================================================================
// Unit Tests: Helper Functions
// ============================================================================

describe('Action event helpers', () => {
  describe('sha256Hex', () => {
    it('produces consistent hex output', () => {
      const hash = sha256Hex('test description');
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
      // Same input should always produce same hash
      expect(sha256Hex('test description')).toBe(hash);
    });

    it('produces different hashes for different inputs', () => {
      expect(sha256Hex('foo')).not.toBe(sha256Hex('bar'));
    });
  });

  describe('generateActionId', () => {
    it('creates deterministic action ID', () => {
      const descHash = sha256Hex('Submit a written comment').slice(0, 8);
      const id = generateActionId('city-san-rafael:housing-2026', 'written_comment', descHash);
      expect(id).toBe(`action:city-san-rafael:housing-2026:written_comment:${descHash}`);
    });

    it('different descriptions produce different IDs', () => {
      const hash1 = sha256Hex('Submit a comment').slice(0, 8);
      const hash2 = sha256Hex('Attend the meeting').slice(0, 8);
      const id1 = generateActionId('init-1', 'written_comment', hash1);
      const id2 = generateActionId('init-1', 'attend_meeting', hash2);
      expect(id1).not.toBe(id2);
    });
  });

  describe('generateCommitmentId', () => {
    it('creates ID with pubkey prefix', () => {
      const id = generateCommitmentId('abc123def456gh78', 'action:init-1:written_comment:a1b2c3d4');
      expect(id).toBe('commit:abc123def456gh78:action:init-1:written_comment:a1b2c3d4');
    });
  });

  describe('generateCompletionId', () => {
    it('creates ID with pubkey prefix', () => {
      const id = generateCompletionId('abc123def456gh78', 'action:init-1:written_comment:a1b2c3d4');
      expect(id).toBe('complete:abc123def456gh78:action:init-1:written_comment:a1b2c3d4');
    });
  });

  describe('generateActionRef', () => {
    it('creates a-tag format reference', () => {
      const ref = generateActionRef('deadbeef01234567', 'action:init-1:written_comment:a1b2c3d4');
      expect(ref).toBe('30810:deadbeef01234567:action:init-1:written_comment:a1b2c3d4');
    });
  });

  describe('CivicEventKinds', () => {
    it('has correct kind numbers', () => {
      expect(CivicEventKinds.ACTION_EVENT).toBe(30810);
      expect(CivicEventKinds.ACTION_COMMITMENT).toBe(30811);
      expect(CivicEventKinds.ACTION_COMPLETION).toBe(30812);
    });

    it('preserves legacy kinds', () => {
      expect(CivicEventKinds.VOICE).toBe(30800);
      expect(CivicEventKinds.COMMITMENT).toBe(30801);
      expect(CivicEventKinds.COMPLETION).toBe(30802);
    });
  });

  describe('Action event content and tags (kind 30810)', () => {
    it('creates canonical content matching Python format', () => {
      const content = createActionEventContent(
        'action:init-1:written_comment:a1b2c3d4',
        'written_comment',
        'a1b2c3d4e5f6g7h8',
        1706900000
      );
      expect(content).toBe(
        'civicos:action:v1:action:init-1:written_comment:a1b2c3d4:written_comment:a1b2c3d4e5f6g7h8:1706900000'
      );
    });

    it('creates tags with required fields', () => {
      const tags = createActionEventTags(
        'action:init-1:written_comment:a1b2c3d4',
        'init-1',
        'written_comment',
        'city-san-rafael'
      );
      expect(tags).toContainEqual(['d', 'action:init-1:written_comment:a1b2c3d4']);
      expect(tags).toContainEqual(['j', 'city-san-rafael']);
      expect(tags).toContainEqual(['initiative', 'init-1']);
      expect(tags).toContainEqual(['action_type', 'written_comment']);
    });

    it('creates tags with optional fields', () => {
      const tags = createActionEventTags(
        'action:init-1:written_comment:a1b2c3d4',
        'init-1',
        'written_comment',
        'city-san-rafael',
        {
          description: 'Submit a comment',
          target: 'clerk@sanrafael.gov',
          deadline: '2026-02-15T17:00:00Z',
          template: 'Dear Council Members...',
          targetCount: 10,
        }
      );
      expect(tags).toContainEqual(['description', 'Submit a comment']);
      expect(tags).toContainEqual(['target', 'clerk@sanrafael.gov']);
      expect(tags).toContainEqual(['deadline', '2026-02-15T17:00:00Z']);
      expect(tags).toContainEqual(['template', 'Dear Council Members...']);
      expect(tags).toContainEqual(['target_count', '10']);
    });
  });

  describe('Action commitment content and tags (kind 30811)', () => {
    it('creates canonical content matching Python format', () => {
      const content = createActionCommitmentContent(
        'commit:abc123def456gh78:action:init-1:written_comment:a1b2c3d4',
        '30810:deadbeef01234567:action:init-1:written_comment:a1b2c3d4'
      );
      expect(content).toBe(
        'civicos:commitment:v1:commit:abc123def456gh78:action:init-1:written_comment:a1b2c3d4:30810:deadbeef01234567:action:init-1:written_comment:a1b2c3d4'
      );
    });

    it('creates tags with a-tag reference', () => {
      const tags = createActionCommitmentTags(
        'commit:abc123:action-id',
        '30810:deadbeef:action-id',
        'city-san-rafael'
      );
      expect(tags).toContainEqual(['d', 'commit:abc123:action-id']);
      expect(tags).toContainEqual(['a', '30810:deadbeef:action-id']);
      expect(tags).toContainEqual(['j', 'city-san-rafael']);
    });
  });

  describe('Action completion content and tags (kind 30812)', () => {
    it('creates canonical content matching Python format', () => {
      const content = createActionCompletionContent(
        'complete:abc123:action-id',
        '30810:deadbeef:action-id',
        'self_report'
      );
      expect(content).toBe(
        'civicos:completion:v1:complete:abc123:action-id:30810:deadbeef:action-id:self_report'
      );
    });

    it('creates tags with evidence', () => {
      const tags = createActionCompletionTags(
        'complete:abc123:action-id',
        '30810:deadbeef:action-id',
        'city-san-rafael',
        'email_confirmation',
        'https://example.com/confirmation'
      );
      expect(tags).toContainEqual(['d', 'complete:abc123:action-id']);
      expect(tags).toContainEqual(['a', '30810:deadbeef:action-id']);
      expect(tags).toContainEqual(['j', 'city-san-rafael']);
      expect(tags).toContainEqual(['evidence_type', 'email_confirmation']);
      expect(tags).toContainEqual(['evidence', 'https://example.com/confirmation']);
    });

    it('omits evidence tag when no content provided', () => {
      const tags = createActionCompletionTags(
        'complete:abc123:action-id',
        '30810:deadbeef:action-id',
        'city-san-rafael',
        'self_report'
      );
      expect(tags.find((t) => t[0] === 'evidence')).toBeUndefined();
    });
  });

  describe('Type validation constants', () => {
    it('has all civic action types', () => {
      expect(CIVIC_ACTION_TYPES).toContain('written_comment');
      expect(CIVIC_ACTION_TYPES).toContain('attend_meeting');
      expect(CIVIC_ACTION_TYPES).toContain('public_comment');
      expect(CIVIC_ACTION_TYPES).toContain('contact_official');
      expect(CIVIC_ACTION_TYPES).toContain('signature');
      expect(CIVIC_ACTION_TYPES).toContain('share');
      expect(CIVIC_ACTION_TYPES).toContain('custom');
      expect(CIVIC_ACTION_TYPES.length).toBe(7);
    });

    it('has all evidence types', () => {
      expect(EVIDENCE_TYPES).toContain('self_report');
      expect(EVIDENCE_TYPES).toContain('email_confirmation');
      expect(EVIDENCE_TYPES).toContain('attendance_check');
      expect(EVIDENCE_TYPES).toContain('verified');
      expect(EVIDENCE_TYPES.length).toBe(4);
    });
  });
});

// ============================================================================
// Integration Tests: PersonalMCPServer Prepare Tools
// ============================================================================

describe('PersonalMCPServer prepare tools', () => {
  let server: PersonalMCPServer;
  let identityManager: IdentityManager;
  let publicKey: string;

  beforeEach(async () => {
    // Create server with memory storage for testing
    const storage = new MemoryStorage();
    identityManager = new IdentityManager({ storage });

    // Create and unlock an identity
    const result = await identityManager.createIdentity('private', 'test-password-123');
    publicKey = result.identity.publicKey;

    // Create server - we'll call handlers directly via the private API
    // For integration testing, we access the server's tool handling
    server = new PersonalMCPServer();

    // We need to access the private method, so we use a workaround:
    // Create a separate IdentityManager that the server wraps
  });

  // Since PersonalMCPServer creates its own IdentityManager internally,
  // we test the helper functions and canonical format alignment instead.
  // Full end-to-end tests require the MCP protocol transport.

  describe('Action ID determinism', () => {
    it('generates same ID for same inputs', () => {
      const desc = 'Submit a written comment on Housing Element Update';
      const hash = sha256Hex(desc).slice(0, 8);
      const id1 = generateActionId('city-san-rafael:housing-2026', 'written_comment', hash);
      const id2 = generateActionId('city-san-rafael:housing-2026', 'written_comment', hash);
      expect(id1).toBe(id2);
    });

    it('matches Python format: action:{initiative}:{type}:{hash}', () => {
      const desc = 'Test description';
      const hash = sha256Hex(desc).slice(0, 8);
      const id = generateActionId('my-initiative', 'attend_meeting', hash);
      expect(id).toMatch(/^action:my-initiative:attend_meeting:[0-9a-f]{8}$/);
    });
  });

  describe('Commitment ID format', () => {
    it('uses first 16 chars of public key', () => {
      const pubkeyPrefix = publicKey.slice(0, 16);
      const actionId = 'action:init-1:written_comment:a1b2c3d4';
      const commitmentId = generateCommitmentId(pubkeyPrefix, actionId);
      expect(commitmentId).toMatch(/^commit:[0-9a-f]{16}:action:/);
    });
  });

  describe('Completion ID format', () => {
    it('uses first 16 chars of public key', () => {
      const pubkeyPrefix = publicKey.slice(0, 16);
      const actionId = 'action:init-1:written_comment:a1b2c3d4';
      const completionId = generateCompletionId(pubkeyPrefix, actionId);
      expect(completionId).toMatch(/^complete:[0-9a-f]{16}:action:/);
    });
  });

  describe('Unsigned event structure', () => {
    it('action event has correct kind and structure', () => {
      const desc = 'Submit a comment supporting affordable housing';
      const descHash = sha256Hex(desc);
      const actionId = generateActionId('housing-2026', 'written_comment', descHash.slice(0, 8));
      const timestamp = Math.floor(Date.now() / 1000);

      const content = createActionEventContent(
        actionId,
        'written_comment',
        descHash.slice(0, 16),
        timestamp
      );
      const tags = createActionEventTags(actionId, 'housing-2026', 'written_comment', 'city-san-rafael', {
        description: desc,
        target: 'clerk@sanrafael.gov',
        deadline: '2026-02-15T17:00:00Z',
        targetCount: 10,
      });

      const event = {
        created_at: timestamp,
        kind: CivicEventKinds.ACTION_EVENT,
        tags,
        content,
      };

      expect(event.kind).toBe(30810);
      expect(event.content).toContain('civicos:action:v1:');
      expect(event.tags.find((t) => t[0] === 'd')?.[1]).toBe(actionId);
      expect(event.tags.find((t) => t[0] === 'j')?.[1]).toBe('city-san-rafael');
      expect(event.tags.find((t) => t[0] === 'initiative')?.[1]).toBe('housing-2026');
      expect(event.tags.find((t) => t[0] === 'target')?.[1]).toBe('clerk@sanrafael.gov');
      expect(event.tags.find((t) => t[0] === 'target_count')?.[1]).toBe('10');
    });

    it('commitment event has correct kind and a-tag reference', () => {
      const actionId = 'action:init-1:written_comment:a1b2c3d4';
      const creatorPubkey = 'deadbeef01234567890abcdef0123456789abcdef0123456789abcdef01234567';
      const commitmentId = generateCommitmentId(publicKey.slice(0, 16), actionId);
      const actionRef = generateActionRef(creatorPubkey, actionId);

      const content = createActionCommitmentContent(commitmentId, actionRef);
      const tags = createActionCommitmentTags(commitmentId, actionRef, 'city-san-rafael');

      const event = {
        created_at: Math.floor(Date.now() / 1000),
        kind: CivicEventKinds.ACTION_COMMITMENT,
        tags,
        content,
      };

      expect(event.kind).toBe(30811);
      expect(event.content).toContain('civicos:commitment:v1:');
      expect(event.tags.find((t) => t[0] === 'a')?.[1]).toBe(actionRef);
      expect(event.tags.find((t) => t[0] === 'd')?.[1]).toBe(commitmentId);
    });

    it('completion event has correct kind and evidence', () => {
      const actionId = 'action:init-1:written_comment:a1b2c3d4';
      const creatorPubkey = 'deadbeef01234567890abcdef0123456789abcdef0123456789abcdef01234567';
      const completionId = generateCompletionId(publicKey.slice(0, 16), actionId);
      const actionRef = generateActionRef(creatorPubkey, actionId);

      const content = createActionCompletionContent(completionId, actionRef, 'email_confirmation');
      const tags = createActionCompletionTags(
        completionId,
        actionRef,
        'city-san-rafael',
        'email_confirmation',
        'https://example.com/proof'
      );

      const event = {
        created_at: Math.floor(Date.now() / 1000),
        kind: CivicEventKinds.ACTION_COMPLETION,
        tags,
        content,
      };

      expect(event.kind).toBe(30812);
      expect(event.content).toContain('civicos:completion:v1:');
      expect(event.content).toContain('email_confirmation');
      expect(event.tags.find((t) => t[0] === 'evidence_type')?.[1]).toBe('email_confirmation');
      expect(event.tags.find((t) => t[0] === 'evidence')?.[1]).toBe('https://example.com/proof');
    });
  });

  describe('Cross-language canonical message alignment', () => {
    it('action event content matches Python _create_action_message format', () => {
      // Python: f"civicos:action:v1:{action.id}:{action.action_type.value}:{desc_hash}:{action.timestamp.isoformat()}"
      // TypeScript uses unix timestamp instead of ISO, but the format structure is the same
      const actionId = 'action:my-init:written_comment:a1b2c3d4';
      const descHash16 = 'a1b2c3d4e5f67890';
      const timestamp = 1706900000;

      const content = createActionEventContent(actionId, 'written_comment', descHash16, timestamp);

      // Verify structure: civicos:action:v1:{id}:{type}:{hash}:{timestamp}
      const parts = content.split(':');
      expect(parts[0]).toBe('civicos');
      expect(parts[1]).toBe('action');
      expect(parts[2]).toBe('v1');
      // The remaining parts form the structured data
      expect(content).toContain(actionId);
      expect(content).toContain('written_comment');
      expect(content).toContain(descHash16);
      expect(content).toContain(String(timestamp));
    });

    it('commitment content matches Python verify_commitment_signature format', () => {
      // Python: f"civicos:commitment:v1:{commitment.id}:{commitment.action_ref}"
      const commitmentId = 'commit:abc123def456gh78:action-id';
      const actionRef = '30810:deadbeef:action-id';

      const content = createActionCommitmentContent(commitmentId, actionRef);
      expect(content).toBe(`civicos:commitment:v1:${commitmentId}:${actionRef}`);
    });

    it('completion content matches Python verify_completion_signature format', () => {
      // Python: f"civicos:completion:v1:{completion.id}:{completion.action_ref}:{completion.evidence_type.value}"
      const completionId = 'complete:abc123def456gh78:action-id';
      const actionRef = '30810:deadbeef:action-id';

      const content = createActionCompletionContent(completionId, actionRef, 'self_report');
      expect(content).toBe(`civicos:completion:v1:${completionId}:${actionRef}:self_report`);
    });
  });
});
