import { SidebarTrigger } from "@evoloop/shared/components/ui/sidebar"
import { useRouterState } from "@tanstack/react-router"
import {
  Brain,
  FolderOpen,
  GraduationCap,
  ListTodo,
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

export function AppTitleBar() {
  const { t } = useTranslation()
  const router = useRouterState()
  const pathname = router.location.pathname
  const { currentProject } = useProjectStore()

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
    if (pathname.startsWith("/todos"))
      return { title: t("sidebar.todos"), icon: ListTodo }
    if (pathname.startsWith("/learning"))
      return { title: t("sidebar.learning"), icon: GraduationCap }
    if (pathname.startsWith("/settings"))
      return { title: t("sidebar.settings"), icon: Settings }
    return { title: "Evoloop Desktop", icon: Brain }
  }

  const info = getPageInfo()
  if (!info) return null

  const IconComp = info.icon
  const noDragStyle = { WebkitAppRegion: "no-drag" } as React.CSSProperties

  return (
    <div
      data-tauri-drag-region
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      className="h-9 bg-background-soft px-3 flex items-center justify-between shrink-0 text-xs select-none relative z-20"
    >
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
