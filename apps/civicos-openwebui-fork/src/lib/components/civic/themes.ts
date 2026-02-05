/**
 * CivicOS Theme Definitions
 *
 * Each theme defines CSS custom properties that override Open WebUI's defaults.
 * Themes are designed for civic contexts - accessible, professional, varied.
 */

export interface Theme {
  id: string;
  name: string;
  description: string;
  mode: 'light' | 'dark';
  colors: {
    primary: string;
    primaryHover: string;
    accent: string;
    background: string;
    surface: string;
    surfaceHover: string;
    text: string;
    textSecondary: string;
    border: string;
  };
}

export const themes: Theme[] = [
  {
    id: 'city-hall',
    name: 'City Hall',
    description: 'Professional blue, inspired by government buildings',
    mode: 'light',
    colors: {
      primary: '#1e40af',
      primaryHover: '#1e3a8a',
      accent: '#3b82f6',
      background: '#f8fafc',
      surface: '#ffffff',
      surfaceHover: '#f1f5f9',
      text: '#0f172a',
      textSecondary: '#475569',
      border: '#e2e8f0',
    },
  },
  {
    id: 'community-garden',
    name: 'Community Garden',
    description: 'Warm greens for neighborhood initiatives',
    mode: 'light',
    colors: {
      primary: '#166534',
      primaryHover: '#14532d',
      accent: '#22c55e',
      background: '#f7fdf9',
      surface: '#ffffff',
      surfaceHover: '#f0fdf4',
      text: '#14532d',
      textSecondary: '#4d7c5f',
      border: '#d1e7dd',
    },
  },
  {
    id: 'night-session',
    name: 'Night Session',
    description: 'Dark mode for late council meetings',
    mode: 'dark',
    colors: {
      primary: '#60a5fa',
      primaryHover: '#93c5fd',
      accent: '#3b82f6',
      background: '#0f172a',
      surface: '#1e293b',
      surfaceHover: '#334155',
      text: '#f1f5f9',
      textSecondary: '#94a3b8',
      border: '#334155',
    },
  },
  {
    id: 'public-comment',
    name: 'Public Comment',
    description: 'High contrast for accessibility',
    mode: 'light',
    colors: {
      primary: '#7c3aed',
      primaryHover: '#6d28d9',
      accent: '#a78bfa',
      background: '#ffffff',
      surface: '#ffffff',
      surfaceHover: '#f5f3ff',
      text: '#1e1b4b',
      textSecondary: '#4c4878',
      border: '#c4b5fd',
    },
  },
  {
    id: 'terra-cotta',
    name: 'Terra Cotta',
    description: 'Warm earth tones, California mission style',
    mode: 'light',
    colors: {
      primary: '#c2410c',
      primaryHover: '#9a3412',
      accent: '#fb923c',
      background: '#fffbf7',
      surface: '#ffffff',
      surfaceHover: '#fff7ed',
      text: '#431407',
      textSecondary: '#78543a',
      border: '#fed7aa',
    },
  },
  {
    id: 'midnight-council',
    name: 'Midnight Council',
    description: 'OLED-friendly pure dark',
    mode: 'dark',
    colors: {
      primary: '#f472b6',
      primaryHover: '#f9a8d4',
      accent: '#ec4899',
      background: '#000000',
      surface: '#0a0a0a',
      surfaceHover: '#171717',
      text: '#fafafa',
      textSecondary: '#a3a3a3',
      border: '#262626',
    },
  },
  {
    id: 'solarized-light',
    name: 'Solarized Light',
    description: 'Classic low-contrast light theme',
    mode: 'light',
    colors: {
      primary: '#268bd2',
      primaryHover: '#2aa198',
      accent: '#859900',
      background: '#fdf6e3',
      surface: '#eee8d5',
      surfaceHover: '#eee8d5',
      text: '#657b83',
      textSecondary: '#93a1a1',
      border: '#eee8d5',
    },
  },
  {
    id: 'solarized-dark',
    name: 'Solarized Dark',
    description: 'Classic low-contrast dark theme',
    mode: 'dark',
    colors: {
      primary: '#268bd2',
      primaryHover: '#2aa198',
      accent: '#859900',
      background: '#002b36',
      surface: '#073642',
      surfaceHover: '#073642',
      text: '#839496',
      textSecondary: '#586e75',
      border: '#073642',
    },
  },
];

export const defaultThemeId = 'city-hall';

export function getThemeById(id: string): Theme | undefined {
  return themes.find((t) => t.id === id);
}

export function getThemesByMode(mode: 'light' | 'dark'): Theme[] {
  return themes.filter((t) => t.mode === mode);
}

/**
 * Generate CSS custom properties string from theme
 */
export function themeToCssVars(theme: Theme): string {
  return `
    --color-primary: ${theme.colors.primary};
    --color-primary-hover: ${theme.colors.primaryHover};
    --color-accent: ${theme.colors.accent};
    --civic-bg: ${theme.colors.background};
    --civic-surface: ${theme.colors.surface};
    --civic-surface-hover: ${theme.colors.surfaceHover};
    --civic-text: ${theme.colors.text};
    --civic-text-secondary: ${theme.colors.textSecondary};
    --civic-border: ${theme.colors.border};
  `.trim();
}
