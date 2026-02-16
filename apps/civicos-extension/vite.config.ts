import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'path';

export default defineConfig({
  plugins: [svelte()],
  base: '',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        'side-panel': resolve(__dirname, 'src/side-panel/index.html'),
        popup: resolve(__dirname, 'src/popup/index.html'),
        options: resolve(__dirname, 'src/options/index.html'),
        'service-worker': resolve(__dirname, 'src/background/service-worker.ts'),
        'nip07-provider': resolve(__dirname, 'src/content-scripts/nip07-provider.ts'),
        'claude-bridge': resolve(__dirname, 'src/content-scripts/claude-bridge.ts'),
      },
      output: {
        entryFileNames: (chunkInfo) => {
          // Service worker and content scripts need predictable names
          if (chunkInfo.name === 'service-worker') return 'service-worker.js';
          if (chunkInfo.name === 'nip07-provider') return 'content-scripts/nip07-provider.js';
          if (chunkInfo.name === 'claude-bridge') return 'content-scripts/claude-bridge.js';
          return 'assets/[name]-[hash].js';
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
