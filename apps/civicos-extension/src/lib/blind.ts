/**
 * Schnorr blind signature client for privacy-preserving token spending.
 *
 * Ports the user-side operations from civicos-relay/voice/blind.py:
 *   blind()   — blind a message before sending challenge to issuer
 *   unblind() — unblind issuer's signature into a spendable token
 *   verifyToken() — local verification (optional, relay does the real check)
 *   generateTokenMessage() — random 32-byte nonce
 *   computeTokenHash() — SHA-256(message || signature) for dedup
 *
 * Uses @noble/curves/secp256k1 for point arithmetic and @noble/hashes for SHA-256.
 * No Chrome APIs — pure crypto, testable anywhere.
 */

import { secp256k1 } from '@noble/curves/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex, hexToBytes, randomBytes, concatBytes } from '@noble/hashes/utils';

const Point = secp256k1.ProjectivePoint;
const N = secp256k1.CURVE.n;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SpendableToken {
  /** Unique nonce, 64-char hex (32 bytes). */
  message: string;
  /** R' || s', 130-char hex (33 + 32 = 65 bytes). */
  signature: string;
  /** Compressed issuer public key, 66-char hex (33 bytes). */
  issuer_pubkey: string;
}

export interface BlindingContext {
  alpha: bigint;
  beta: bigint;
  blindedNonce: Uint8Array; // R' compressed, 33 bytes
  message: Uint8Array; // 32 bytes
}

// ---------------------------------------------------------------------------
// Scalar helpers
// ---------------------------------------------------------------------------

function bytesToBigInt(bytes: Uint8Array): bigint {
  return BigInt('0x' + bytesToHex(bytes));
}

function bigIntToBytes32(n: bigint): Uint8Array {
  const hex = n.toString(16).padStart(64, '0');
  return hexToBytes(hex);
}

/** Random scalar in [1, N-1]. */
function randomScalar(): bigint {
  // Generate 32 random bytes, reduce mod (N-1), then add 1.
  // This gives a uniform distribution in [1, N-1].
  const raw = bytesToBigInt(randomBytes(32));
  return (raw % (N - 1n)) + 1n;
}

// ---------------------------------------------------------------------------
// Core protocol — user side
// ---------------------------------------------------------------------------

/**
 * Blind a token message for the issuer to sign.
 *
 * @param message     32-byte token nonce (from generateTokenMessage)
 * @param issuerPubkey  Issuer's compressed public key (33 bytes)
 * @param noncePoint    Issuer's nonce point R (33 bytes compressed)
 * @returns  { challenge: 32-byte blinded challenge to send to issuer,
 *             ctx: BlindingContext kept secret until unblinding }
 */
export function blind(
  message: Uint8Array,
  issuerPubkey: Uint8Array,
  noncePoint: Uint8Array,
): { challenge: Uint8Array; ctx: BlindingContext } {
  const alpha = randomScalar();
  const beta = randomScalar();

  const R = Point.fromHex(noncePoint);
  const P = Point.fromHex(issuerPubkey);

  // R' = R + α·G + β·P
  const alphaG = Point.BASE.multiply(alpha);
  const betaP = P.multiply(beta);
  const RPrime = R.add(alphaG).add(betaP);
  const RPrimeBytes = RPrime.toRawBytes(true); // 33 bytes compressed

  // e' = SHA-256(R' || P || m) mod N
  const h = sha256(concatBytes(RPrimeBytes, issuerPubkey, message));
  const ePrime = bytesToBigInt(h) % N;

  // Blinded challenge: e = (e' + β) mod N
  const e = (ePrime + beta) % N;

  return {
    challenge: bigIntToBytes32(e),
    ctx: { alpha, beta, blindedNonce: RPrimeBytes, message },
  };
}

/**
 * Unblind the issuer's signature to produce a spendable token.
 *
 * @param blindSig     32-byte blind signature from issuer
 * @param ctx          BlindingContext from the blind() call
 * @param issuerPubkey Issuer's compressed public key (33 bytes)
 */
export function unblind(
  blindSig: Uint8Array,
  ctx: BlindingContext,
  issuerPubkey: Uint8Array,
): SpendableToken {
  const s = bytesToBigInt(blindSig);

  // s' = (s + α) mod N
  const sPrime = (s + ctx.alpha) % N;
  const sigBytes = concatBytes(ctx.blindedNonce, bigIntToBytes32(sPrime));

  return {
    message: bytesToHex(ctx.message),
    signature: bytesToHex(sigBytes),
    issuer_pubkey: bytesToHex(issuerPubkey),
  };
}

/**
 * Verify a token's Schnorr signature against the issuer's public key.
 * Checks: s'·G == R' + H(R'||P||m)·P
 */
export function verifyToken(token: SpendableToken): boolean {
  try {
    const sigBytes = hexToBytes(token.signature);
    if (sigBytes.length !== 65) return false;

    const RPrimeBytes = sigBytes.slice(0, 33);
    const sPrimeBytes = sigBytes.slice(33, 65);
    const issuerPubkeyBytes = hexToBytes(token.issuer_pubkey);
    const messageBytes = hexToBytes(token.message);

    const sPrimeInt = bytesToBigInt(sPrimeBytes);
    if (sPrimeInt === 0n || sPrimeInt >= N) return false;

    const P = Point.fromHex(issuerPubkeyBytes);

    // e' = SHA-256(R' || P || m) mod N
    const h = sha256(concatBytes(RPrimeBytes, issuerPubkeyBytes, messageBytes));
    const ePrime = bytesToBigInt(h) % N;

    // Left: s'·G
    const lhs = Point.BASE.multiply(sPrimeInt);

    // Right: R' + e'·P
    const RPrime = Point.fromHex(RPrimeBytes);
    const ePrimeP = P.multiply(ePrime);
    const rhs = RPrime.add(ePrimeP);

    return lhs.equals(rhs);
  } catch {
    return false;
  }
}

/** Generate a unique random 32-byte message (nonce) for a new token. */
export function generateTokenMessage(): Uint8Array {
  return randomBytes(32);
}

/** SHA-256(message || signature) as 64-char hex — used for spent-token tracking. */
export function computeTokenHash(token: SpendableToken): string {
  const data = concatBytes(hexToBytes(token.message), hexToBytes(token.signature));
  return bytesToHex(sha256(data));
}
