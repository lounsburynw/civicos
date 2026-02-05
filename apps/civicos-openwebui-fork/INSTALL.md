# Installation Guide

Quick guide to getting the CivicOS Open WebUI fork running.

## Prerequisites

- Node.js 20+
- Docker (optional, for production)
- Git

## Step 1: Clone Open WebUI

```bash
# Clone the official repo
git clone https://github.com/open-webui/open-webui.git civicos-openwebui
cd civicos-openwebui

# Create a new branch for our customizations
git checkout -b civicos-fork
```

## Step 2: Copy Civic Files

```bash
# From the civicos project root
cp -r apps/civicos-openwebui-fork/src/* ../civicos-openwebui/src/
```

Or manually copy:

```
civicos-openwebui-fork/src/
├── lib/
│   ├── apis/civic.ts           → src/lib/apis/civic.ts
│   └── components/civic/       → src/lib/components/civic/
└── routes/(app)/
    ├── +page.svelte            → src/routes/(app)/+page.svelte (REPLACE)
    └── decisions/[id]/         → src/routes/(app)/decisions/[id]/
```

## Step 3: Install Dependencies

```bash
cd civicos-openwebui
npm install
```

## Step 4: Environment Setup

Create `.env` in the root:

```env
# CivicOS MCP endpoint
VITE_CIVICOS_MCP_URL=https://san-rafael.civicosproject.org/mcp

# Open WebUI settings (adjust as needed)
WEBUI_SECRET_KEY=your-secret-key-here
```

## Step 5: Run Development Server

```bash
npm run dev
```

Open http://localhost:5173

## Step 6: Verify

1. Homepage should show city pulse (not redirect to /chat)
2. Decision cards should load from MCP
3. Chat input at bottom should work
4. Clicking a decision should go to detail page

## Troubleshooting

### "Failed to load civic data"

Check that the MCP URL is accessible:
```bash
curl https://san-rafael.civicosproject.org/health
```

### Components not found

Make sure files are in the correct locations:
```bash
ls src/lib/components/civic/
# Should show: CityPulseHeader.svelte, DecisionCard.svelte, etc.
```

### Styles look wrong

Open WebUI uses CSS variables. If colors look off, check that you're inheriting:
- `--surface-color`
- `--text-primary`
- `--border-color`
- `--primary-color`

## Production Build

```bash
npm run build
npm run preview  # Test production build locally
```

## Docker Deployment

```dockerfile
# Use the standard Open WebUI Dockerfile
# Just ensure your src/ changes are included before build
```

## Theme System

The fork includes a theme switcher with 6 civic-branded themes.

### Adding ThemeSwitcher to the UI

In Open WebUI's settings panel or header, add:

```svelte
<script>
  import { ThemeSwitcher } from '$lib/components/civic';
</script>

<ThemeSwitcher />
```

### Setting a City Default Theme

Inject the default via environment variable. In your layout or app entry:

```svelte
<script>
  import { onMount } from 'svelte';
  import { PUBLIC_CIVICOS_DEFAULT_THEME } from '$env/static/public';

  onMount(() => {
    if (PUBLIC_CIVICOS_DEFAULT_THEME) {
      window.__CIVICOS_DEFAULT_THEME__ = PUBLIC_CIVICOS_DEFAULT_THEME;
    }
  });
</script>
```

Then set in `.env`:
```env
PUBLIC_CIVICOS_DEFAULT_THEME=community-garden
```

### Available Themes

| ID | Name | Mode | Description |
|----|------|------|-------------|
| `city-hall` | City Hall | Light | Professional blue (default) |
| `community-garden` | Community Garden | Light | Warm greens |
| `public-comment` | Public Comment | Light | High contrast purple |
| `terra-cotta` | Terra Cotta | Light | California mission style |
| `solarized-light` | Solarized Light | Light | Classic low-contrast |
| `night-session` | Night Session | Dark | Late council meetings |
| `midnight-council` | Midnight Council | Dark | OLED-friendly pure dark |
| `solarized-dark` | Solarized Dark | Dark | Classic low-contrast |

### Programmatic Theme Control

```typescript
import { setTheme, toggleMode, cycleTheme, currentTheme } from '$lib/components/civic';

// Set specific theme
setTheme('night-session');

// Toggle light/dark
toggleMode();

// Cycle through all themes
cycleTheme();

// Subscribe to current theme
$: console.log($currentTheme.name);
```

### Adding Custom Themes

Edit `src/lib/components/civic/themes.ts`:

```typescript
export const themes: Theme[] = [
  // ... existing themes
  {
    id: 'my-city',
    name: 'My City',
    description: 'Custom theme for My City',
    mode: 'light',
    colors: {
      primary: '#your-color',
      // ... all color properties
    },
  },
];
```

## Next Steps

1. **Customize neighborhoods** - Edit `CityPulseHeader.svelte` neighborhoods array
2. **Add more pages** - Create routes for `/meetings/[id]`, `/issues`, etc.
3. **Wire up voice casting** - Connect VoiceWidget to your relay
4. **Add authentication** - Use Open WebUI's auth for verified identity
5. **Add ThemeSwitcher** - Place in settings panel or header for user customization
