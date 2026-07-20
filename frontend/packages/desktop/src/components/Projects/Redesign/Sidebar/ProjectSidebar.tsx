import { Link, useNavigate, useParams } from "@tanstack/react-router"
import {
  BrainCircuit,
  Briefcase,
  ChevronDown,
  ChevronLeft,
  Code2,
  FileBox,
  FolderTree,
  GraduationCap,
  KeyRound,
  Palette,
  PanelLeft,
  PanelLeftClose,
  Zap,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
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

import { domainAdapters, getDomainAdapter } from "@/adapters/domainAdapterRegistry"
import type { ProjectDomainMode } from "@/types/domain"

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
  const [selectedDomain, setSelectedDomain] = useState<ProjectDomainMode>("software")

  const adapter = getDomainAdapter(selectedDomain)

  // Keyboard shortcut Cmd+B / Ctrl+B toggle
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
      id: "assets",
      label: adapter.labels.assetsTab,
      icon: FolderTree,
      path: `/projects/${projectId}/assets`,
    },
    {
      id: "knowledge",
      label: adapter.labels.knowledgeTab,
      icon: BrainCircuit,
      path: `/projects/${projectId}/knowledge`,
    },
    {
      id: "workflows",
      label: adapter.labels.workflowsTab,
      icon: Zap,
      path: `/projects/${projectId}/workflows`,
    },
    {
      id: "vault",
      label: adapter.labels.vaultTab,
      icon: KeyRound,
      path: `/projects/${projectId}/vault`,
    },
  ]

  const domainIcons: Record<ProjectDomainMode, any> = {
    software: Code2,
    research: GraduationCap,
    design: Palette,
    business: Briefcase,
    general: FileBox,
  }

  const DomainIcon = domainIcons[selectedDomain] || Code2

  return (
    <aside
      className={`${
        collapsed ? "w-14" : "w-64"
      } border-r border-border bg-card flex flex-col shrink-0 transition-all duration-200 select-none`}
    >
      {/* Settings-style Header Zone: Project Switcher */}
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

            {/* Quick Project Switcher Dropdown */}
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
                    onClick={() => navigate({ to: `/projects/${p.id}/assets` })}
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

            {/* Domain Mode Selector Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger
                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground shrink-0 outline-none"
                title={`当前模式: ${adapter.meta.name}`}
              >
                <DomainIcon className="h-4 w-4 text-primary" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  领域工作区模式
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {(Object.keys(domainAdapters) as ProjectDomainMode[]).map((modeKey) => {
                  const item = domainAdapters[modeKey]
                  const IconComp = domainIcons[modeKey]
                  return (
                    <DropdownMenuItem
                      key={modeKey}
                      onClick={() => setSelectedDomain(modeKey)}
                      className="flex items-center gap-2 text-xs"
                    >
                      <IconComp className="h-3.5 w-3.5 text-primary" />
                      <span>{item.meta.name}</span>
                    </DropdownMenuItem>
                  )
                })}
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

      {/* Settings-style Nav Zone: Clean vertical buttons */}
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

      {/* Footer Zone: Collapse Control & SSE Status Dot */}
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
            {/* Status Indicator Dot */}
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
