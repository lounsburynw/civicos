/**
 * Token wallet — persistent storage for blinded tokens in chrome.storage.local.
 *
 * Follows the ChromeStorageWalletStorage pattern from storage.ts.
 * Tokens are stored as an array of SpendableToken dicts.
 */

import { bytesToHex, hexToBytes } from '@noble/hashes/utils';
import { blind, unblind, generateTokenMessage } from './blind.js';
import type { SpendableToken, BlindingContext } from './blind.js';

const TOKEN_STORAGE_KEY = 'civicos-tokens';

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

/** Read all stored tokens. */
export async function getTokens(): Promise<SpendableToken[]> {
  const result = await chrome.storage.local.get(TOKEN_STORAGE_KEY);
  return result[TOKEN_STORAGE_KEY] ?? [];
}

/** Persist the token array. */
async function saveTokens(tokens: SpendableToken[]): Promise<void> {
  await chrome.storage.local.set({ [TOKEN_STORAGE_KEY]: tokens });
}

/** Store newly acquired tokens (appends to existing). */
export async function storeTokens(newTokens: SpendableToken[]): Promise<void> {
  const existing = await getTokens();
  await saveTokens([...existing, ...newTokens]);
}

/** Pop one token for spending. Returns null if wallet is empty. */
export async function getAvailableToken(): Promise<SpendableToken | null> {
  const tokens = await getTokens();
  if (tokens.length === 0) return null;
  const token = tokens[0];
  await saveTokens(tokens.slice(1));
  return token;
}

/** How many tokens are available. */
export async function getTokenCount(): Promise<number> {
  const tokens = await getTokens();
  return tokens.length;
}

/** Remove all tokens (e.g., on identity reset). */
export async function clearTokens(): Promise<void> {
  await chrome.storage.local.remove(TOKEN_STORAGE_KEY);
}

// ---------------------------------------------------------------------------
// Acquisition — 2-step blind signing protocol with issuer
// ---------------------------------------------------------------------------

export interface TokenIssuerConfig {
  /** Base URL of the token issuer service, e.g. "https://relay.civicos.dev" */
  issuerUrl: string;
  /** Issuer's compressed public key, 66-char hex */
  issuerPubkey: string;
}

interface NonceSessionResponse {
  session_id: string;
  nonce_point: string; // 66-char hex, compressed R
}

interface SignResponse {
  blind_signature: string; // 64-char hex, 32 bytes
}

/**
 * Acquire tokens from the issuer via the blind signing protocol.
 *
 * For each token:
 *   1. Request a nonce session from the issuer
 *   2. Blind a random message locally
 *   3. Send the blinded challenge to the issuer
 *   4. Unblind the response into a SpendableToken
 *   5. Store in chrome.storage.local
 *
 * @returns Number of tokens successfully acquired.
 */
export async function requestTokens(
  config: TokenIssuerConfig,
  count: number,
): Promise<number> {
  const issuerPubkeyBytes = hexToBytes(config.issuerPubkey);
  const acquired: SpendableToken[] = [];

  for (let i = 0; i < count; i++) {
    try {
      // Step 1: Request nonce session
      const sessionRes = await fetch(`${config.issuerUrl}/coordination/tokens/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 1 }),
      });
      if (!sessionRes.ok) break;
      const session: NonceSessionResponse = await sessionRes.json();

      // Step 2: Blind locally
      const message = generateTokenMessage();
      const noncePoint = hexToBytes(session.nonce_point);
      const { challenge, ctx } = blind(message, issuerPubkeyBytes, noncePoint);

      // Step 3: Send blinded challenge to issuer
      const signRes = await fetch(`${config.issuerUrl}/coordination/tokens/sign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: session.session_id,
          blinded_challenge: bytesToHex(challenge),
        }),
      });
      if (!signRes.ok) continue;
      const signData: SignResponse = await signRes.json();

      // Step 4: Unblind into spendable token
      const blindSig = hexToBytes(signData.blind_signature);
      const token = unblind(blindSig, ctx, issuerPubkeyBytes);
      acquired.push(token);
    } catch {
      // Skip failed token, continue with rest
      continue;
    }
  }

  if (acquired.length > 0) {
    await storeTokens(acquired);
  }
  return acquired.length;
}
