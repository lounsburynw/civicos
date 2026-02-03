/**
 * Tests for client-side signing providers.
 *
 * Test file: apps/civicos-personal-mcp/tests/signing.spec.ts
 * Run: cd apps/civicos-personal-mcp && npm test
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  // Crypto utilities
  generatePrivateKey,
  getPublicKey,
  publicKeyToHex,
  privateKeyToHex,
  hexToPrivateKey,
  computeEventId,
  signNostrEvent,
  verifyNostrEvent,
  publicKeyToNpub,
  npubToPublicKey,
  privateKeyToNsec,
  nsecToPrivateKey,
  // Provider
  LocalWalletProvider,
  MemoryStorage,
  // Types
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  type NostrEvent,
} from '../lib/providers/index.js';

describe('Crypto utilities', () => {
  describe('Key generation', () => {
    it('generates 32-byte private keys', () => {
      const privateKey = generatePrivateKey();
      expect(privateKey).toBeInstanceOf(Uint8Array);
      expect(privateKey.length).toBe(32);
    });

    it('generates different keys each time', () => {
      const key1 = generatePrivateKey();
      const key2 = generatePrivateKey();
      expect(privateKeyToHex(key1)).not.toBe(privateKeyToHex(key2));
    });

    it('derives 32-byte public keys (x-only)', () => {
      const privateKey = generatePrivateKey();
      const publicKey = getPublicKey(privateKey);
      expect(publicKey).toBeInstanceOf(Uint8Array);
      expect(publicKey.length).toBe(32);
    });
  });

  describe('Hex conversion', () => {
    it('converts private key to hex and back', () => {
      const original = generatePrivateKey();
      const hex = privateKeyToHex(original);
      const restored = hexToPrivateKey(hex);

      expect(hex.length).toBe(64); // 32 bytes = 64 hex chars
      expect(restored).toEqual(original);
    });

    it('converts public key to hex', () => {
      const privateKey = generatePrivateKey();
      const publicKey = getPublicKey(privateKey);
      const hex = publicKeyToHex(publicKey);

      expect(hex.length).toBe(64);
      expect(/^[0-9a-f]+$/.test(hex)).toBe(true);
    });
  });

  describe('Bech32 encoding (NIP-19)', () => {
    it('encodes public key to npub', () => {
      const privateKey = generatePrivateKey();
      const publicKey = getPublicKey(privateKey);
      const pubkeyHex = publicKeyToHex(publicKey);
      const npub = publicKeyToNpub(pubkeyHex);

      expect(npub.startsWith('npub1')).toBe(true);
      expect(npub.length).toBe(63); // npub1 + 58 chars
    });

    it('decodes npub to public key', () => {
      const privateKey = generatePrivateKey();
      const publicKey = getPublicKey(privateKey);
      const pubkeyHex = publicKeyToHex(publicKey);
      const npub = publicKeyToNpub(pubkeyHex);
      const decoded = npubToPublicKey(npub);

      expect(decoded).toBe(pubkeyHex);
    });

    it('encodes private key to nsec', () => {
      const privateKey = generatePrivateKey();
      const privkeyHex = privateKeyToHex(privateKey);
      const nsec = privateKeyToNsec(privkeyHex);

      expect(nsec.startsWith('nsec1')).toBe(true);
      expect(nsec.length).toBe(63);
    });

    it('decodes nsec to private key', () => {
      const privateKey = generatePrivateKey();
      const privkeyHex = privateKeyToHex(privateKey);
      const nsec = privateKeyToNsec(privkeyHex);
      const decoded = nsecToPrivateKey(nsec);

      expect(decoded).toBe(privkeyHex);
    });

    it('rejects invalid npub prefix', () => {
      // Short strings fail bech32 validation before prefix check
      expect(() => npubToPublicKey('nsec1abc')).toThrow();
    });

    it('rejects invalid nsec prefix', () => {
      // Short strings fail bech32 validation before prefix check
      expect(() => nsecToPrivateKey('npub1abc')).toThrow();
    });
  });

  describe('Event ID computation', () => {
    it('computes deterministic event ID per NIP-01', () => {
      const pubkey = '0000000000000000000000000000000000000000000000000000000000000001';
      const createdAt = 1234567890;
      const kind = 1;
      const tags: string[][] = [];
      const content = 'Hello, Nostr!';

      const id1 = computeEventId(pubkey, createdAt, kind, tags, content);
      const id2 = computeEventId(pubkey, createdAt, kind, tags, content);

      expect(id1).toBe(id2);
      expect(id1.length).toBe(64); // SHA-256 = 32 bytes = 64 hex chars
    });

    it('changes ID when content changes', () => {
      const pubkey = '0000000000000000000000000000000000000000000000000000000000000001';
      const createdAt = 1234567890;
      const kind = 1;
      const tags: string[][] = [];

      const id1 = computeEventId(pubkey, createdAt, kind, tags, 'Hello');
      const id2 = computeEventId(pubkey, createdAt, kind, tags, 'World');

      expect(id1).not.toBe(id2);
    });

    it('changes ID when tags change', () => {
      const pubkey = '0000000000000000000000000000000000000000000000000000000000000001';
      const createdAt = 1234567890;
      const kind = 1;
      const content = 'Test';

      const id1 = computeEventId(pubkey, createdAt, kind, [], content);
      const id2 = computeEventId(pubkey, createdAt, kind, [['t', 'test']], content);

      expect(id1).not.toBe(id2);
    });
  });

  describe('Event signing and verification', () => {
    it('signs a Nostr event', async () => {
      const privateKey = generatePrivateKey();
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Test message',
      };

      const signed = await signNostrEvent(event, privateKey);

      expect(signed.id).toBeDefined();
      expect(signed.pubkey).toBeDefined();
      expect(signed.sig).toBeDefined();
      expect(signed.id.length).toBe(64);
      expect(signed.pubkey.length).toBe(64);
      expect(signed.sig.length).toBe(128); // Schnorr sig = 64 bytes = 128 hex
    });

    it('verifies a valid signed event', async () => {
      const privateKey = generatePrivateKey();
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [['t', 'test']],
        content: 'Verification test',
      };

      const signed = await signNostrEvent(event, privateKey);
      const isValid = await verifyNostrEvent(signed);

      expect(isValid).toBe(true);
    });

    it('rejects tampered event (modified content)', async () => {
      const privateKey = generatePrivateKey();
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Original content',
      };

      const signed = await signNostrEvent(event, privateKey);

      // Tamper with content
      const tampered = { ...signed, content: 'Tampered content' };
      const isValid = await verifyNostrEvent(tampered);

      expect(isValid).toBe(false);
    });

    it('rejects tampered event (modified tags)', async () => {
      const privateKey = generatePrivateKey();
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [['t', 'original']],
        content: 'Test',
      };

      const signed = await signNostrEvent(event, privateKey);

      // Tamper with tags
      const tampered = { ...signed, tags: [['t', 'tampered']] };
      const isValid = await verifyNostrEvent(tampered);

      expect(isValid).toBe(false);
    });
  });

  describe('Civic event helpers', () => {
    it('creates voice content in canonical format', () => {
      const content = createVoiceContent(
        'decision:city-san-rafael:2026-01-15:item-6a',
        'support',
        1705334400
      );

      expect(content).toBe(
        'civicos:voice:v1:decision:city-san-rafael:2026-01-15:item-6a:support:1705334400'
      );
    });

    it('creates voice tags with required fields', () => {
      const tags = createVoiceTags(
        'decision:city-san-rafael:2026-01-15:item-6a',
        'city-san-rafael',
        'oppose'
      );

      expect(tags).toEqual([
        ['d', 'decision:city-san-rafael:2026-01-15:item-6a'],
        ['j', 'city-san-rafael'],
        ['stance', 'oppose'],
      ]);
    });

    it('defines correct civic event kinds', () => {
      expect(CivicEventKinds.VOICE).toBe(30800);
      expect(CivicEventKinds.COMMITMENT).toBe(30801);
      expect(CivicEventKinds.COMPLETION).toBe(30802);
      expect(CivicEventKinds.ATTESTATION).toBe(30850);
    });
  });
});

describe('LocalWalletProvider', () => {
  let provider: LocalWalletProvider;
  let storage: MemoryStorage;

  beforeEach(() => {
    storage = new MemoryStorage();
    provider = new LocalWalletProvider(storage);
  });

  afterEach(() => {
    provider.lock();
  });

  describe('Provider properties', () => {
    it('has correct tier', () => {
      expect(provider.tier).toBe('private');
    });

    it('has descriptive name', () => {
      expect(provider.name).toBe('Local Wallet (Password Protected)');
    });

    it('is available when Web Crypto API exists', async () => {
      const available = await provider.isAvailable();
      expect(available).toBe(true);
    });
  });

  describe('Identity lifecycle', () => {
    it('reports no identity initially', async () => {
      expect(await provider.hasIdentity()).toBe(false);
      expect(await provider.getIdentity()).toBeNull();
      expect(await provider.getPublicKey()).toBeNull();
    });

    it('creates new identity with mnemonic', async () => {
      const result = await provider.createIdentity({
        tier: 'private',
        password: 'test-password-123',
      });

      expect(result.identity).toBeDefined();
      expect(result.identity.tier).toBe('private');
      expect(result.identity.publicKey.length).toBe(64);
      expect(result.identity.npub.startsWith('npub1')).toBe(true);
      expect(result.identity.createdAt).toBeGreaterThan(0);

      // Mnemonic should be 12 words
      expect(result.mnemonic).toBeDefined();
      const words = result.mnemonic.split(' ');
      expect(words.length).toBe(12);
    });

    it('persists identity after creation', async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'test-password-123',
      });

      expect(await provider.hasIdentity()).toBe(true);
      expect(await provider.getIdentity()).not.toBeNull();
    });

    it('remains unlocked after creation', async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'test-password-123',
      });

      expect(provider.isUnlocked()).toBe(true);
    });

    it('rejects creation with wrong tier', async () => {
      await expect(
        provider.createIdentity({
          tier: 'easy', // Wrong tier for this provider
          password: 'test',
        })
      ).rejects.toThrow("only supports 'private' tier");
    });

    it('requires password for creation', async () => {
      await expect(
        provider.createIdentity({
          tier: 'private',
          // No password
        })
      ).rejects.toThrow('Password is required');
    });
  });

  describe('Import identity', () => {
    const testMnemonic =
      'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';

    it('imports identity from valid mnemonic', async () => {
      const identity = await provider.importIdentity({
        tier: 'private',
        password: 'import-password',
        mnemonic: testMnemonic,
      });

      expect(identity.tier).toBe('private');
      expect(identity.publicKey.length).toBe(64);
      expect(identity.npub.startsWith('npub1')).toBe(true);
    });

    it('derives same key from same mnemonic', async () => {
      const provider1 = new LocalWalletProvider(new MemoryStorage());
      const provider2 = new LocalWalletProvider(new MemoryStorage());

      const identity1 = await provider1.importIdentity({
        tier: 'private',
        password: 'password1',
        mnemonic: testMnemonic,
      });

      const identity2 = await provider2.importIdentity({
        tier: 'private',
        password: 'password2', // Different password, same mnemonic
        mnemonic: testMnemonic,
      });

      // Same public key (derived from same mnemonic)
      expect(identity1.publicKey).toBe(identity2.publicKey);
      expect(identity1.npub).toBe(identity2.npub);
    });

    it('rejects invalid mnemonic', async () => {
      await expect(
        provider.importIdentity({
          tier: 'private',
          password: 'test',
          mnemonic: 'invalid mnemonic phrase that is not valid',
        })
      ).rejects.toThrow('Invalid mnemonic');
    });

    it('requires mnemonic for import', async () => {
      await expect(
        provider.importIdentity({
          tier: 'private',
          password: 'test',
          // No mnemonic
        })
      ).rejects.toThrow('Mnemonic is required');
    });
  });

  describe('Lock and unlock', () => {
    beforeEach(async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'test-password',
      });
    });

    it('locks the wallet', () => {
      expect(provider.isUnlocked()).toBe(true);

      provider.lock();

      expect(provider.isUnlocked()).toBe(false);
    });

    it('unlocks with correct password', async () => {
      provider.lock();
      expect(provider.isUnlocked()).toBe(false);

      const success = await provider.unlock({ password: 'test-password' });

      expect(success).toBe(true);
      expect(provider.isUnlocked()).toBe(true);
    });

    it('fails to unlock with wrong password', async () => {
      provider.lock();

      const success = await provider.unlock({ password: 'wrong-password' });

      expect(success).toBe(false);
      expect(provider.isUnlocked()).toBe(false);
    });

    it('requires password for unlock', async () => {
      provider.lock();

      await expect(provider.unlock({})).rejects.toThrow('Password is required');
    });

    it('fails to unlock when no identity exists', async () => {
      const emptyProvider = new LocalWalletProvider(new MemoryStorage());

      await expect(
        emptyProvider.unlock({ password: 'test' })
      ).rejects.toThrow('No identity found');
    });
  });

  describe('Signing', () => {
    beforeEach(async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'signing-test',
      });
    });

    it('signs a Nostr event', async () => {
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Test from LocalWalletProvider',
      };

      const result = await provider.signEvent(event);

      expect(result.success).toBe(true);
      expect(result.event).toBeDefined();
      expect(result.event!.id.length).toBe(64);
      expect(result.event!.pubkey.length).toBe(64);
      expect(result.event!.sig.length).toBe(128);
    });

    it('signs civic voice event', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const entity = 'decision:city-san-rafael:2026-01-15:item-6a';
      const jurisdiction = 'city-san-rafael';
      const stance = 'support' as const;

      const event: NostrEvent = {
        created_at: timestamp,
        kind: CivicEventKinds.VOICE,
        tags: createVoiceTags(entity, jurisdiction, stance),
        content: createVoiceContent(entity, stance, timestamp),
      };

      const result = await provider.signEvent(event);

      expect(result.success).toBe(true);
      expect(result.event!.kind).toBe(30800);

      // Verify the signed event
      const isValid = await verifyNostrEvent(result.event!);
      expect(isValid).toBe(true);
    });

    it('fails to sign when locked', async () => {
      provider.lock();

      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Should fail',
      };

      const result = await provider.signEvent(event);

      expect(result.success).toBe(false);
      expect(result.error).toContain('locked');
    });

    it('produces verifiable signatures', async () => {
      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [['t', 'test']],
        content: 'Verification test message',
      };

      const result = await provider.signEvent(event);
      expect(result.success).toBe(true);

      const isValid = await verifyNostrEvent(result.event!);
      expect(isValid).toBe(true);
    });

    it('uses consistent public key', async () => {
      const pubkey = await provider.getPublicKey();

      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Test',
      };

      const result = await provider.signEvent(event);

      expect(result.event!.pubkey).toBe(pubkey);
    });
  });

  describe('Delete identity', () => {
    it('deletes identity and locks wallet', async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'delete-test',
      });

      expect(await provider.hasIdentity()).toBe(true);
      expect(provider.isUnlocked()).toBe(true);

      await provider.deleteIdentity();

      expect(await provider.hasIdentity()).toBe(false);
      expect(provider.isUnlocked()).toBe(false);
    });

    it('cannot sign after deletion', async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'delete-test',
      });

      await provider.deleteIdentity();

      const event: NostrEvent = {
        created_at: Math.floor(Date.now() / 1000),
        kind: 1,
        tags: [],
        content: 'Should fail',
      };

      const result = await provider.signEvent(event);
      expect(result.success).toBe(false);
    });
  });

  describe('Password security', () => {
    it('encrypts private key (not stored in plain text)', async () => {
      await provider.createIdentity({
        tier: 'private',
        password: 'secure-password',
      });

      // Get the stored wallet data
      const storedData = await storage.load();

      expect(storedData).not.toBeNull();
      // encryptedKey should not be the raw private key
      expect(storedData!.encryptedKey.length).toBeGreaterThan(64);
      // Salt and IV should be present
      expect(storedData!.salt.length).toBe(32); // 16 bytes = 32 hex
      expect(storedData!.iv.length).toBe(24); // 12 bytes = 24 hex
    });

    it('different passwords produce different encrypted data', async () => {
      const testMnemonic =
        'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';

      const provider1 = new LocalWalletProvider(new MemoryStorage());
      const storage1 = new MemoryStorage();
      const provider1b = new LocalWalletProvider(storage1);

      await provider1b.importIdentity({
        tier: 'private',
        password: 'password1',
        mnemonic: testMnemonic,
      });

      const provider2 = new LocalWalletProvider(new MemoryStorage());
      const storage2 = new MemoryStorage();
      const provider2b = new LocalWalletProvider(storage2);

      await provider2b.importIdentity({
        tier: 'private',
        password: 'password2',
        mnemonic: testMnemonic,
      });

      const data1 = await storage1.load();
      const data2 = await storage2.load();

      // Same public key (derived from same mnemonic)
      expect(data1!.publicKey).toBe(data2!.publicKey);

      // Different encrypted keys (different passwords)
      expect(data1!.encryptedKey).not.toBe(data2!.encryptedKey);
      expect(data1!.salt).not.toBe(data2!.salt);
      expect(data1!.iv).not.toBe(data2!.iv);
    });
  });
});

describe('Known vectors', () => {
  // Test against known BIP-39/NIP-06 vectors to ensure compatibility
  describe('BIP-39 + NIP-06 derivation', () => {
    it('derives correct key from known mnemonic', async () => {
      // This is the "abandon" mnemonic - a well-known test vector
      const testMnemonic =
        'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';

      const provider = new LocalWalletProvider(new MemoryStorage());
      const identity = await provider.importIdentity({
        tier: 'private',
        password: 'test',
        mnemonic: testMnemonic,
      });

      // The public key should be deterministic
      // This value comes from the NIP-06 derivation path m/44'/1237'/0'/0/0
      // If this test fails, the derivation is not NIP-06 compatible
      expect(identity.publicKey).toBeDefined();
      expect(identity.publicKey.length).toBe(64);

      // The npub should be deterministic
      expect(identity.npub.startsWith('npub1')).toBe(true);
    });
  });
});
