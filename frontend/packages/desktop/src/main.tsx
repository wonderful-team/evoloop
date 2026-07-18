import { ThemeProvider } from "@evoloop/shared/components/theme-provider"
import { Toaster } from "@evoloop/shared/components/ui/sonner"
import i18n from "@evoloop/shared/i18n"
import "@xterm/xterm/css/xterm.css"

// Configure Monaco Editor Web Workers globally for Vite/Tauri ESM compatibility.
// Resolves warning and prevents UI freezes by executing editors syntax tree parsers inside workers.
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker"
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker"
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker"
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker"
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker"

self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === "json") {
      return new jsonWorker()
    }
    if (label === "css" || label === "less" || label === "scss") {
      return new cssWorker()
    }
    if (label === "html" || label === "handlebars" || label === "razor") {
      return new htmlWorker()
    }
    if (label === "typescript" || label === "javascript") {
      return new tsWorker()
    }
    return new editorWorker()
  },
}

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

// Redirect Tauri WebviewUrl paths to Hash History routes to prevent multi-window routing mismatch
if (window.location.pathname.includes("/android-marker-overlay")) {
  if (!window.location.hash.includes("/android-marker-overlay")) {
    window.location.hash = "#/android-marker-overlay"
  }
} else if (window.location.pathname.includes("/marker-overlay")) {
  if (!window.location.hash.includes("/marker-overlay")) {
    window.location.hash = "#/marker-overlay"
  }
} else if (window.location.pathname.includes("/voice-hud")) {
  if (!window.location.hash.includes("/voice-hud")) {
    window.location.hash = "#/voice-hud"
  }
}

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
