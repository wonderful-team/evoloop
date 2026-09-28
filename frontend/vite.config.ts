import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig, loadEnv } from "vite"

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "")
  console.log("============ VITE PROXY TARGET: ============")
  console.log("VITE_API_URL =", env.VITE_API_URL)
  console.log("EVOCLOUD_API_URL =", env.EVOCLOUD_API_URL)
  console.log("============================================")

  return {
    base: "./",
    root: path.resolve(__dirname, "packages/desktop"),
    envDir: path.resolve(__dirname, ".."),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./packages/desktop/src"),
        "@evoloop/shared": path.resolve(__dirname, "./packages/shared/src"),
        "@evoloop/workbench": path.resolve(__dirname, "./packages/workbench/src"),
      },
      dedupe: ["react", "react-dom"],
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
    optimizeDeps: {
      include: [
        "react",
        "react-dom",
        "react-dom/client",
        "@radix-ui/react-collapsible",
        "react-resizable-panels",
      ],
    },
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
      port: Number(env.FRONTEND_PORT) || 5173,
      strictPort: true,
      host: true,
      proxy: {
        "/api": {
          target: env.VITE_API_URL || "http://127.0.0.1:20160", // 后端统一端口
          changeOrigin: true,
          timeout: 0,
        },
      },
    },
    clearScreen: false,
  }
})
