import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "path";

// Build one widget at a time (singlefile plugin limitation)
// Use WIDGET env var to specify which one
const widget = process.env.WIDGET || "voice";

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  build: {
    // Each widget gets its own output directory to avoid overwrites
    outDir: `dist/widgets/${widget}`,
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, `src/widgets/${widget}.html`),
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
