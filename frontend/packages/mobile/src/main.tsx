/**
 * Mobile App Entry Point
 * This is the main entry for the mobile application.
 * It uses the mobile-specific client that connects to the Cloud API.
 */
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import {
  createHashHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ThemeProvider } from "@evoloop/shared/components/theme-provider"
import { Toaster } from "@evoloop/shared/components/ui/sonner"

// Mobile-specific i18n and styles
import i18n from "@evoloop/shared/i18n"
import enLocal from "./locales/en.json"
import zhLocal from "./locales/zh.json"
import "./index.css"

// Use the isolated route tree
import { routeTree } from "./router"

i18n.addResourceBundle("en", "translation", enLocal, true, true)
i18n.addResourceBundle("zh", "translation", zhLocal, true, true)

// Error Handling (Simplified for Mobile)
const handleApiError = (error: Error) => {
  console.error("Mobile API Error", error)
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

// Create router with isolated tree and hash history for mobile
const router = createRouter({
  routeTree: routeTree,
  history: createHashHistory(),
})

// Ensure we start at the correct route
if (
  !window.location.hash ||
  window.location.hash === "#/" ||
  window.location.hash.startsWith("#/mobile")
) {
  setTimeout(() => {
    router.navigate({ to: "/" as any, replace: true })
  }, 0)
}

console.log("Mobile App Mounting...")

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="light" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
