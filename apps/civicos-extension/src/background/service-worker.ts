/**
 * CivicOS Extension Service Worker.
 *
 * Manages identity state and handles messages from popup, side panel,
 * options page, and NIP-07 content scripts.
 */

import { IdentityManager } from '../lib/identity.js';
import { ChromeStorageWalletStorage, ChromeStoragePasskeyStorage } from '../lib/storage.js';
import { api } from '../lib/client.js';
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

