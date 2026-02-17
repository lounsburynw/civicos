/**
 * Cryptographic utilities for Nostr signing.
 *
 * Delegates to loom-core for core crypto (SHA-256, Schnorr, bech32).
 * Extension-specific wrappers bridge loom-core's strict types with the
 * extension's NostrEvent (which has optional pubkey/id/sig fields).
 */

import { schnorr } from '@noble/curves/secp256k1';
import { bytesToHex, hexToBytes, randomBytes } from '@noble/hashes/utils';
import { sha256Hex } from 'loom-core';
import {
  computeEventId as loomComputeEventId,
  signEvent as loomSignEvent,
  verifyEvent as loomVerifyEvent,
  publicKeyToNpub,
  npubToPublicKey,
  privateKeyToNsec,
  nsecToPrivateKey,
} from 'loom-core/nostr';
import type { NostrEvent, SignedNostrEvent } from './types.js';

// Re-export loom-core utilities directly
export { sha256Hex, publicKeyToNpub, npubToPublicKey, privateKeyToNsec, nsecToPrivateKey };

export function generatePrivateKey(): Uint8Array {
  return randomBytes(32);
}

export function getPublicKey(privateKey: Uint8Array): Uint8Array {
  return schnorr.getPublicKey(privateKey);
}

export function publicKeyToHex(publicKey: Uint8Array): string {
  return bytesToHex(publicKey);
}

export function privateKeyToHex(privateKey: Uint8Array): string {
  return bytesToHex(privateKey);
}

export function hexToPrivateKey(hex: string): Uint8Array {
  return hexToBytes(hex);
}

/**
 * Compute the Nostr event ID per NIP-01.
 * Convenience wrapper that takes individual params (extension API shape).
 */
export function computeEventId(
  pubkey: string,
  createdAt: number,
  kind: number,
  tags: string[][],
  content: string
): string {
  return loomComputeEventId({ pubkey, created_at: createdAt, kind, tags, content });
}

export async function schnorrSign(
  message: Uint8Array,
  privateKey: Uint8Array
): Promise<Uint8Array> {
  return schnorr.sign(message, privateKey);
}

export async function schnorrVerify(
  signature: Uint8Array,
  message: Uint8Array,
  publicKey: Uint8Array
): Promise<boolean> {
  return schnorr.verify(signature, message, publicKey);
}

/**
 * Sign a Nostr event with a private key.
 * Bridges extension's NostrEvent (optional pubkey) to loom-core's UnsignedEvent (required pubkey).
 */
export async function signNostrEvent(
  event: NostrEvent,
  privateKey: Uint8Array
): Promise<SignedNostrEvent> {
  const publicKey = getPublicKey(privateKey);
  const pubkeyHex = publicKeyToHex(publicKey);

  const signed = await loomSignEvent(
    {
      pubkey: pubkeyHex,
      created_at: event.created_at,
      kind: event.kind,
      tags: event.tags,
      content: event.content,
    },
    privateKey
  );

  return {
    ...event,
    id: signed.id,
    pubkey: signed.pubkey,
    sig: signed.sig,
  };
}

/**
 * Verify a signed Nostr event.
 */
export async function verifyNostrEvent(event: SignedNostrEvent): Promise<boolean> {
  return loomVerifyEvent({
    pubkey: event.pubkey,
    created_at: event.created_at,
    kind: event.kind,
    tags: event.tags,
    content: event.content,
    id: event.id,
    sig: event.sig,
  });
}
