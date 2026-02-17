import { schnorr } from '@noble/curves/secp256k1';
import { bytesToHex, hexToBytes } from '@noble/hashes/utils';
import { sha256Hex } from '../hash.js';
import type { MessageSignature } from './types.js';

export async function signMessage(
  message: string,
  privateKey: Uint8Array
): Promise<MessageSignature> {
  const messageHash = sha256Hex(message);
  const hashBytes = hexToBytes(messageHash);
  const signature = bytesToHex(schnorr.sign(hashBytes, privateKey));
  return { messageHash, signature };
}

export async function verifyMessage(
  message: string,
  signature: string,
  publicKey: string
): Promise<boolean> {
  const messageHash = sha256Hex(message);
  const hashBytes = hexToBytes(messageHash);
  const sigBytes = hexToBytes(signature);
  const pubBytes = hexToBytes(publicKey);
  return schnorr.verify(sigBytes, hashBytes, pubBytes);
}
