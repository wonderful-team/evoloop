import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  root: path.resolve(__dirname, "packages/desktop"),
  envDir: __dirname,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./packages/desktop/src"),
      "@evoloop/shared": path.resolve(__dirname, "./packages/shared/src"),
    },
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
      routesDirectory: "./src/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
    }),
    react(),
    tailwindcss(),
  ],
  build: {
    outDir: path.resolve(__dirname, "dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "packages/desktop/index.html"),
      },
    },
  },
  // Tauri expects a fixed port, fail if that port is not available
  server: {
    port: Number(process.env.FRONTEND_PORT) || 5173,
    strictPort: true,
    host: true,
  },
  clearScreen: false,
})
