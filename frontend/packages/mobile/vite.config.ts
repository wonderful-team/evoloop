import path from "node:path"
import { fileURLToPath } from "url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig({
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
            "@evoloop/shared": path.resolve(__dirname, "../shared/src"),
        },
    },
    plugins: [
        react(),
        tailwindcss(),
    ],
    build: {
        emptyOutDir: true,
        outDir: "dist",
    },
    server: {
        port: 5174,
        strictPort: true,
        host: true,
    },
})
