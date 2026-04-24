import path from "node:path"
import { fileURLToPath } from "url"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig, loadEnv } from "vite"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, path.resolve(__dirname, "../"), "")
    return {
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./src"),
                "@evoloop/shared": path.resolve(__dirname, "../shared/src"),
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
            emptyOutDir: true,
            outDir: "dist",
        },
        server: {
            port: Number(env.FRONTEND_PORT) || 5173,
            strictPort: true,
            proxy: {
                "/api": {
                    target: env.VITE_API_URL || "http://127.0.0.1:8123",
                    changeOrigin: true,
                },
            },
        },
    }
})
