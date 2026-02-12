/**
 * NIP-07 Content Script.
 *
 * Injects `window.nostr` into web pages for Nostr client compatibility.
 * Delegates all cryptographic operations to the service worker via
 * chrome.runtime.sendMessage.
 *
 * Runs in "MAIN" world so it can set properties on the page's window object.
 * Defers to existing NIP-07 providers (nos2x, Alby) if already present.
 */

// Check if another NIP-07 provider already exists (nos2x, Alby, etc.)
if (typeof window !== 'undefined' && !(window as any).nostr) {
  const nostrProvider = {
    async getPublicKey(): Promise<string> {
      const response = await chrome.runtime.sendMessage({
        type: 'NIP07_GET_PUBLIC_KEY',
      });

      if (!response.success) {
        throw new Error(response.error ?? 'Failed to get public key');
      }

      return response.data;
    },

    async signEvent(event: {
      created_at: number;
      kind: number;
      tags: string[][];
      content: string;
    }): Promise<{
      id: string;
      pubkey: string;
      created_at: number;
      kind: number;
      tags: string[][];
      content: string;
      sig: string;
    }> {
      const response = await chrome.runtime.sendMessage({
        type: 'NIP07_SIGN_EVENT',
        event,
      });

      if (!response.success) {
        throw new Error(response.error ?? 'Failed to sign event');
      }

      return response.data;
    },

    async getRelays(): Promise<
      Record<string, { read: boolean; write: boolean }>
    > {
      const response = await chrome.runtime.sendMessage({
        type: 'NIP07_GET_RELAYS',
      });

      if (!response.success) {
        return {};
      }

      return response.data;
    },

    // NIP-07 optional methods (not yet implemented)
    nip04: undefined,
    nip44: undefined,
  };

  // Inject as non-configurable, non-writable to prevent override
  Object.defineProperty(window, 'nostr', {
    value: nostrProvider,
    writable: false,
    configurable: false,
    enumerable: true,
  });
}
