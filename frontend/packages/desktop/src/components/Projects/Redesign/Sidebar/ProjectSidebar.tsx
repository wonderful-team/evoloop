import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  FileText,
  FolderTree,
  KeyRound,
  PanelLeft,
  PanelLeftClose,
  Zap,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

interface ProjectSidebarProps {
  currentProject: any
  projects: any[]
  indexingStatus?: string
}

export function ProjectSidebar({
  currentProject,
  projects,
  indexingStatus = "synced",
}: ProjectSidebarProps) {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault()
        setCollapsed((prev) => !prev)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  const topLevelEntrances = [
    {
      id: "overview",
      label: "项目概览",
      icon: FileText,
      path: `/projects/${projectId}/overview`,
    },
    {
      id: "wiki",
      label: "Wiki 文档",
      icon: BookOpen,
      path: `/projects/${projectId}/wiki`,
    },
    {
      id: "files",
      label: "文件浏览",
      icon: FolderTree,
      path: `/projects/${projectId}/files`,
    },
    {
      id: "macros",
      label: "指令管理",
      icon: Zap,
      path: `/projects/${projectId}/macros`,
    },
    {
      id: "vault",
      label: "密钥保险箱",
      icon: KeyRound,
      path: `/projects/${projectId}/vault`,
    },
  ]

  return (
    <aside
      className={`${
        collapsed ? "w-14" : "w-64"
      } border-r border-border bg-card flex flex-col shrink-0 transition-all duration-200 select-none`}
    >
      {/* Header: Project Switcher */}
      <div
        data-tauri-drag-region
        style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
        className="h-14 flex items-center justify-between px-3 border-b border-border"
      >
        {!collapsed ? (
          <div
            className="flex items-center gap-2 overflow-hidden w-full"
            style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
          >
            <Link
              to="/projects"
              className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground shrink-0"
              title={t("projects.backToList", "返回项目列表")}
            >
              <ChevronLeft className="h-4 w-4" />
            </Link>

            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-1.5 font-bold text-sm truncate hover:text-primary transition-colors text-left flex-1 min-w-0 outline-none">
                <span className="truncate">
                  {currentProject?.name || `Project #${projectId}`}
                </span>
                <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  {t("projects.quickSwitch", "快速切换项目")}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {projects.map((p) => (
                  <DropdownMenuItem
                    key={p.id}
                    onClick={() => navigate({ to: `/projects/${p.id}/overview` })}
                    className="flex items-center justify-between text-xs"
                  >
                    <span className="truncate">{p.name}</span>
                    {p.id === Number(projectId) && (
                      <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                        当前
                      </span>
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ) : (
          <Link
            to="/projects"
            className="mx-auto p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
            title={t("projects.backToList", "返回项目列表")}
          >
            <ChevronLeft className="h-4 w-4" />
          </Link>
        )}
      </div>

      {/* Navigation */}
      <TooltipProvider delayDuration={200}>
        <nav className="flex-1 p-3 flex flex-col gap-1 overflow-y-auto">
          {topLevelEntrances.map((entrance) => {
            const Icon = entrance.icon
            return (
              <div key={entrance.id}>
                {!collapsed ? (
                  <Link
                    to={entrance.path}
                    className="group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200 text-muted-foreground hover:bg-muted hover:text-foreground data-[status=active]:bg-primary data-[status=active]:text-primary-foreground"
                    activeProps={{ "data-status": "active" }}
                  >
                    <Icon className="h-4 w-4 transition-transform group-hover:scale-110 shrink-0" />
                    <span className="truncate">{entrance.label}</span>
                  </Link>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Link
                        to={entrance.path}
                        className="flex justify-center p-2.5 rounded-md hover:bg-muted transition-colors data-[status=active]:bg-primary data-[status=active]:text-primary-foreground"
                        activeProps={{ "data-status": "active" }}
                      >
                        <Icon className="h-4 w-4" />
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="text-xs">
                      {entrance.label}
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            )
          })}
        </nav>
      </TooltipProvider>

      {/* Footer */}
      <div className="p-3 border-t border-border flex items-center justify-between">
        {!collapsed ? (
          <div className="flex items-center justify-between w-full text-xs text-muted-foreground">
            <button
              onClick={() => setCollapsed(true)}
              className="flex items-center gap-2 px-2 py-1 hover:text-foreground hover:bg-muted rounded-md transition-colors"
            >
              <PanelLeftClose className="h-4 w-4" />
              <span>折叠 (Cmd+B)</span>
            </button>
            <div className="flex items-center gap-1.5 px-2" title={`管道状态: ${indexingStatus}`}>
              <span
                className={`h-2 w-2 rounded-full ${
                  indexingStatus === "indexing"
                    ? "bg-blue-500 animate-pulse"
                    : indexingStatus === "failed"
                      ? "bg-red-500"
                      : "bg-emerald-500"
                }`}
              />
            </div>
          </div>
        ) : (
          <button
            onClick={() => setCollapsed(false)}
            className="mx-auto p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
            title="展开侧边栏 (Cmd+B)"
          >
            <PanelLeft className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  )
}
