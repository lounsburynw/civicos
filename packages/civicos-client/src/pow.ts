/**
 * NIP-13 proof-of-work mining for Nostr events.
 *
 * Adds a nonce tag and increments it until the event ID
 * (SHA-256 of serialized event) has sufficient leading zero bits.
 *
 * Server-side verification: acceptance.py:_verify_pow()
 * Spec: https://github.com/nostr-protocol/nips/blob/master/13.md
 */

import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from '@noble/hashes/utils';

export interface MinableEvent {
  pubkey: string;
  created_at: number;
  kind: number;
  tags: string[][];
  content: string;
}

/**
 * Count leading zero bits in a hex event ID.
 * Matches the server-side algorithm in acceptance.py:_verify_pow().
 */
export function countLeadingZeroBits(hexId: string): number {
  const bytes = hexToBytes(hexId);
  let zeros = 0;
  for (const byte of bytes) {
    if (byte === 0) {
      zeros += 8;
    } else {
      zeros += Math.clz32(byte) - 24; // clz32 counts for 32-bit, byte is 8-bit
      break;
    }
  }
  return zeros;
}

/**
 * Compute a Nostr event ID (SHA-256 of canonical serialization).
 * Inlined to avoid depending on loom-core.
 */
function computeEventId(event: MinableEvent): string {
  const serialized = JSON.stringify([
    0,
    event.pubkey,
    event.created_at,
    event.kind,
    event.tags,
    event.content,
  ]);
  const encoded = new TextEncoder().encode(serialized);
  return bytesToHex(sha256(encoded));
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/**
 * Mine proof-of-work for a Nostr event by adding a nonce tag.
 *
 * Adds ['nonce', counter, targetDifficulty] per NIP-13 and increments
 * the counter until the event ID has >= difficulty leading zero bits.
 *
 * @param event - Unsigned event with pubkey set
 * @param difficulty - Required leading zero bits (16 = ~65K hashes, ~50-200ms)
 * @param maxIterations - Safety limit to prevent infinite loops
 * @returns Event with nonce tag added, or null if max iterations exceeded
 */
export function minePoW(
  event: MinableEvent,
  difficulty: number,
  maxIterations: number = 10_000_000,
): MinableEvent | null {
  if (difficulty <= 0) return event;

  // Remove any existing nonce tag
  const baseTags = event.tags.filter(t => t[0] !== 'nonce');
  const targetStr = difficulty.toString();

  for (let nonce = 0; nonce < maxIterations; nonce++) {
    const tags = [...baseTags, ['nonce', nonce.toString(), targetStr]];
    const candidate: MinableEvent = { ...event, tags };
    const eventId = computeEventId(candidate);

    if (countLeadingZeroBits(eventId) >= difficulty) {
      return candidate;
    }
  }

  return null; // Exhausted iterations
}
