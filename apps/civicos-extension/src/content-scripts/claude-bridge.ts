/**
 * Claude.ai Bridge Content Script.
 *
 * Runs on claude.ai pages in the ISOLATED world. Checks for pending civic
 * context stored by the side panel. Shows a visible banner on the page and
 * attempts to auto-inject text into the chat editor.
 */

const PENDING_KEY = 'civicos_claude_pending_context';

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

function showBanner(status: 'pending' | 'success'): HTMLElement {
  // Remove existing banner if any
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
      <div style="font-size:13px;font-weight:600;color:#93c5fd;margin-bottom:4px;">
        CivicOS context is in your clipboard
      </div>
      <div style="font-size:12px;color:#cbd5e1;">
        Press <kbd style="background:#334155;padding:1px 6px;border-radius:3px;font-size:11px;border:1px solid #475569;">⌘V</kbd> to paste into the chat
      </div>
    `;
  } else {
    banner.innerHTML = `
      <div style="font-size:13px;font-weight:600;color:#6ee7b7;">
        CivicOS context loaded — ready to send
      </div>
    `;
  }

  // Add slide-in animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes civicos-slide-in {
      from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
      to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(banner);
  return banner;
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
  // Try multiple selectors — Claude.ai's DOM structure can vary
  const selectors = [
    'div.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"].ProseMirror',
    '[contenteditable="true"] p',
    'div[contenteditable="true"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el) return el;
  }
  return null;
}

function injectText(editor: HTMLElement, text: string): boolean {
  editor.focus();

  // For ProseMirror: if we found a <p> inside, use its parent
  const target = editor.closest('[contenteditable="true"]') as HTMLElement ?? editor;
  target.focus();

  // execCommand('insertText') is the most reliable way to populate
  // framework-managed contenteditable elements (triggers all internal events)
  const success = document.execCommand('insertText', false, text);
  if (success) return true;

  // Fallback: set textContent and dispatch input event
  target.textContent = text;
  target.dispatchEvent(new Event('input', { bubbles: true }));
  target.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}

async function run(): Promise<void> {
  const context = await getPendingContext();
  if (!context) return;

  // Show banner immediately so user knows what's happening
  showBanner('pending');

  // Try to auto-inject into the editor
  let attempts = 0;
  const maxAttempts = 50; // 10 seconds
  const interval = setInterval(() => {
    attempts++;
    const editor = findEditor();
    if (editor) {
      clearInterval(interval);
      setTimeout(() => {
        const injected = injectText(editor, context);
        if (injected) {
          showBanner('success');
          dismissBanner(2500);
        } else {
          dismissBanner(8000);
        }
        clearPendingContext();
      }, 500);
    } else if (attempts >= maxAttempts) {
      clearInterval(interval);
      // Auto-inject failed — banner stays visible so user knows to paste
      dismissBanner(8000);
      clearPendingContext();
    }
  }, 200);
}

run();
