/**
 * Cryptographic utilities for Nostr signing.
 *
 * Uses @noble/curves/secp256k1 for BIP-340 Schnorr signatures (Nostr-compatible).
 * Uses @noble/hashes for SHA-256 and other hash functions.
 */

import { secp256k1, schnorr } from '@noble/curves/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex, hexToBytes, randomBytes } from '@noble/hashes/utils';
import type { NostrEvent, SignedNostrEvent } from './types.js';

/**
 * Generate a new random private key.
 */
export function generatePrivateKey(): Uint8Array {
  return randomBytes(32);
}

/**
 * Derive public key from private key.
 * Returns the x-only public key (32 bytes) per BIP-340.
 */
export function getPublicKey(privateKey: Uint8Array): Uint8Array {
  // schnorr.getPublicKey returns x-only public key (32 bytes) per BIP-340
  return schnorr.getPublicKey(privateKey);
}

/**
 * Convert public key bytes to hex string.
 */
export function publicKeyToHex(publicKey: Uint8Array): string {
  return bytesToHex(publicKey);
}

/**
 * Convert private key bytes to hex string.
 */
export function privateKeyToHex(privateKey: Uint8Array): string {
  return bytesToHex(privateKey);
}

/**
 * Convert hex string to bytes.
 */
export function hexToPrivateKey(hex: string): Uint8Array {
  return hexToBytes(hex);
}

/**
 * Compute SHA-256 hash and return as hex string.
 * Useful for generating deterministic IDs from descriptions.
 */
export function sha256Hex(input: string): string {
  const hash = sha256(new TextEncoder().encode(input));
  return bytesToHex(hash);
}

/**
 * Compute the Nostr event ID per NIP-01.
 *
 * The ID is the SHA-256 hash of the serialized event:
 * [0, pubkey, created_at, kind, tags, content]
 */
export function computeEventId(
  pubkey: string,
  createdAt: number,
  kind: number,
  tags: string[][],
  content: string
): string {
  const serialized = JSON.stringify([0, pubkey, createdAt, kind, tags, content]);
  const hash = sha256(new TextEncoder().encode(serialized));
  return bytesToHex(hash);
}

/**
 * Sign a message using BIP-340 Schnorr signature.
 */
export async function schnorrSign(
  message: Uint8Array,
  privateKey: Uint8Array
): Promise<Uint8Array> {
  return schnorr.sign(message, privateKey);
}

/**
 * Verify a BIP-340 Schnorr signature.
 */
export async function schnorrVerify(
  signature: Uint8Array,
  message: Uint8Array,
  publicKey: Uint8Array
): Promise<boolean> {
  return schnorr.verify(signature, message, publicKey);
}

/**
 * Sign a Nostr event with a private key.
 *
 * This:
 * 1. Computes the event ID from the canonical serialization
 * 2. Signs the event ID with BIP-340 Schnorr
 * 3. Returns the complete signed event
 */
export async function signNostrEvent(
  event: NostrEvent,
  privateKey: Uint8Array
): Promise<SignedNostrEvent> {
  const publicKey = getPublicKey(privateKey);
  const pubkeyHex = publicKeyToHex(publicKey);

  const eventId = computeEventId(
    pubkeyHex,
    event.created_at,
    event.kind,
    event.tags,
    event.content
  );

  const eventIdBytes = hexToBytes(eventId);
  const signature = await schnorrSign(eventIdBytes, privateKey);

  return {
    ...event,
    id: eventId,
    pubkey: pubkeyHex,
    sig: bytesToHex(signature),
  };
}

/**
 * Verify a signed Nostr event.
 */
export async function verifyNostrEvent(event: SignedNostrEvent): Promise<boolean> {
  // Recompute the event ID
  const expectedId = computeEventId(
    event.pubkey,
    event.created_at,
    event.kind,
    event.tags,
    event.content
  );

  // Check ID matches
  if (event.id !== expectedId) {
    return false;
  }

  // Verify signature
  const eventIdBytes = hexToBytes(event.id);
  const signatureBytes = hexToBytes(event.sig);
  const publicKeyBytes = hexToBytes(event.pubkey);

  return schnorrVerify(signatureBytes, eventIdBytes, publicKeyBytes);
}

/**
 * Encode a public key to npub (NIP-19 bech32 format).
 */
