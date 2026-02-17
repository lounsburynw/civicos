import { describe, it, expect } from 'vitest';
import { hexToBytes } from '@noble/hashes/utils';
import { serializeEvent, computeEventId, signEvent, verifyEvent } from './event.js';
import type { UnsignedEvent } from './types.js';
import vectors from '../../test-vectors.json';

const privateKey = hexToBytes(vectors.privateKey);

describe('serializeEvent', () => {
  it('produces compact JSON with no whitespace', () => {
    const event: UnsignedEvent = {
      pubkey: 'a'.repeat(64),
      created_at: 1000,
      kind: 1,
      tags: [['t', 'test']],
      content: 'hello',
    };
    const serialized = serializeEvent(event);
    expect(serialized).not.toContain(' ');
    expect(serialized).toMatch(/^\[0,"/);
  });

  it('matches expectedSerialized from test vectors', () => {
    for (const v of vectors.events) {
      const serialized = serializeEvent(v.unsigned);
      expect(serialized, `serialization mismatch for ${v.name}`).toBe(v.expectedSerialized);
    }
  });
});

describe('computeEventId', () => {
  it('matches expectedEventId from test vectors', () => {
    for (const v of vectors.events) {
      const id = computeEventId(v.unsigned);
      expect(id, `event ID mismatch for ${v.name}`).toBe(v.expectedEventId);
    }
  });

  it('is deterministic', () => {
    const event: UnsignedEvent = vectors.events[0].unsigned;
    const id1 = computeEventId(event);
    const id2 = computeEventId(event);
    expect(id1).toBe(id2);
  });
});

describe('signEvent + verifyEvent', () => {
  it('roundtrip: sign then verify', async () => {
    const unsigned: UnsignedEvent = vectors.events[0].unsigned;
    const signed = await signEvent(unsigned, privateKey);

    expect(signed.id).toBe(vectors.events[0].expectedEventId);
    expect(signed.sig).toHaveLength(128);
    expect(await verifyEvent(signed)).toBe(true);
  });

  it('frozen signatures from test vectors verify', async () => {
    for (const v of vectors.events) {
      const signed = { ...v.unsigned, id: v.expectedEventId, sig: v.expectedSig };
      expect(await verifyEvent(signed), `verification failed for ${v.name}`).toBe(true);
    }
  });

  it('rejects tampered content', async () => {
    const v = vectors.events[0];
    const tampered = {
      ...v.unsigned,
      content: 'TAMPERED',
      id: v.expectedEventId,
      sig: v.expectedSig,
    };
    expect(await verifyEvent(tampered)).toBe(false);
  });

  it('rejects tampered tags', async () => {
    const v = vectors.events[0];
    const tampered = {
      ...v.unsigned,
      tags: [['d', 'TAMPERED']],
      id: v.expectedEventId,
      sig: v.expectedSig,
    };
    expect(await verifyEvent(tampered)).toBe(false);
  });

  it('rejects tampered kind', async () => {
    const v = vectors.events[0];
    const tampered = {
      ...v.unsigned,
      kind: 99999,
      id: v.expectedEventId,
      sig: v.expectedSig,
    };
    expect(await verifyEvent(tampered)).toBe(false);
  });
});
