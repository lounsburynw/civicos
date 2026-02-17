import { describe, it, expect } from 'vitest';
import { sha256Hex } from './hash.js';
import vectors from '../test-vectors.json';

describe('sha256Hex', () => {
  it('produces correct hash for known input', () => {
    // SHA-256("test") is a well-known value
    const hash = sha256Hex('test');
    expect(hash).toBe('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08');
  });

  it('produces correct hash for empty string', () => {
    const hash = sha256Hex('');
    expect(hash).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
  });

  it('matches message vector hashes', () => {
    for (const v of vectors.messages) {
      const hash = sha256Hex(v.message);
      expect(hash, `hash mismatch for ${v.name}`).toBe(v.expectedHash);
    }
  });
});
