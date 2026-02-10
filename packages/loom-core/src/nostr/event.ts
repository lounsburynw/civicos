import { schnorr, etc } from '@noble/secp256k1';
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

export async function computeEventId(event: UnsignedEvent): Promise<string> {
  return sha256Hex(serializeEvent(event));
}

export async function signEvent(
  event: UnsignedEvent,
  privateKey: Uint8Array
): Promise<SignedEvent> {
  const id = await computeEventId(event);
  const idBytes = etc.hexToBytes(id);
  const sig = etc.bytesToHex(await schnorr.signAsync(idBytes, privateKey));
  return { ...event, id, sig };
}

export async function verifyEvent(event: SignedEvent): Promise<boolean> {
  const expectedId = await computeEventId(event);
  if (expectedId !== event.id) return false;
  const idBytes = etc.hexToBytes(event.id);
  const sigBytes = etc.hexToBytes(event.sig);
  const pubBytes = etc.hexToBytes(event.pubkey);
  return schnorr.verifyAsync(sigBytes, idBytes, pubBytes);
}
