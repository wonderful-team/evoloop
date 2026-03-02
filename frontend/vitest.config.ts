import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react-swc"
import path from "node:path"

export default defineConfig({
  plugins: [react()],
  test: {
    name: "evoloop-frontend",
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: [
      "packages/**/*.{test,spec}.{ts,tsx}",
      "tests/unit/**/*.{test,spec}.{ts,tsx}",
    ],
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "**/e2e/**",
      "**/playwright/**",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: [
        "**/node_modules/**",
        "**/dist/**",
        "**/*.d.ts",
        "**/*.config.{ts,js}",
        "**/types/**",
        "**/mocks/**",
        "**/tests/**",
        "vitest.setup.ts",
      ],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 50,
        statements: 60,
      },
    },
    alias: {
      "@": path.resolve(__dirname, "./packages/desktop/src"),
      "@mobile": path.resolve(__dirname, "./packages/mobile/src"),
      "@shared": path.resolve(__dirname, "./packages/shared/src"),
      "@evoloop/shared": path.resolve(__dirname, "./packages/shared/src"),
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./packages/desktop/src"),
      "@mobile": path.resolve(__dirname, "./packages/mobile/src"),
      "@shared": path.resolve(__dirname, "./packages/shared/src"),
      "@evoloop/shared": path.resolve(__dirname, "./packages/shared/src"),
    },
  },
})
