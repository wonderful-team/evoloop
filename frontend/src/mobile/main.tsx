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
import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"
import "@/i18n"
import "@/index.css"

// Use the isolated route tree
import { routeTree } from "./router"
import { OpenAPI } from "@/client"

// Configure API for Mobile (connects to Cloud)
OpenAPI.BASE = import.meta.env.VITE_EVOCLOUD_API_URL || "https://mall.imagicbox.cn"

// Error Handling (Simplified for Mobile)
const handleApiError = (error: Error) => {
  console.error("API Error", error)
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
// Ensure we start at the correct route
if (
  !window.location.hash ||
  window.location.hash === "#/" ||
  window.location.hash.startsWith("#/mobile")
) {
  // Use router to navigate to ensure internal state is updated
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
