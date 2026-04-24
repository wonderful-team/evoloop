import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./packages/desktop/src"),
      "@evoloop/shared": path.resolve(__dirname, "./packages/shared/src"),
    },
  },
  envDir: "./",
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
      routesDirectory: "./packages/desktop/src/routes",
      generatedRouteTree: "./packages/desktop/src/routeTree.gen.ts",
    }),
    react(),
    tailwindcss(),
  ],
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "packages/desktop/index.html"),
        mobile: path.resolve(__dirname, "packages/mobile/index.html"),
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
