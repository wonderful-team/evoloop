import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { createHashHistory } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ApiError, OpenAPI } from "./client"
import { initApiInterceptors } from "./interceptors.ts"
import { ThemeProvider } from "@evoloop/shared/components/theme-provider"
import { Toaster } from "@evoloop/shared/components/ui/sonner"
import i18n from "@evoloop/shared/i18n"
import enLocal from "./locales/en.json"
import zhLocal from "./locales/zh.json"
import "./index.css"
import { routeTree } from "./routeTree.gen"

i18n.addResourceBundle("en", "translation", enLocal, true, true)
i18n.addResourceBundle("zh", "translation", zhLocal, true, true)

OpenAPI.BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:20160"
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}

// 初始化 API 拦截器（处理权限错误）
initApiInterceptors()

const handleApiError = (error: Error) => {
  // 401 未授权 - 跳转到登录
  if (error instanceof ApiError && error.status === 401) {
    localStorage.removeItem("access_token")
    window.location.href = "/login"
    return
  }
  
  // 403 权限不足 - 已由拦截器处理，这里不跳转
  if (error instanceof ApiError && error.status === 403) {
    // 拦截器已经显示了 toast 提示
    // 这里不做任何操作，避免跳转到登录页
    return
  }
}
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

// Use hash history for Tauri WebView compatibility
const hashHistory = createHashHistory()
const router = createRouter({ 
  routeTree,
  history: hashHistory,
})
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
