import { schnorr } from '@noble/curves/secp256k1';
import { bytesToHex, hexToBytes } from '@noble/hashes/utils';
import { sha256Hex } from '../hash.js';
import type { UnsignedEvent, SignedEvent } from './types.js';

export function serializeEvent(event: UnsignedEvent): string {
  return JSON.stringify([
    0,
    event.pubkey,
    event.created_at,
    event.kind,
    event.tags,
    event.content
  ]);
}

export function computeEventId(event: UnsignedEvent): string {
  return sha256Hex(serializeEvent(event));
}

export async function signEvent(
  event: UnsignedEvent,
  privateKey: Uint8Array
): Promise<SignedEvent> {
  const id = computeEventId(event);
  const idBytes = hexToBytes(id);
  const sig = bytesToHex(schnorr.sign(idBytes, privateKey));
  return { ...event, id, sig };
}

export async function verifyEvent(event: SignedEvent): Promise<boolean> {
  const expectedId = computeEventId(event);
  if (expectedId !== event.id) return false;
  const idBytes = hexToBytes(event.id);
  const sigBytes = hexToBytes(event.sig);
  const pubBytes = hexToBytes(event.pubkey);
  return schnorr.verify(sigBytes, idBytes, pubBytes);
}
