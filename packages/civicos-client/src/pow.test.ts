import { describe, it, assert } from 'vitest';
import { minePoW, countLeadingZeroBits, type MinableEvent } from './pow.js';

describe('countLeadingZeroBits', () => {
  it('counts 0 bits for 0xff...', () => {
    assert.equal(countLeadingZeroBits('ff00000000000000000000000000000000000000000000000000000000000000'), 0);
  });

  it('counts 8 bits for 00ff...', () => {
    assert.equal(countLeadingZeroBits('00ff000000000000000000000000000000000000000000000000000000000000'), 8);
  });

  it('counts 16 bits for 0000ff...', () => {
    assert.equal(countLeadingZeroBits('0000ff0000000000000000000000000000000000000000000000000000000000'), 16);
  });

  it('counts partial bits correctly', () => {
    // 0x01 = 0b00000001 → 7 leading zeros in that byte
    assert.equal(countLeadingZeroBits('0100000000000000000000000000000000000000000000000000000000000000'), 7);
    // 0x07 = 0b00000111 → 5 leading zeros
    assert.equal(countLeadingZeroBits('0700000000000000000000000000000000000000000000000000000000000000'), 5);
    // 0x0001 → 8 + 7 = 15 leading zero bits
    assert.equal(countLeadingZeroBits('0001000000000000000000000000000000000000000000000000000000000000'), 15);
  });
});

describe('minePoW', () => {
  const testEvent: MinableEvent = {
    pubkey: 'a'.repeat(64),
    created_at: 1700000000,
    kind: 30800,
    tags: [['d', 'test-entity'], ['j', 'city-san-rafael'], ['stance', 'support']],
    content: 'civicos:voice:v1:test-entity:support:1700000000',
  };

  it('returns event unchanged for difficulty 0', () => {
    const result = minePoW(testEvent, 0);
    assert.deepEqual(result, testEvent);
  });

  it('mines 8-bit PoW successfully', () => {
    const result = minePoW(testEvent, 8);
    assert.ok(result, 'should find a valid nonce');
    // Verify nonce tag was added
    const nonceTag = result!.tags.find(t => t[0] === 'nonce');
    assert.ok(nonceTag, 'should have nonce tag');
    assert.equal(nonceTag![2], '8', 'nonce tag should declare target difficulty');
  });

  it('mines 16-bit PoW successfully (production difficulty)', () => {
    const result = minePoW(testEvent, 16);
    assert.ok(result, 'should find a valid nonce for 16-bit difficulty');
    const nonceTag = result!.tags.find(t => t[0] === 'nonce');
    assert.ok(nonceTag, 'should have nonce tag');
    assert.equal(nonceTag![2], '16');
  });

  it('preserves original tags and adds nonce', () => {
    const result = minePoW(testEvent, 8);
    assert.ok(result);
    // Original tags should be present
    assert.ok(result!.tags.find(t => t[0] === 'd' && t[1] === 'test-entity'));
    assert.ok(result!.tags.find(t => t[0] === 'j' && t[1] === 'city-san-rafael'));
    assert.ok(result!.tags.find(t => t[0] === 'stance' && t[1] === 'support'));
    // Nonce tag should be last
    assert.equal(result!.tags[result!.tags.length - 1][0], 'nonce');
  });

  it('does not mutate the original event', () => {
    const originalTags = [...testEvent.tags.map(t => [...t])];
    minePoW(testEvent, 8);
    assert.deepEqual(testEvent.tags, originalTags);
  });

  it('returns null when max iterations exceeded', () => {
    const result = minePoW(testEvent, 64, 100); // 64 bits is impossible in 100 iterations
    assert.equal(result, null);
  });

  it('replaces existing nonce tag on re-mine', () => {
    const eventWithNonce: MinableEvent = {
      ...testEvent,
      tags: [...testEvent.tags, ['nonce', '999', '8']],
    };
    const result = minePoW(eventWithNonce, 8);
    assert.ok(result);
    const nonceTags = result!.tags.filter(t => t[0] === 'nonce');
    assert.equal(nonceTags.length, 1, 'should have exactly one nonce tag');
  });
});
