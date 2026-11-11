import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  root: "frontend",
  base: "./",
  plugins: [vue()],
  build: {
    outDir: "../views/settings",
    emptyOutDir: true,
    rollupOptions: {
      input: "frontend/index.html",
    },
  },
});
