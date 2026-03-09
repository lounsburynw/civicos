<script lang="ts">
  let {
    attested = false,
    jurisdiction = null,
    date = null,
    selectedJurisdiction = null,
    selectedJurisdictionName = null,
    verifying = false,
    error = null,
    onredeem,
  }: {
    attested?: boolean;
    jurisdiction?: string | null;
    date?: string | null;
    selectedJurisdiction?: string | null;
    selectedJurisdictionName?: string | null;
    verifying?: boolean;
    error?: string | null;
    onredeem?: (code: string) => void;
  } = $props();

  let code = $state('');

  function handleSubmit(e: Event) {
    e.preventDefault();
    const trimmed = code.trim();
    if (!trimmed || !onredeem) return;
    onredeem(trimmed);
  }

  // Clear code input when attestation succeeds
  $effect(() => {
    if (attested) code = '';
  });
</script>

{#if attested}
  <div class="verified-badge">
    <span class="verified-badge-check">&#10003;</span>
    <div class="verified-badge-text">
      <span class="verified-badge-label">Verified resident</span>
      {#if jurisdiction || date}
        <span class="verified-badge-meta">
          {#if jurisdiction}{jurisdiction}{/if}{#if date} · {date}{/if}
        </span>
      {/if}
    </div>
  </div>
  {#if jurisdiction && jurisdiction !== selectedJurisdiction}
    <div class="attestation-mismatch">
      You're verified for {jurisdiction} but viewing {selectedJurisdictionName || selectedJurisdiction}. CivicOS AI features require verification for the selected city.
    </div>
  {/if}
{:else}
  <div class="form-group">
    <label>Verify residency</label>
    <span class="field-desc">Enter a code from a civic event to unlock CivicOS AI</span>
    <form class="attestation-form" onsubmit={handleSubmit}>
      <input
        type="text"
        placeholder="e.g. SR-2026-02-XXXX"
        bind:value={code}
        autocomplete="off"
      />
      <button type="submit" class="btn-primary btn-compact" disabled={verifying || !code.trim()}>
        {verifying ? '...' : 'Verify'}
      </button>
    </form>
    {#if error}
      <div class="attestation-error">{error}</div>
    {/if}
  </div>
{/if}

<style>
  .verified-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: var(--civic-status-success-bg-subtle);
    border-radius: 6px;
    margin-top: 8px;
  }
  .verified-badge-check {
    color: var(--civic-status-success-light);
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
  }
  .verified-badge-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .verified-badge-label {
    font-size: 13px;
    color: var(--civic-status-success-light);
    font-weight: 500;
  }
  .verified-badge-meta {
    font-size: 11px;
    color: var(--civic-text-dim);
  }

  .form-group {
    margin-bottom: 0;
  }
  label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--civic-text-secondary);
    margin-bottom: 4px;
  }
  .field-desc {
    display: block;
    font-size: 11px;
    color: var(--civic-text-dim);
    margin-bottom: 8px;
  }

  .attestation-form {
    display: flex;
    gap: 8px;
  }
  .attestation-form input {
    flex: 1;
    min-width: 0;
    font-family: var(--civic-font-family-mono);
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 6px 10px;
    background: var(--civic-surface-card-alt);
    border: 1px solid var(--civic-border-input);
    border-radius: 4px;
    color: var(--civic-text-secondary);
    font-size: 12px;
    outline: none;
  }
  .attestation-form input:focus {
    border-color: var(--civic-accent-indigo);
  }
  .attestation-form .btn-primary {
    width: auto;
    flex-shrink: 0;
  }

  .attestation-mismatch {
    font-size: 11px;
    color: var(--civic-status-warning-light);
    background: var(--civic-status-warning-bg-subtle);
    padding: 8px 10px;
    border-radius: 6px;
    margin-top: 6px;
    line-height: 1.4;
  }

  .attestation-error {
    font-size: 11px;
    color: var(--civic-status-error);
    margin-top: 4px;
  }
</style>
