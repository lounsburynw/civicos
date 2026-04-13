<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';

  let {
    identity,
  }: {
    identity: { isUnlocked?: boolean } | null;
  } = $props();

  let tokenCount = $state(0);
  let purchasing = $state(false);
  let pendingSessionId: string | null = $state(null);
  let pendingClaimSecret: string | null = $state(null);
  let pendingTokenCount = $state(0);
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let statusMessage: string | null = $state(null);

  const PURCHASE_STORAGE_KEY = 'civicos-pending-purchase';

  async function loadTokenCount() {
    const res = await sendMessage<number>({ type: 'GET_TOKEN_COUNT' });
    if (res.success) {
      tokenCount = res.data;
    }
  }

  async function loadPendingPurchase() {
    const stored = await chrome.storage.local.get(PURCHASE_STORAGE_KEY);
    const pending = stored[PURCHASE_STORAGE_KEY];
    if (pending?.session_id && pending?.claim_secret) {
      pendingSessionId = pending.session_id;
      pendingClaimSecret = pending.claim_secret;
      pendingTokenCount = pending.token_count || 50;
      startPolling();
    }
  }

  async function buyTokens() {
    if (purchasing || pendingSessionId) return;
    purchasing = true;
    statusMessage = null;

    const res = await sendMessage<{
      checkout_url: string;
      session_id: string;
      token_count: number;
      claim_secret: string;
    }>({ type: 'CREATE_TOKEN_CHECKOUT' });

    if (!res.success) {
      statusMessage = 'error' in res ? res.error : 'Failed to create checkout';
      purchasing = false;
      return;
    }

    const { checkout_url, session_id, token_count, claim_secret } = res.data;

    // Store pending purchase (including claim_secret) for resumption
    await chrome.storage.local.set({
      [PURCHASE_STORAGE_KEY]: { session_id, token_count, claim_secret },
    });
    pendingSessionId = session_id;
    pendingClaimSecret = claim_secret;
    pendingTokenCount = token_count;

    // Open Stripe checkout in new tab
    chrome.tabs.create({ url: checkout_url });

    // Start polling for payment completion
    startPolling();
    purchasing = false;
  }

  function startPolling() {
    if (pollTimer) return;
    statusMessage = 'Waiting for payment...';
    pollTimer = setInterval(pollCheckoutStatus, 3000);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollCheckoutStatus() {
    if (!pendingSessionId || !pendingClaimSecret) {
      stopPolling();
      return;
    }

    const res = await sendMessage<{
      status: string;
      token_count: number;
      claimed: boolean;
      voucher?: string;
    }>({
      type: 'CHECK_TOKEN_CHECKOUT',
      session_id: pendingSessionId,
      claim_secret: pendingClaimSecret,
    });

    if (!res.success) return; // Retry on next poll

    const { status, token_count, voucher } = res.data;

    if (status === 'paid') {
      stopPolling();
      statusMessage = 'Payment received, acquiring tokens...';

      // Request tokens from relay via blind signing protocol (with voucher auth)
      const tokenRes = await sendMessage<number>({
        type: 'REQUEST_TOKENS',
        count: token_count,
        voucher: voucher,
      });

      // Clear pending purchase
      await chrome.storage.local.remove(PURCHASE_STORAGE_KEY);
      pendingSessionId = null;
      pendingClaimSecret = null;

      if (tokenRes.success && tokenRes.data > 0) {
        statusMessage = `${tokenRes.data} tokens added`;
        await loadTokenCount();
        // Auto-clear success message after 4s
        setTimeout(() => { statusMessage = null; }, 4000);
      } else {
        statusMessage = 'Payment succeeded but token acquisition failed. Try refreshing.';
      }
    } else if (status === 'expired') {
      stopPolling();
      await chrome.storage.local.remove(PURCHASE_STORAGE_KEY);
      pendingSessionId = null;
      pendingClaimSecret = null;
      statusMessage = 'Checkout expired';
      setTimeout(() => { statusMessage = null; }, 4000);
    }
    // 'pending' — keep polling
  }

  // Load on mount
  loadTokenCount();
  loadPendingPurchase();

  // Listen for token count changes (e.g., after spending a token)
  chrome.storage.onChanged.addListener((changes) => {
    if (changes['civicos-tokens']) {
      loadTokenCount();
    }
  });
</script>

{#if identity?.isUnlocked}
  <div class="token-balance">
    <div class="token-row">
      <span class="token-label">Tokens</span>
      <span class="token-count">{tokenCount}</span>
      <button
        class="buy-btn"
        onclick={buyTokens}
        disabled={purchasing || !!pendingSessionId}
      >
        {#if purchasing}
          ...
        {:else if pendingSessionId}
          Pending
        {:else}
          Buy tokens
        {/if}
      </button>
    </div>
    {#if statusMessage}
      <div class="token-status">{statusMessage}</div>
    {/if}
  </div>
{/if}

<style>
  .token-balance {
    background: var(--civic-surface-elevated);
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 12px;
  }
  .token-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .token-label {
    font-size: 11px;
    color: var(--civic-text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 500;
  }
  .token-count {
    font-family: var(--civic-font-family-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--civic-text-secondary);
  }
  .buy-btn {
    margin-left: auto;
    background: var(--civic-accent-indigo);
    color: white;
    border: none;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
  }
  .buy-btn:hover { background: var(--civic-accent-indigo-hover); }
  .buy-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .token-status {
    font-size: 10px;
    color: var(--civic-text-dim);
    margin-top: 4px;
  }
</style>
