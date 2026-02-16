/**
 * Claude.ai Bridge Content Script.
 *
 * Runs on claude.ai pages in the ISOLATED world. Checks for pending civic
 * context stored by the side panel, waits for the chat editor to appear,
 * and attempts to inject text via synthetic paste event.
 *
 * Falls back to showing a banner prompting the user to paste manually.
 */

const PENDING_KEY = 'civicos_claude_pending_context';

const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
const pasteShortcut = isMac ? '⌘V' : 'Ctrl+V';

async function getPendingContext(): Promise<string | null> {
  try {
    const result = await chrome.storage.session.get(PENDING_KEY);
    return result[PENDING_KEY] ?? null;
  } catch {
    return null;
  }
}

async function clearPendingContext(): Promise<void> {
  try {
    await chrome.storage.session.remove(PENDING_KEY);
  } catch { /* ignore */ }
}

function showBanner(status: 'pending' | 'success'): void {
  document.getElementById('civicos-bridge-banner')?.remove();

  const banner = document.createElement('div');
  banner.id = 'civicos-bridge-banner';
  Object.assign(banner.style, {
    position: 'fixed',
    top: '16px',
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: '999999',
    background: status === 'success' ? '#065f46' : '#1e293b',
    border: status === 'success' ? '1px solid #10b981' : '1px solid #3b82f6',
    borderRadius: '10px',
    padding: '12px 20px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    textAlign: 'center',
    maxWidth: '480px',
    animation: 'civicos-slide-in 0.3s ease',
  });

  if (status === 'pending') {
    banner.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;gap:8px;">
        <div>
          <div style="font-size:13px;font-weight:600;color:#93c5fd;margin-bottom:4px;">
            CivicOS context is in your clipboard
          </div>
          <div style="font-size:12px;color:#cbd5e1;">
            Press <kbd style="background:#334155;padding:1px 6px;border-radius:3px;font-size:11px;border:1px solid #475569;">${pasteShortcut}</kbd> to paste, then send
          </div>
        </div>
        <button id="civicos-bridge-dismiss" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;padding:0 4px;line-height:1;">&times;</button>
      </div>
    `;
  } else {
    banner.innerHTML = `
      <div style="font-size:13px;font-weight:600;color:#6ee7b7;">
        CivicOS context loaded — ready to send
      </div>
    `;
  }

  if (!document.getElementById('civicos-bridge-style')) {
    const style = document.createElement('style');
    style.id = 'civicos-bridge-style';
    style.textContent = `
      @keyframes civicos-slide-in {
        from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }
  document.body.appendChild(banner);

  // Dismiss button handler
  document.getElementById('civicos-bridge-dismiss')?.addEventListener('click', () => {
    dismissBanner(0);
  });
}

function dismissBanner(delay = 3000): void {
  setTimeout(() => {
    const banner = document.getElementById('civicos-bridge-banner');
    if (banner) {
      banner.style.transition = 'opacity 0.3s ease';
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 300);
    }
  }, delay);
}

function findEditor(): HTMLElement | null {
  const selectors = [
    'div.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"].ProseMirror',
    'div[contenteditable="true"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el) return el;
  }
  return null;
}

/**
 * Try multiple strategies to inject text into the editor.
 * Returns true only if text actually appears in the editor.
 */
function injectText(editor: HTMLElement, text: string): boolean {
  const target = editor.matches('[contenteditable="true"]')
    ? editor
    : (editor.closest('[contenteditable="true"]') as HTMLElement);
  if (!target) return false;

  target.focus();

  // Strategy 1: Synthetic paste event (best for ProseMirror)
  try {
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    const pasteEvent = new ClipboardEvent('paste', {
      bubbles: true,
      cancelable: true,
      clipboardData: dt,
    });
    target.dispatchEvent(pasteEvent);
    // Verify text actually appeared (wait a tick for ProseMirror to process)
    if (target.textContent && target.textContent.includes(text.substring(0, 40))) {
      return true;
    }
  } catch { /* continue to next strategy */ }

  // Strategy 2: execCommand insertText (deprecated but widely supported)
  try {
    const success = document.execCommand('insertText', false, text);
    if (success && target.textContent && target.textContent.includes(text.substring(0, 40))) {
      return true;
    }
  } catch { /* continue */ }

  // Strategy 3: Direct DOM manipulation + input event
  try {
    const p = target.querySelector('p');
    if (p) {
      p.textContent = text;
    } else {
      target.textContent = text;
    }
    target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertFromPaste' }));
    if (target.textContent && target.textContent.includes(text.substring(0, 40))) {
      return true;
    }
  } catch { /* fall through */ }

  return false;
}

async function run(): Promise<void> {
  const context = await getPendingContext();
  if (!context) return;

  // Show "paste" banner immediately as fallback UX
  showBanner('pending');

  // Wait for the editor to appear, then try auto-inject
  let attempts = 0;
  const maxAttempts = 50; // 10 seconds
  const interval = setInterval(() => {
    attempts++;
    const editor = findEditor();
    if (editor) {
      clearInterval(interval);
      // Focus editor so user can paste immediately if auto-inject fails
      editor.focus();
      // Give the editor time to fully initialize
      setTimeout(() => {
        const success = injectText(editor, context);
        clearPendingContext();
        if (success) {
          showBanner('success');
          dismissBanner(2500);
        }
        // If auto-inject failed, the pending banner stays visible with paste instructions
        // User can dismiss it manually or it fades after 12s
        if (!success) {
          dismissBanner(12000);
        }
      }, 800);
    } else if (attempts >= maxAttempts) {
      clearInterval(interval);
      // Editor never appeared — keep banner a bit longer
      dismissBanner(10000);
      clearPendingContext();
    }
  }, 200);
}

run();
