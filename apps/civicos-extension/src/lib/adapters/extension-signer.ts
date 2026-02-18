/**
 * ExtensionSigner — implements Signer by delegating to the Chrome service worker.
 *
 * Signs events via chrome.runtime.sendMessage({ type: 'SIGN_EVENT' }),
 * which routes to IdentityManager → SigningProvider → secp256k1 schnorr.
 */

import { sendMessage } from '../messaging.js';
import type { SignedNostrEvent } from '../providers/types.js';
import type { Signer, UnsignedCivicEvent, SignedCivicEvent } from '@civicos/client';

export class ExtensionSigner implements Signer {
  async getPublicKey(): Promise<string> {
    const result = await sendMessage<string | null>({ type: 'GET_PUBLIC_KEY' });
    if (!result.success || !result.data) {
      throw new Error('Public key unavailable');
    }
    return result.data;
  }

  async signEvent(event: UnsignedCivicEvent): Promise<SignedCivicEvent> {
    const result = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event });
    if (!result.success) {
      throw new Error(`Signing failed: ${(result as { error?: string }).error || 'unknown'}`);
    }
    return {
      kind: event.kind,
      tags: event.tags,
      content: event.content,
      created_at: event.created_at,
      id: result.data.id,
      pubkey: result.data.pubkey,
      sig: result.data.sig,
    };
  }
}
