import { schnorr, etc } from '@noble/secp256k1';
import { sha256Hex } from '../hash.js';
import type { MessageSignature } from './types.js';

export async function signMessage(
  message: string,
  privateKey: Uint8Array
): Promise<MessageSignature> {
  const messageHash = await sha256Hex(message);
  const hashBytes = etc.hexToBytes(messageHash);
  const signature = etc.bytesToHex(await schnorr.signAsync(hashBytes, privateKey));
  return { messageHash, signature };
}

export async function verifyMessage(
  message: string,
  signature: string,
  publicKey: string
): Promise<boolean> {
  const messageHash = await sha256Hex(message);
  const hashBytes = etc.hexToBytes(messageHash);
  const sigBytes = etc.hexToBytes(signature);
  const pubBytes = etc.hexToBytes(publicKey);
  return schnorr.verifyAsync(sigBytes, hashBytes, pubBytes);
}
