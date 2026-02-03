import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteSingleFile } from "vite-plugin-singlefile";
import { readdirSync } from "fs";
import { resolve } from "path";

// Auto-discover widgets
const widgetsDir = resolve(__dirname, "src/widgets");
const widgets = readdirSync(widgetsDir)
  .filter((f) => f.endsWith(".html"))
  .reduce(
    (acc, file) => {
      const name = file.replace(".html", "");
      acc[name] = resolve(widgetsDir, file);
      return acc;
    },
    {} as Record<string, string>
  );

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  build: {
    outDir: "dist/widgets",
    rollupOptions: {
      input: widgets,
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
