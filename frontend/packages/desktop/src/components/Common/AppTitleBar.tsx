import { SidebarTrigger } from "@evoloop/shared/components/ui/sidebar"
import { useRouter, useRouterState } from "@tanstack/react-router"
import {
  Brain,
  FolderOpen,
  GraduationCap,
  MessageSquare,
  Settings,
} from "lucide-react"
import type React from "react"
import { useTranslation } from "react-i18next"
import {
  ChatTitleActions,
  ChatTitleBreadcrumb,
} from "@/components/Chat/ChatTitleSlot"
import { useProjectStore } from "@/stores/projectStore"
import { useUIStore } from "@/stores/uiStore"

export function AppTitleBar() {
  const { t } = useTranslation()
  const routerState = useRouterState()
  const router = useRouter()
  const pathname = routerState.location.pathname
  const { currentProject } = useProjectStore()
  // 迷你模式窗口收窄（Tauri miniWindow 400px / Web 迷你卡片），顶栏 Tabs 换用短文案防换行
  const miniMode = useUIStore((s) => s.miniMode)

  // Project route check
  const matchProject = pathname.match(/\/projects\/(\d+)/)
  const projectId = matchProject ? matchProject[1] : null

  // Chat context slot: only on /chat with an active project
  const hasChatContext = pathname.startsWith("/chat") && !!currentProject

  // Map routes to human readable title & icons
  const getPageInfo = () => {
    if (projectId) {
      return {
        title: currentProject?.name
          ? `项目 / ${currentProject.name}`
          : `项目详情 #${projectId}`,
        icon: FolderOpen,
      }
    }
    if (pathname.startsWith("/chat"))
      return { title: t("sidebar.chat"), icon: MessageSquare }
    if (pathname === "/projects")
      return { title: t("sidebar.projects"), icon: FolderOpen }
    if (pathname.startsWith("/learning"))
      return { title: t("sidebar.learning"), icon: GraduationCap }
    if (pathname.startsWith("/settings"))
      return { title: t("sidebar.settings"), icon: Settings }
    return { title: "Evoloop Desktop", icon: Brain }
  }

  const info = getPageInfo()
  if (!info) return null

  const IconComp = info.icon
  // 顶栏视图 Tabs 显隐开关（对话/值守切换）：当前隐藏，入口为工作台/侧边栏
  const SHOW_VIEW_TABS = false
  const noDragStyle = { WebkitAppRegion: "no-drag" } as React.CSSProperties

  return (
    <div
      data-tauri-drag-region
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      className="h-9 bg-background-soft px-3 flex items-center justify-between shrink-0 text-xs select-none relative z-20"
    >
      {/* Center: top-level view tabs (chat | autonomous duty)
          暂时隐藏（不删）：恢复时将 SHOW_VIEW_TABS 改回 true */}
      {SHOW_VIEW_TABS &&
        (pathname.startsWith("/chat") || pathname.startsWith("/duty-autonomous")) && (
        <div
          style={{ ...noDragStyle, left: "50%", transform: "translateX(-50%)" }}
          className="absolute flex items-center rounded-md border bg-muted/60 p-0.5 gap-0.5"
        >
          {[
            {
              key: "chat",
              label: miniMode
                ? t("sidebar.chatShort", "对话")
                : t("sidebar.chat"),
              to: "/chat",
            },
            {
              key: "duty",
              label: miniMode
                ? t("sidebar.dutyAutonomousShort", "值守")
                : t("sidebar.dutyAutonomous", "自主值守（实验）"),
              to: "/duty-autonomous",
            },
          ].map((tab) => {
            const active = pathname.startsWith(tab.to)
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => (active ? undefined : router.navigate({ to: tab.to }))}
                className={`px-3 h-6 rounded text-xs font-medium whitespace-nowrap transition-colors ${
                  active
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Left: Sidebar Trigger & Page Breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        <div style={noDragStyle}>
          <SidebarTrigger className="h-6 w-6 p-0 hover:bg-muted text-muted-foreground hover:text-foreground" />
        </div>
        <div className="h-3 w-[1px] bg-border/60" />
        {hasChatContext ? (
          <ChatTitleBreadcrumb />
        ) : (
          <div className="flex items-center gap-1.5 font-normal text-foreground/55">
            <IconComp className="h-3.5 w-3.5 text-primary/50 shrink-0" />
            <span className="truncate max-w-[260px]">{info.title}</span>
          </div>
        )}
      </div>

      {/* Right: Chat contextual actions (compact window entry points) */}
      <div className="flex items-center gap-2 shrink-0">
        {hasChatContext && <ChatTitleActions />}
      </div>
    </div>
  )
}

export default AppTitleBar
