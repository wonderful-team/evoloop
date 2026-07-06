import { ThemeProvider } from "@evoloop/shared/components/theme-provider"
import { Toaster } from "@evoloop/shared/components/ui/sonner"
import i18n from "@evoloop/shared/i18n"
import "@xterm/xterm/css/xterm.css"

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
import { toast } from "sonner"
import { ApiError, OpenAPI } from "./client"
import { initApiInterceptors } from "./interceptors.ts"
import enLocal from "./locales/en.json"
import zhLocal from "./locales/zh.json"
import "./index.css"
import { routeTree } from "./routeTree.gen"

i18n.addResourceBundle("en", "translation", enLocal, true, true)
i18n.addResourceBundle("zh", "translation", zhLocal, true, true)

OpenAPI.BASE = import.meta.env.DEV ? "" : import.meta.env.VITE_API_URL
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}

// 初始化 API 拦截器（处理权限错误）
initApiInterceptors()

// 全局标志，防止重复显示401提示
let isHandling401 = false

const handleApiError = (error: Error) => {
  // 401 未授权 - 跳转到登录
  if (error instanceof ApiError && error.status === 401) {
    // 如果已经在处理401，避免重复操作
    if (isHandling401) return
    isHandling401 = true

    // 保存当前完整路径（包括hash路径和query参数），用于登录后返回
    const currentPath = window.location.hash
    if (currentPath && currentPath !== "#/login") {
      localStorage.setItem("redirect_after_login", currentPath)
      console.log("[401 Handler] Saved redirect path:", currentPath)
    }

    // 清除token
    localStorage.removeItem("access_token")

    // 显示提示
    toast.error(i18n.t("auth.sessionExpired"), {
      description: i18n.t("auth.pleaseLoginAgain"),
      duration: 5000,
    })

    // 延迟跳转，让用户看到提示
    setTimeout(() => {
      window.location.hash = "#/login"
    }, 500)
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
