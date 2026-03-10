<script lang="ts">
  type FeedbackType = 'bug' | 'feature' | 'general';

  let {
    jurisdiction = '',
    disabled = false,
    onsubmit,
  }: {
    jurisdiction?: string;
    disabled?: boolean;
    onsubmit?: (detail: { type: FeedbackType; content: string }) => void;
  } = $props();

  let feedbackType: FeedbackType = $state('bug');
  let content = $state('');
  let submitting = $state(false);
  let success = $state(false);

  const types: { value: FeedbackType; label: string; icon: string }[] = [
    { value: 'bug', label: 'Bug', icon: '!' },
    { value: 'feature', label: 'Feature', icon: '+' },
    { value: 'general', label: 'General', icon: '?' },
  ];

  const isValid = $derived(content.trim().length >= 10 && content.trim().length <= 2000);

  function handleSubmit() {
    if (!isValid || disabled || submitting) return;
    submitting = true;
    onsubmit?.({ type: feedbackType, content: content.trim() });
    submitting = false;
    success = true;
    content = '';
    setTimeout(() => { success = false; }, 3000);
  }
</script>

<div class="feedback-form">
  <div class="feedback-types">
    {#each types as t}
      <button
        class="type-btn"
        class:active={feedbackType === t.value}
        onclick={() => feedbackType = t.value}
        {disabled}
      >
        <span class="type-icon">{t.icon}</span>
        {t.label}
      </button>
    {/each}
  </div>

  <textarea
    class="feedback-input"
    placeholder="What's on your mind? (min 10 characters)"
    bind:value={content}
    {disabled}
    maxlength={2000}
    rows={4}
  ></textarea>

  <div class="feedback-footer">
    <span class="char-count" class:near-limit={content.length > 1800}>
      {content.length}/2000
    </span>
    {#if success}
      <span class="success-msg">Sent — thank you!</span>
    {:else}
      <button
        class="submit-btn"
        onclick={handleSubmit}
        disabled={!isValid || disabled || submitting}
      >
        {submitting ? 'Sending...' : 'Send Feedback'}
      </button>
    {/if}
  </div>
</div>

<style>
  .feedback-form {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    background: var(--civic-surface-card, #1a1a2e);
    border: 1px solid var(--civic-border-default, #374151);
    border-radius: 8px;
  }

  .feedback-types {
    display: flex;
    gap: 6px;
  }

  .type-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 500;
    color: var(--civic-text-muted, #9ca3af);
    background: var(--civic-surface-elevated, #1f2937);
    border: 1px solid var(--civic-border-default, #374151);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .type-btn:hover:not(:disabled) {
    color: var(--civic-text-body, #e5e7eb);
    border-color: var(--civic-text-muted, #9ca3af);
  }

  .type-btn.active {
    color: var(--civic-accent-indigo, #6366f1);
    border-color: var(--civic-accent-indigo, #6366f1);
    background: var(--civic-accent-indigo-bg, rgba(99, 102, 241, 0.1));
  }

  .type-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .type-icon {
    font-weight: 700;
    font-size: 12px;
  }

  .feedback-input {
    width: 100%;
    padding: 8px 10px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--civic-text-body, #e5e7eb);
    background: var(--civic-surface-elevated, #1f2937);
    border: 1px solid var(--civic-border-default, #374151);
    border-radius: 6px;
    resize: vertical;
    font-family: inherit;
    box-sizing: border-box;
  }

  .feedback-input:focus {
    outline: none;
    border-color: var(--civic-accent-indigo, #6366f1);
  }

  .feedback-input::placeholder {
    color: var(--civic-text-dim, #6b7280);
  }

  .feedback-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .char-count {
    font-size: 10px;
    color: var(--civic-text-dim, #6b7280);
  }

  .char-count.near-limit {
    color: var(--civic-status-warning, #f59e0b);
  }

  .success-msg {
    font-size: 11px;
    font-weight: 500;
    color: var(--civic-status-success-light, #34d399);
  }

  .submit-btn {
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 500;
    color: white;
    background: var(--civic-accent-indigo, #6366f1);
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .submit-btn:hover:not(:disabled) {
    background: var(--civic-accent-indigo-hover, #4f46e5);
  }

  .submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
