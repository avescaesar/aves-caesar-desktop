import { defineConfig } from "vite";
import legacy from "@vitejs/plugin-legacy";

export default defineConfig({
  root: "frontend",
  base: "./",
  plugins: [legacy()],
  build: {
    outDir: "dist",
    emptyOutDir: true
  }
});
