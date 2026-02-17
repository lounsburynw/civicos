import { describe, it, expect } from 'vitest';
import { hexToBytes } from '@noble/hashes/utils';
import { signMessage, verifyMessage } from './message.js';
import vectors from '../../test-vectors.json';

const privateKey = hexToBytes(vectors.privateKey);

describe('signMessage', () => {
  it('hash matches expectedHash from test vectors', async () => {
    for (const v of vectors.messages) {
      const { messageHash } = await signMessage(v.message, privateKey);
      expect(messageHash, `hash mismatch for ${v.name}`).toBe(v.expectedHash);
    }
  });

  it('roundtrip: sign then verify', async () => {
    const { signature } = await signMessage('roundtrip test', privateKey);
    const valid = await verifyMessage('roundtrip test', signature, vectors.publicKey);
    expect(valid).toBe(true);
  });
});

describe('verifyMessage', () => {
  it('frozen signatures from test vectors verify', async () => {
    for (const v of vectors.messages) {
      const valid = await verifyMessage(v.message, v.expectedSig, vectors.publicKey);
      expect(valid, `verification failed for ${v.name}`).toBe(true);
    }
  });

  it('rejects wrong message', async () => {
    const v = vectors.messages[0];
    const valid = await verifyMessage('wrong message', v.expectedSig, vectors.publicKey);
    expect(valid).toBe(false);
  });

  it('rejects wrong public key', async () => {
    const v = vectors.messages[0];
    const fakeKey = 'a'.repeat(64);
    const valid = await verifyMessage(v.message, v.expectedSig, fakeKey);
    expect(valid).toBe(false);
  });
});