export function publicKeyToNpub(publicKey: string): string {
  // Simple implementation - bech32 encoding
  // For production, use a proper bech32 library
  const words = convertBits(hexToBytes(publicKey), 8, 5, true);
  return bech32Encode('npub', words);
}

/**
 * Decode npub to hex public key.
 */
export function npubToPublicKey(npub: string): string {
  const { prefix, words } = bech32Decode(npub);
  if (prefix !== 'npub') {
    throw new Error(`Invalid npub prefix: ${prefix}`);
  }
  const data = convertBits(words, 5, 8, false);
  return bytesToHex(new Uint8Array(data));
}

/**
 * Encode a private key to nsec (NIP-19 bech32 format).
 */
export function privateKeyToNsec(privateKey: string): string {
  const words = convertBits(hexToBytes(privateKey), 8, 5, true);
  return bech32Encode('nsec', words);
}

/**
 * Decode nsec to hex private key.
 */
export function nsecToPrivateKey(nsec: string): string {
  const { prefix, words } = bech32Decode(nsec);
  if (prefix !== 'nsec') {
    throw new Error(`Invalid nsec prefix: ${prefix}`);
  }
  const data = convertBits(words, 5, 8, false);
  return bytesToHex(new Uint8Array(data));
}

// Bech32 implementation (minimal, for npub/nsec only)
const BECH32_ALPHABET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';

function bech32Polymod(values: number[]): number {
  const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
  let chk = 1;
  for (const v of values) {
    const top = chk >> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) {
      if ((top >> i) & 1) {
        chk ^= GEN[i];
      }
    }
  }
  return chk;
}

function bech32HrpExpand(hrp: string): number[] {
  const result: number[] = [];
  for (let i = 0; i < hrp.length; i++) {
    result.push(hrp.charCodeAt(i) >> 5);
  }
  result.push(0);
  for (let i = 0; i < hrp.length; i++) {
    result.push(hrp.charCodeAt(i) & 31);
  }
  return result;
}

function bech32CreateChecksum(hrp: string, data: number[]): number[] {
  const values = bech32HrpExpand(hrp).concat(data).concat([0, 0, 0, 0, 0, 0]);
  const polymod = bech32Polymod(values) ^ 1;
  const result: number[] = [];
  for (let i = 0; i < 6; i++) {
    result.push((polymod >> (5 * (5 - i))) & 31);
  }
  return result;
}

function bech32VerifyChecksum(hrp: string, data: number[]): boolean {
  return bech32Polymod(bech32HrpExpand(hrp).concat(data)) === 1;
}

function bech32Encode(hrp: string, data: number[]): string {
  const checksum = bech32CreateChecksum(hrp, data);
  const combined = data.concat(checksum);
  let result = hrp + '1';
  for (const d of combined) {
    result += BECH32_ALPHABET[d];
  }
  return result;
}

function bech32Decode(str: string): { prefix: string; words: number[] } {
  const pos = str.lastIndexOf('1');
  if (pos < 1 || pos + 7 > str.length) {
    throw new Error('Invalid bech32 string');
  }

  const hrp = str.slice(0, pos).toLowerCase();
  const data: number[] = [];

  for (let i = pos + 1; i < str.length; i++) {
    const idx = BECH32_ALPHABET.indexOf(str[i].toLowerCase());
    if (idx === -1) {
      throw new Error(`Invalid bech32 character: ${str[i]}`);
    }
    data.push(idx);
  }

  if (!bech32VerifyChecksum(hrp, data)) {
    throw new Error('Invalid bech32 checksum');
  }

  return { prefix: hrp, words: data.slice(0, -6) };
}

function convertBits(
  data: Uint8Array | number[],
  fromBits: number,
  toBits: number,
  pad: boolean
): number[] {
  let acc = 0;
  let bits = 0;
  const result: number[] = [];
  const maxv = (1 << toBits) - 1;

  for (const value of data) {
    acc = (acc << fromBits) | value;
    bits += fromBits;
    while (bits >= toBits) {
      bits -= toBits;
      result.push((acc >> bits) & maxv);
    }
  }

  if (pad) {
    if (bits > 0) {
      result.push((acc << (toBits - bits)) & maxv);
    }
  } else if (bits >= fromBits || ((acc << (toBits - bits)) & maxv) !== 0) {
    throw new Error('Invalid bit conversion');
  }

  return result;
}
