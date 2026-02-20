import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'path';

export default defineConfig({
  root: 'tests/visual',
  plugins: [svelte()],
  resolve: {
    alias: {
      '@civicos/components': resolve(__dirname, '../../packages/civicos-components'),
    },
  },
  server: {
    port: 5199,
    strictPort: true,
  },
});
