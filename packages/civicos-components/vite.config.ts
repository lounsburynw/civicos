import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [
    svelte({
      compilerOptions: {
        customElement: true,
      },
    }),
  ],
  build: {
    lib: {
      entry: 'src/index.ts',
      formats: ['es'],
      fileName: 'civicos-components',
    },
    rollupOptions: {
      external: ['leaflet', 'leaflet/dist/leaflet.css', 'chart.js'],
    },
  },
});
