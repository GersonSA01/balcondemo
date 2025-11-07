import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: "localhost",
    port: 5173,
    strictPort: true,
    origin: "http://localhost:5173",
  },
  build: {
    outDir: "../static/frontend",  // <— compila en BALCONDEMO/static/frontend
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: "./src/main.js",
    },
  },
});

