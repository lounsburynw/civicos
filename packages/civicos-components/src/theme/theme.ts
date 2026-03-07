/**
 * CivicOS Theme Manager
 *
 * Applies, persists, and loads theme preferences.
 * Works in both browser extension (chrome.storage) and web (localStorage) contexts.
 */

export type ThemeId = 'dark' | 'light' | 'solarized-light';

export interface ThemeOption {
  id: ThemeId;
  label: string;
}

export const THEMES: ThemeOption[] = [
  { id: 'dark', label: 'Dark' },
  { id: 'light', label: 'Light' },
  { id: 'solarized-light', label: 'Solarized Light' },
];

const STORAGE_KEY = 'civicos_theme';
const DEFAULT_THEME: ThemeId = 'dark';

/** Apply a theme to the document by setting data-theme attribute */
export function applyTheme(themeId: ThemeId): void {
  document.documentElement.setAttribute('data-theme', themeId);
}

/** Persist theme choice (chrome.storage if available, else localStorage) */
export async function saveTheme(themeId: ThemeId): Promise<void> {
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    await chrome.storage.local.set({ [STORAGE_KEY]: themeId });
  } else if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, themeId);
  }
}

/** Load saved theme preference */
export async function loadSavedTheme(): Promise<ThemeId> {
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    return (result[STORAGE_KEY] as ThemeId) || DEFAULT_THEME;
  }
  if (typeof localStorage !== 'undefined') {
    return (localStorage.getItem(STORAGE_KEY) as ThemeId) || DEFAULT_THEME;
  }
  return DEFAULT_THEME;
}

/** Initialize theme on page load and watch for cross-page changes */
export async function initTheme(): Promise<ThemeId> {
  const themeId = await loadSavedTheme();
  applyTheme(themeId);

  // Listen for theme changes from other extension pages (e.g. Settings → Side Panel)
  if (typeof chrome !== 'undefined' && chrome.storage?.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && changes[STORAGE_KEY]?.newValue) {
        applyTheme(changes[STORAGE_KEY].newValue as ThemeId);
      }
    });
  }

  return themeId;
}

/** Set theme: apply + persist in one call */
export async function setTheme(themeId: ThemeId): Promise<void> {
  applyTheme(themeId);
  await saveTheme(themeId);
}
