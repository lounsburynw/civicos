<template>
  <div :class="['message-bubble', `message-${message.role}`]">
    <!-- Session 56: Special system message layout -->
    <div v-if="message.role === 'system'" class="system-message">
      <span class="system-icon">ℹ️</span>
      <div class="system-content" v-html="renderedContent"></div>
    </div>

    <!-- Regular user/assistant message layout -->
    <template v-else>
      <!-- Avatar -->
      <div class="message-avatar">
        <span class="avatar-circle">{{ avatarInitial }}</span>
      </div>

      <!-- Content -->
      <div class="message-main">
        <div class="message-header">
          <span class="message-role">{{ roleLabel }}</span>
          <span class="message-time">{{ formattedTime }}</span>
        </div>
        <div class="message-content" v-html="renderedContent"></div>

        <!-- Session 68: Developer mode badge (shows LLM provider info) -->
        <div v-if="developerStore.isEnabled && message.role === 'assistant' && message.provider_used" class="dev-badge">
          Dev: {{ message.provider_used }}/{{ message.model_used || 'unknown' }} | {{ message.usage?.total_tokens || 0 }} tokens
          <span v-if="message.usage?.total_tokens" class="dev-cost">
            (~${{ developerStore.estimateCost(message.usage.total_tokens, message.provider_used) }})
          </span>
        </div>

        <!-- Session 50: Use in draft button (only for assistant messages with substantial content) -->
        <button
          v-if="canUseInDraft"
          @click="handleUseInDraft"
          class="use-in-draft-btn"
          title="Add this to your draft comment"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            <path d="m15 5 4 4"/>
          </svg>
          Use this in draft
        </button>
      </div>

      <!-- Copy button for code blocks -->
      <button
        v-if="hasCodeBlocks"
        @click="copyCode"
        class="btn-copy-code"
        title="Copy code"
      >
        <span v-if="!copied">📋</span>
        <span v-else>✓</span>
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, inject, watchEffect } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import type { ChatMessage } from '../../stores/chat'
import { useWorkspaceStore } from '../../stores/workspace'
import { useDeveloperStore } from '../../stores/developer'

/**
 * MessageBubble Component (Session 28 - Rich markdown rendering, Session 50 - Use in draft)
 *
 * Displays a single chat message with:
 * - Role-specific styling (user/assistant/system)
 * - Timestamp formatting
 * - Full markdown rendering with syntax highlighting
 * - Code copy functionality
 * - "Use this in draft" button for assistant messages (Session 50)
 */

interface Props {
  message: ChatMessage
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'use-in-draft': []
}>()

const copied = ref(false)
const workspaceStore = useWorkspaceStore()
const developerStore = useDeveloperStore()

// Configure marked for syntax highlighting
onMounted(() => {
  marked.setOptions({
    highlight: (code: string, lang: string) => {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(code, { language: lang }).value
        } catch (err) {
          console.error('Highlight error:', err)
        }
      }
      try {
        return hljs.highlightAuto(code).value
      } catch (err) {
        console.error('Auto-highlight error:', err)
        return code
      }
    },
    breaks: true,
    gfm: true
  } as any)
})

const roleLabel = computed(() => {
  switch (props.message.role) {
    case 'user':
      return 'You'
    case 'assistant':
      return 'Assistant'
    case 'system':
      return 'System'
    default:
      return props.message.role
  }
})

const avatarInitial = computed(() => {
  switch (props.message.role) {
    case 'user':
      return 'U'
    case 'assistant':
      return 'A'
    case 'system':
      return 'S'
    default:
      return '?'
  }
})

const formattedTime = computed(() => {
  const date = new Date(props.message.timestamp)
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
})

// Render markdown and sanitize HTML
const renderedContent = computed(() => {
  try {
    const html = marked(props.message.content) as string
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'code', 'pre', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span'],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'class']
    })
  } catch (err) {
    console.error('Markdown rendering error:', err)
    return props.message.content
  }
})

const hasCodeBlocks = computed(() => {
  return props.message.content.includes('```') || props.message.content.includes('`')
})

// Session 50: Show "Use in draft" button for assistant messages with substantial content
const canUseInDraft = computed(() => {
  // Only show for assistant messages
  if (props.message.role !== 'assistant') return false

  // Only show if there's an active event artifact
  if (!workspaceStore.activeArtifact || workspaceStore.activeArtifact.type !== 'event') return false

  // Only show if message has substantial content (>50 chars)
  if (props.message.content.length < 50) return false

  // Session 50 fix: Exclude navigation/confirmation messages
  const content = props.message.content.toLowerCase()
  const isNavigationMessage =
    content.startsWith("i've opened") ||
    content.startsWith("i've applied") ||
    content.startsWith("i can help") ||
    content.startsWith("could you please") ||
    content.includes("browse the sidebar")

  if (isNavigationMessage) return false

  return true
})

// Session 50: Handle "Use in draft" button click
function handleUseInDraft() {
  console.log('[MessageBubble] Use in draft button clicked')
  emit('use-in-draft')
}

// Session 50: Debug button visibility
watchEffect(() => {
  if (props.message.role === 'assistant') {
    console.log('[MessageBubble] Button visibility check:', {
      messageId: props.message.id,
      canUseInDraft: canUseInDraft.value,
      hasActiveArtifact: !!workspaceStore.activeArtifact,
      artifactType: workspaceStore.activeArtifact?.type,
      contentLength: props.message.content.length
    })
  }
})

