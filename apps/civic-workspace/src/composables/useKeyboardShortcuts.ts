import { onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'

/**
 * Composable for workspace keyboard shortcuts
 *
 * Shortcuts:
 * - Cmd/Ctrl + K: Toggle workspace visibility (chat ↔ workspace)
 * - Escape: Hide workspace and return to fullscreen chat
 * - Cmd/Ctrl + N: New complaint / Report issue
 * - Cmd/Ctrl + B: Toggle left pane (event list)
 * - Cmd/Ctrl + Shift + B: Toggle right pane (event detail)
 * - Cmd/Ctrl + W: Close active tab
 * - Cmd/Ctrl + [1-9]: Switch to tab N
 * - Cmd/Ctrl + [: Previous tab
 * - Cmd/Ctrl + ]: Next tab
 * - Cmd/Ctrl + Shift + W: Close all tabs
 */
export function useKeyboardShortcuts(
  onNewComplaint?: () => void,
  splitPaneRef?: Ref<{ toggleLeftPane: () => void; toggleRightPane: () => void } | null>
) {
  const workspace = useWorkspaceStore()

  function handleKeyDown(event: KeyboardEvent) {
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
    const cmdOrCtrl = isMac ? event.metaKey : event.ctrlKey

    // Ignore if user is typing in an input/textarea (except for Escape)
    const target = event.target as HTMLElement
    const isTyping = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

    // Escape: Hide workspace and return to fullscreen chat (works even when typing)
    if (event.key === 'Escape') {
      console.log('[Keyboard] Escape pressed', {
        viewMode: workspace.viewMode,
        workspaceVisible: workspace.workspaceVisible,
        shouldToggle: workspace.viewMode === 'chat-first' && workspace.workspaceVisible
      })

      if (workspace.viewMode === 'chat-first' && workspace.workspaceVisible) {
        event.preventDefault()
        console.log('[Keyboard] Toggling workspace visibility')
        workspace.toggleWorkspaceVisibility()
        return
      }
    }

    // Don't process other shortcuts while typing
    if (isTyping) {
      return
    }

    // Cmd/Ctrl + K: Toggle workspace visibility (chat ↔ workspace)
    if (cmdOrCtrl && event.key === 'k') {
      event.preventDefault()
      if (workspace.viewMode === 'chat-first') {
        workspace.toggleWorkspaceVisibility()
      }
      return
    }

    // Cmd/Ctrl + N: New complaint
    if (cmdOrCtrl && event.key === 'n') {
      event.preventDefault()
      if (onNewComplaint) {
        onNewComplaint()
      }
      return
    }

    // Cmd/Ctrl + B: Toggle left pane (event list)
    if (cmdOrCtrl && event.key === 'b' && !event.shiftKey) {
      event.preventDefault()
      if (splitPaneRef?.value) {
        splitPaneRef.value.toggleLeftPane()
      }
      return
    }

    // Cmd/Ctrl + Shift + B: Toggle right pane (event detail)
    if (cmdOrCtrl && event.key === 'B' && event.shiftKey) {
      event.preventDefault()
      if (splitPaneRef?.value) {
        splitPaneRef.value.toggleRightPane()
      }
      return
    }

    // Cmd/Ctrl + W: Close active tab
    if (cmdOrCtrl && event.key === 'w' && !event.shiftKey) {
      event.preventDefault()
      workspace.closeActiveArtifact()
      return
    }

    // Cmd/Ctrl + Shift + W: Close all tabs
    if (cmdOrCtrl && event.key === 'w' && event.shiftKey) {
      event.preventDefault()
      workspace.closeAllArtifacts()
      return
    }

    // Cmd/Ctrl + [1-9]: Switch to tab N
    if (cmdOrCtrl && event.key >= '1' && event.key <= '9') {
      event.preventDefault()
      const tabNumber = parseInt(event.key, 10)
      workspace.switchToTab(tabNumber)
      return
    }

    // Cmd/Ctrl + [: Previous tab
    if (cmdOrCtrl && event.key === '[') {
      event.preventDefault()
      workspace.previousTab()
      return
    }

    // Cmd/Ctrl + ]: Next tab
    if (cmdOrCtrl && event.key === ']') {
      event.preventDefault()
      workspace.nextTab()
      return
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown)
  })

  return {
    // No need to expose anything - shortcuts work globally
  }
}
