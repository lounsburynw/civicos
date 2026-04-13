/**
 * CivicOS Extension Service Worker.
 *
 * Manages identity state and handles messages from popup, side panel,
 * options page, and NIP-07 content scripts.
 */

import { IdentityManager } from '../lib/identity.js';
import { ChromeStorageWalletStorage, ChromeStoragePasskeyStorage } from '../lib/storage.js';
import { api, registry } from '../lib/client.js';
import { getTokenCount, getAvailableToken, requestTokens } from '../lib/token-wallet.js';
import type { ExtensionRequest, ExtensionResponse } from '../lib/messaging.js';
import type { NostrEvent } from '../lib/providers/types.js';

// Explicitly use Chrome storage — don't rely on auto-detection in bundled context
let identityManager = new IdentityManager({
  storage: new ChromeStorageWalletStorage(),
  passkeyStorage: new ChromeStoragePasskeyStorage(),
});

// Handle messages from extension pages and content scripts
chrome.runtime.onMessage.addListener(
  (message: ExtensionRequest, _sender, sendResponse: (response: ExtensionResponse) => void) => {
    handleMessage(message).then(sendResponse);
    return true; // Keep message channel open for async response
  }
);

async function handleMessage(message: ExtensionRequest): Promise<ExtensionResponse> {
  try {
    switch (message.type) {
      case 'GET_IDENTITY': {
        await identityManager.ensureRestored();
        const identity = await identityManager.getIdentity();
        return {
          success: true,
          data: identity
            ? { ...identity, isUnlocked: identityManager.isUnlocked() }
            : null,
        };
      }

      case 'GET_PUBLIC_KEY': {
        const pubkey = await identityManager.getPublicKey();
        return { success: true, data: pubkey };
      }

      case 'CREATE_IDENTITY': {
        const result = await identityManager.createIdentity(
          message.tier,
          message.passwordOrEmail
        );
        return { success: true, data: result };
      }

      case 'IMPORT_IDENTITY': {
        const identity = await identityManager.importIdentity(
          message.tier,
          message.passwordOrEmail,
          message.mnemonic
        );
        return { success: true, data: identity };
      }

      case 'UNLOCK': {
        const unlocked = await identityManager.unlock(message.password);
        return { success: true, data: unlocked };
      }

      case 'LOCK': {
        identityManager.lock();
        return { success: true, data: undefined };
      }

      case 'DELETE_IDENTITY': {
        await identityManager.deleteIdentity();
        return { success: true, data: undefined };
      }

      case 'SIGN_EVENT': {
        const result = await identityManager.signEvent(message.event);
        if (result.success && result.event) {
          return { success: true, data: result.event };
        }
        return { success: false, error: result.error ?? 'Signing failed' };
      }

      // NIP-07 delegated operations (from content script)
      case 'NIP07_GET_PUBLIC_KEY': {
        const pubkey = await identityManager.getPublicKey();
        if (!pubkey) {
          return { success: false, error: 'No identity configured' };
        }
        return { success: true, data: pubkey };
      }

      case 'NIP07_SIGN_EVENT': {
        if (!identityManager.isUnlocked()) {
          return { success: false, error: 'Identity is locked' };
        }
        const signResult = await identityManager.signEvent(message.event);
        if (signResult.success && signResult.event) {
          return { success: true, data: signResult.event };
        }
        return { success: false, error: signResult.error ?? 'Signing failed' };
      }

      case 'NIP07_GET_RELAYS': {
        return {
          success: true,
          data: {
            'wss://relay.civicos.dev': { read: true, write: true },
          },
        };
      }

      case 'SIGN_MESSAGE': {
        // Sign a canonical message for AI proxy authentication.
        // Creates a Nostr event (kind 24242) and signs it.
        await identityManager.ensureRestored();
        const pubkey = await identityManager.getPublicKey();
        if (!pubkey) {
          return { success: false, error: 'No identity configured' };
        }
        if (!identityManager.isUnlocked()) {
          return { success: false, error: 'Identity is locked' };
        }

        const createdAt = Math.floor(Date.now() / 1000);
        const event: NostrEvent = {
          kind: 24242,
          created_at: createdAt,
          tags: [['action', 'ai_draft']],
          content: `civicos:ai:v1:${pubkey}:${createdAt}`,
        };

        const signResult = await identityManager.signEvent(event);
        if (!signResult.success || !signResult.event) {
          return { success: false, error: signResult.error ?? 'Signing failed' };
        }

        return {
          success: true,
          data: {
            public_key: signResult.event.pubkey,
            signature: signResult.event.sig,
            created_at: createdAt,
          },
        };
      }

      case 'REDEEM_ATTESTATION': {
        // Sign a kind-24242 auth event for attestation code redemption,
        // then call the relay to redeem.
        const attestPubkey = await identityManager.getPublicKey();
        if (!attestPubkey) {
          return { success: false, error: 'No identity configured' };
        }
        if (!identityManager.isUnlocked()) {
          return { success: false, error: 'Identity is locked' };
        }

        const attestCode = message.code;
        const attestCreatedAt = Math.floor(Date.now() / 1000);
        const attestEvent: NostrEvent = {
          kind: 24242,
          created_at: attestCreatedAt,
          tags: [['action', 'attest'], ['code', attestCode]],
          content: `civicos:attest:v1:${attestPubkey}:${attestCode}:${attestCreatedAt}`,
        };

        const attestSignResult = await identityManager.signEvent(attestEvent);
        if (!attestSignResult.success || !attestSignResult.event) {
          return { success: false, error: attestSignResult.error ?? 'Signing failed' };
        }

        const redeemResult = await api.redeemAttestationCode(
          attestCode,
          attestSignResult.event.pubkey,
          attestSignResult.event.sig,
          attestCreatedAt
        );

        if (redeemResult.success && redeemResult.attestation_event) {
          // Store attestation event locally
          await chrome.storage.local.set({
            civicos_attestation: redeemResult.attestation_event,
          });
          return { success: true, data: redeemResult.attestation_event };
        }

        return { success: false, error: redeemResult.error || 'Attestation failed' };
      }

      case 'GET_TOKEN_COUNT': {
        const count = await getTokenCount();
        return { success: true, data: count };
      }

      case 'REQUEST_TOKENS': {
        // Discover issuer config from relay, then acquire tokens
        const relayUrl = await registry.getRelayUrl();
        const infoRes = await fetch(`${relayUrl}/coordination/tokens/info`);
        if (!infoRes.ok) {
          return { success: false, error: 'Failed to reach token issuer' };
        }
        const info = await infoRes.json();
        if (!info.enabled || !info.issuer_pubkey) {
          return { success: false, error: 'Token issuance not enabled on this relay' };
        }
        const acquired = await requestTokens(
          { issuerUrl: relayUrl, issuerPubkey: info.issuer_pubkey, voucher: message.voucher },
          message.count,
        );
        return { success: true, data: acquired };
      }

      case 'SPEND_TOKEN': {
        const token = await getAvailableToken();
        return { success: true, data: token };
      }

      case 'CREATE_TOKEN_CHECKOUT': {
        const apiUrl = await registry.getRelayUrl();
        const checkoutRes = await fetch(`${apiUrl}/api/tokens/checkout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ count: message.count }),
        });
        if (!checkoutRes.ok) {
          const detail = await checkoutRes.text();
          return { success: false, error: `Checkout failed: ${detail}` };
        }
        const checkoutData = await checkoutRes.json();
        return { success: true, data: checkoutData };
      }

      case 'CHECK_TOKEN_CHECKOUT': {
        const statusApiUrl = await registry.getRelayUrl();
        const statusRes = await fetch(
          `${statusApiUrl}/api/tokens/status/${message.session_id}`,
          { headers: { 'X-Claim-Secret': message.claim_secret } },
        );
        if (!statusRes.ok) {
          const detail = await statusRes.text();
          return { success: false, error: `Status check failed: ${detail}` };
        }
        const statusData = await statusRes.json();
        return { success: true, data: statusData };
      }

      default:
        return { success: false, error: `Unknown message type: ${(message as { type: string }).type}` };
    }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    };
  }
}

// Open side panel when extension icon is clicked
chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id) {
    await chrome.sidePanel.open({ tabId: tab.id });
  }
});

