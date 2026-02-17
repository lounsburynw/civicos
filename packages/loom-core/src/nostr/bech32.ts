import { bech32 } from '@scure/base';
import { hexToBytes, bytesToHex } from '@noble/hashes/utils';

export function publicKeyToNpub(pubkeyHex: string): string {
  const words = bech32.toWords(hexToBytes(pubkeyHex));
  return bech32.encode('npub', words, 90);
}

export function npubToPublicKey(npub: string): string {
  const { prefix, words } = bech32.decode(npub as `${string}1${string}`, 90);
  if (prefix !== 'npub') {
    throw new Error(`Invalid npub prefix: ${prefix}`);
  }
  return bytesToHex(bech32.fromWords(words));
}

export function privateKeyToNsec(privkeyHex: string): string {
  const words = bech32.toWords(hexToBytes(privkeyHex));
  return bech32.encode('nsec', words, 90);
}

export function nsecToPrivateKey(nsec: string): string {
  const { prefix, words } = bech32.decode(nsec as `${string}1${string}`, 90);
  if (prefix !== 'nsec') {
    throw new Error(`Invalid nsec prefix: ${prefix}`);
  }
  return bytesToHex(bech32.fromWords(words));
}
