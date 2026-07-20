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
import React from "react"
import { useTranslation } from "react-i18next"
import { useProjectStore } from "@/stores/projectStore"

export function AppTitleBar() {
  const { t } = useTranslation()
  const router = useRouterState()
  const pathname = router.location.pathname
  const { currentProject } = useProjectStore()

  // Project route check
  const matchProject = pathname.match(/\/projects\/(\d+)/)
  const projectId = matchProject ? matchProject[1] : null

  // Map routes to human readable title & icons
  const getPageInfo = () => {
    if (projectId) {
      return {
        title: currentProject?.name ? `项目 / ${currentProject.name}` : `项目详情 #${projectId}`,
        icon: FolderOpen,
      }
    }
    if (pathname.startsWith("/chat")) return { title: t("sidebar.chat", "聊天智能助手"), icon: MessageSquare }
    if (pathname === "/projects") return { title: t("sidebar.projects", "项目列表中心"), icon: FolderOpen }
    if (pathname.startsWith("/todos")) return { title: t("sidebar.todos", "待办与任务列表"), icon: ListTodo }
    if (pathname.startsWith("/learning")) return { title: t("sidebar.learning", "学习与 Skill 中心"), icon: GraduationCap }
    if (pathname.startsWith("/settings")) return { title: t("sidebar.settings", "系统设置"), icon: Settings }
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
      className="h-9 border-b border-border/60 bg-card/60 backdrop-blur-xs px-3 flex items-center justify-between shrink-0 text-xs select-none relative z-20"
    >
      {/* Left: Sidebar Trigger & Page Breadcrumb */}
      <div className="flex items-center gap-2">
        <div style={noDragStyle}>
          <SidebarTrigger className="h-6 w-6 p-0 hover:bg-muted text-muted-foreground hover:text-foreground" />
        </div>
        <div className="h-3 w-[1px] bg-border/60" />
        <div className="flex items-center gap-1.5 font-medium text-foreground/80">
          <IconComp className="h-3.5 w-3.5 text-primary shrink-0" />
          <span className="truncate max-w-[260px]">{info.title}</span>
        </div>
      </div>

      {/* Center & Right: Clean Window Drag Area */}
      <div className="flex items-center gap-2" style={noDragStyle}>
        {/* Sleek, minimal titlebar right space */}
      </div>
    </div>
  )
}