async function copyCode() {
  try {
    // Extract code blocks from markdown
    const codeBlocks = props.message.content.match(/```[\s\S]*?```/g)
    if (codeBlocks) {
      const code = codeBlocks.map(block => {
        // Remove the ``` markers and language identifier
        return block.replace(/```\w*\n?/g, '').replace(/```$/g, '')
      }).join('\n\n')
      await navigator.clipboard.writeText(code)
      copied.value = true
      setTimeout(() => {
        copied.value = false
      }, 2000)
    }
  } catch (err) {
    console.error('Copy error:', err)
  }
}
</script>

<style scoped>
.message-bubble {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 100%;
  position: relative;
  padding: 8px 16px;
  margin-left: -16px;
  margin-right: -16px;
  border-radius: 8px;
  transition: background-color 0.15s ease;
}

/* Subtle background for assistant messages only */
.message-assistant {
  background-color: rgba(0, 0, 0, 0.025);
}

.message-bubble:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

/* Avatar */
.message-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2px;
}

.avatar-circle {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: white;
  background-color: var(--text-secondary);
}

.message-assistant .avatar-circle {
  background-color: var(--primary);
}

.message-user .avatar-circle {
  background-color: var(--text-secondary);
}

.message-system .avatar-circle {
  background-color: var(--chat-border);
  color: var(--text-secondary);
}

/* Main content area */
.message-main {
  flex: 1;
  min-width: 0; /* Allow text to wrap */
  word-wrap: break-word;
  max-width: 100%;
}

/* Remove all role-specific background styling */
.message-user .message-main,
.message-assistant .message-main {
  background-color: transparent;
}

.message-system .message-main {
  background-color: transparent;
  text-align: center;
  font-size: var(--font-size-sm);
  max-width: 100%;
}

/* Header - hidden by default, visible on hover */
.message-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.message-bubble:hover .message-header {
  opacity: 1;
}

.message-system .message-header {
  justify-content: center;
  margin-bottom: 0;
  opacity: 0.6;
}

.message-role {
  font-weight: 600;
  color: var(--text-secondary);
}

.message-system .message-role {
  display: none;
}

.message-time {
  color: var(--chat-border);
  font-size: 11px;
}

.message-system .message-time {
  display: none;
}

/* Content */
.message-content {
  color: var(--text-primary);
  line-height: 1.75;
  font-size: 15px;
}

.message-system .message-content {
  color: var(--text-secondary);
  font-style: italic;
  font-size: 13px;
}

/* Markdown elements */
.message-content :deep(p) {
  margin: 0 0 12px 0;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message-content :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}

.message-content :deep(em) {
  font-style: italic;
}

.message-content :deep(code) {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-primary);
}

.message-content :deep(pre) {
  background-color: #1e1e1e;
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 12px 0;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.message-content :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: inherit;
  font-size: 14px;
  line-height: 1.6;
}

.message-content :deep(a) {
  color: var(--primary);
  text-decoration: underline;
}

.message-content :deep(a:hover) {
  color: var(--accent-purple);
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
  line-height: 1.75;
}

.message-content :deep(li) {
  margin: 4px 0;
  position: relative;
}

.message-content :deep(li::marker) {
  color: var(--text-secondary);
}

.message-content :deep(blockquote) {
  border-left: 2px solid var(--text-secondary);
  padding-left: 16px;
  margin: 12px 0;
  color: var(--text-secondary);
  font-style: italic;
}

.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3),
.message-content :deep(h4),
.message-content :deep(h5),
.message-content :deep(h6) {
  margin: 16px 0 8px 0;
  color: var(--text-primary);
  font-weight: 600;
  line-height: 1.4;
}

.message-content :deep(h1) { font-size: 24px; }
.message-content :deep(h2) { font-size: 20px; }
.message-content :deep(h3) { font-size: 17px; }

.message-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 14px;
}

.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid rgba(0, 0, 0, 0.1);
  padding: 8px 12px;
  text-align: left;
}

.message-content :deep(th) {
  background-color: rgba(0, 0, 0, 0.03);
  font-weight: 600;
}

/* Copy button - minimal, only visible on hover */
.btn-copy-code {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  transition: all 0.15s ease;
  opacity: 0;
  color: rgba(255, 255, 255, 0.8);
}

.message-bubble:hover .btn-copy-code {
  opacity: 1;
}

.btn-copy-code:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: white;
}

/* Session 50: Use in draft button */
.use-in-draft-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  margin-top: 0.75rem;
  background: transparent;
  border: 1px solid var(--primary);
  border-radius: 4px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: var(--font-family);
}

.use-in-draft-btn:hover {
  background: var(--primary);
  color: white;
}

.use-in-draft-btn svg {
  flex-shrink: 0;
}

/* Session 56: System message styling */
.system-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--base02);
  border-left: 3px solid var(--blue);
  border-radius: 4px;
  font-size: 13px;
  color: var(--base1);
  margin: 8px 0;
  width: 100%;
}

.system-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.system-content {
  flex: 1;
  min-width: 0;
}

.system-content p {
  margin: 0;
}

/* Hide background hover effect for system messages */
.message-system:hover {
  background-color: transparent;
}

/* Session 68: Developer mode badge */
.dev-badge {
  font-size: 11px;
  color: var(--base01); /* dim gray */
  font-family: var(--font-mono);
  margin-top: 8px;
  opacity: 0.7;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 4px;
  display: inline-block;
}

.dev-cost {
  color: var(--green);
  margin-left: 4px;
}
</style>
