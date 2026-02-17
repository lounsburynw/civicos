import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from '@noble/hashes/utils';

export function sha256Hex(data: string): string {
  const encoded = new TextEncoder().encode(data);
  return bytesToHex(sha256(encoded));
}
