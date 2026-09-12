import { ThemeProvider } from "@evoloop/shared/components/theme-provider"
import { Toaster } from "@evoloop/shared/components/ui/sonner"
import i18n from "@evoloop/shared/i18n"
import "@xterm/xterm/css/xterm.css"

// Tell @monaco-editor/react to use local monaco-editor instead of jsdelivr CDN
import { loader } from "@monaco-editor/react"
import * as monaco from "monaco-editor"

loader.config({ monaco })

// Configure Monaco Editor Web Workers globally for Vite/Tauri ESM compatibility.
// Resolves warning and prevents UI freezes by executing editors syntax tree parsers inside workers.
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker"
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker"
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker"
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker"
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
import {
  normalizeHostContext,
  useHostContextStore,
} from "./stores/hostContextStore"
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

// SSO：Member Center 后台免登（AI 搭子 iframe 链路）
// 检测 URL 上的 evosso 一次性 code → 兑换 member token → 存储 → 刷新进入已登录界面
;(function handleSsoCode() {
  const evosso = new URLSearchParams(window.location.search).get("evosso")
  if (!evosso) return
  // 先清参数（保留 hash 路由），防刷新重复兑换
  const cleanUrl =
    window.location.origin + window.location.pathname + window.location.hash
  window.history.replaceState({}, "", cleanUrl)
  fetch("/api/v1/sso/accept-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sso_code: evosso }),
  })
    .then((res) => res.json())
    .then((res) => {
      const data = res?.data || {}
      if (res?.success !== false && data.access_token) {
        localStorage.setItem("access_token", data.access_token)
        if (data.member_id) {
          localStorage.setItem("evoloop_member_id", String(data.member_id))
        }
        window.location.reload()
      }
    })
    .catch(() => {})
})()

// 宿主上下文（Member Center 后台 iframe 注入）：
// 监听 matrix_context 消息 → 存 store（覆盖式）→ ChatWelcome/聊天链路消费
;(function initHostContextBridge() {
  // 乐观内嵌态：运行于 iframe 即标记（UI 裁剪不等消息到达，避免
  // evosso reload / vite 冷启动等时序竞态导致宿主 UI 闪现全量）。
  // context 数据仍由 matrix_context 消息补充。
  if (window.parent !== window) {
    useHostContextStore.getState().markEmbedded()
  }

  // 唯一配置来源：VITE_HOST_ORIGINS（env 文件/构建注入）——代码零硬编码。
  // 开发默认值在 frontend/.env.development；生产在构建时注入宿主域名。
  const envOrigins =
    (import.meta.env.VITE_HOST_ORIGINS as string | undefined) ?? ""
  const allowed = envOrigins
    .split(",")
    .map((s) => s.trim().replace(/\/$/, ""))
    .filter(Boolean)
  const allowedSet = new Set(allowed)
  if (allowedSet.size === 0) {
    // 审计修复（静默失效告警）：生产构建若漏配 VITE_HOST_ORIGINS，宿主
    // 上下文桥直接不启动——内嵌搭子收不到 matrix_context，域判定静默
    // 降级且无任何报错。内嵌态（iframe）下这是必然失效组合，必须喊出来。
    if (import.meta.env.PROD && window.parent !== window) {
      console.error(
        "[HostContext] iframe embedded but VITE_HOST_ORIGINS is empty — " +
          "host context bridge disabled. Set VITE_HOST_ORIGINS at build time " +
          "(e.g. https://your-host-domain) or the embedded assistant will " +
          "silently lose domain preselection.",
      )
    }
    return
  }

  // 通知宿主 iframe 已就绪，宿主会补发当前页面快照
  try {
    window.parent.postMessage({ type: "matrix_ready", v: 1 }, "*")
  } catch {
    // 非 iframe 环境（直接访问）时无需通知
  }

  window.addEventListener("message", (event: MessageEvent) => {
    if (!allowedSet.has(event.origin.replace(/\/$/, ""))) return
    const data = event.data as { type?: string; payload?: unknown } | null
    if (!data || data.type !== "matrix_context") return
    const ctx = normalizeHostContext(data.payload)
    if (ctx) useHostContextStore.getState().setContext(ctx)
  })
})()

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
