/**
 * CivicOS Theme Store
 *
 * Svelte store for theme state with localStorage persistence.
 * Respects CIVICOS_DEFAULT_THEME env var for per-city defaults.
 */

import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { themes, defaultThemeId, getThemeById, themeToCssVars, type Theme } from './themes';

const STORAGE_KEY = 'civicos-theme';

/**
 * Get the default theme ID, checking env var first
 */
function getDefaultThemeId(): string {
  if (browser && typeof window !== 'undefined') {
    // Check for city-specific default via env var injected into window
    const envDefault = (window as any).__CIVICOS_DEFAULT_THEME__;
    if (envDefault && getThemeById(envDefault)) {
      return envDefault;
    }
  }
  return defaultThemeId;
}

/**
 * Load saved theme from localStorage, or return default
 */
function loadSavedTheme(): string {
  if (!browser) return getDefaultThemeId();

  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && getThemeById(saved)) {
      return saved;
    }
  } catch (e) {
    // localStorage may be unavailable (private browsing, etc.)
    console.warn('Could not access localStorage for theme:', e);
  }

  return getDefaultThemeId();
}

/**
 * Save theme to localStorage
 */
function saveTheme(themeId: string): void {
  if (!browser) return;

  try {
    localStorage.setItem(STORAGE_KEY, themeId);
  } catch (e) {
    console.warn('Could not save theme to localStorage:', e);
  }
}

// Create the writable store with the saved/default theme
const themeIdStore = writable<string>(loadSavedTheme());

// Derived store that provides the full theme object
export const currentTheme = derived<typeof themeIdStore, Theme>(
  themeIdStore,
  ($themeId) => getThemeById($themeId) || getThemeById(defaultThemeId)!
);

// Derived store for just the mode (light/dark)
export const themeMode = derived<typeof currentTheme, 'light' | 'dark'>(
  currentTheme,
  ($theme) => $theme.mode
);

/**
 * Set the current theme by ID
 */
export function setTheme(themeId: string): void {
  const theme = getThemeById(themeId);
  if (!theme) {
    console.warn(`Unknown theme: ${themeId}`);
    return;
  }

  themeIdStore.set(themeId);
  saveTheme(themeId);
  applyTheme(theme);
}

/**
 * Apply theme CSS variables to document
 */
export function applyTheme(theme: Theme): void {
  if (!browser) return;

  const root = document.documentElement;

  // Set CSS variables
  root.style.setProperty('--color-primary', theme.colors.primary);
  root.style.setProperty('--color-primary-hover', theme.colors.primaryHover);
  root.style.setProperty('--color-accent', theme.colors.accent);
  root.style.setProperty('--civic-bg', theme.colors.background);
  root.style.setProperty('--civic-surface', theme.colors.surface);
  root.style.setProperty('--civic-surface-hover', theme.colors.surfaceHover);
  root.style.setProperty('--civic-text', theme.colors.text);
  root.style.setProperty('--civic-text-secondary', theme.colors.textSecondary);
  root.style.setProperty('--civic-border', theme.colors.border);

  // Set data attribute for mode-based styling
  root.setAttribute('data-civic-theme', theme.id);
  root.setAttribute('data-civic-mode', theme.mode);

  // Sync with Open WebUI's dark mode class
  if (theme.mode === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

/**
 * Initialize theme on app load
 */
export function initializeTheme(): void {
  if (!browser) return;

  const themeId = get(themeIdStore);
  const theme = getThemeById(themeId);
  if (theme) {
    applyTheme(theme);
  }
}

/**
 * Cycle to next theme (useful for quick toggle)
 */
export function cycleTheme(): void {
  const currentId = get(themeIdStore);
  const currentIndex = themes.findIndex((t) => t.id === currentId);
  const nextIndex = (currentIndex + 1) % themes.length;
  setTheme(themes[nextIndex].id);
}

/**
 * Toggle between light and dark modes (picks first theme of opposite mode)
 */
export function toggleMode(): void {
  const current = get(currentTheme);
  const oppositeMode = current.mode === 'light' ? 'dark' : 'light';
  const firstOfMode = themes.find((t) => t.mode === oppositeMode);
  if (firstOfMode) {
    setTheme(firstOfMode.id);
  }
}

// Export available themes for UI
export { themes };
