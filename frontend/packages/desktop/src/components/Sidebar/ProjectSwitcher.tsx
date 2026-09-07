import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { cn } from "@evoloop/shared/lib/utils"
import { useNavigate } from "@tanstack/react-router"
import {
  CheckCircle2,
  ChevronsUpDown,
  Clock,
  Folder,
  Globe,
  Headset,
  ListTodo,
  RefreshCw,
  Search,
  Unlink,
  XCircle,
} from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectsService } from "@/client"
import { useProjectStatus } from "@/hooks/useProjectStatus"
import { useDutyStore } from "@/stores/dutyStore"
import {
  GLOBAL_PROJECT,
  type Project,
  useProjectStore,
} from "@/stores/projectStore"

function getIndexingStatusDisplay(
  project: Project,
  t: (key: string) => string,
) {
  // Priority 1: Real-time Redis status (indexing)
  if (project.indexing_status === "indexing") {
    return {
      icon: <RefreshCw className="h-3 w-3 animate-spin" />,
      text: t("projectSwitcher.indexing"),
      className: "bg-info/10 text-info",
    }
  }

  // Priority 2: DB persisted status
  const dbStatus = project.db_indexing_status
  switch (dbStatus) {
    case "in_progress":
      return {
        icon: <RefreshCw className="h-3 w-3 animate-spin" />,
        text: t("projectSwitcher.indexing"),
        className: "bg-info/10 text-info",
      }
    case "completed":
      return {
        icon: <CheckCircle2 className="h-3 w-3" />,
        text: t("projectSwitcher.indexed"),
        className: "bg-success/10 text-success",
      }
    case "failed":
      return {
        icon: <XCircle className="h-3 w-3" />,
        text: t("projectSwitcher.indexFailed"),
        className: "bg-destructive/10 text-destructive",
      }
    case "pending":
      return {
        icon: <Clock className="h-3 w-3" />,
        text: t("projectSwitcher.indexPending"),
        className: "bg-warning/10 text-warning",
      }
    default:
      return null
  }
}

interface ProjectSwitcherProps {
  /** Control dialog open state externally */
  open?: boolean
  /** Callback when open state changes */
  onOpenChange?: (open: boolean) => void
  /** Callback when a project is selected */
  onSelect?: (project: Project) => void
}

export function ProjectSwitcher({
  open: controlledOpen,
  onOpenChange,
  onSelect,
}: ProjectSwitcherProps = {}) {
  const { t } = useTranslation()
  const { projects, currentProject, setProject, fetchProjects, isGlobalMode } =
    useProjectStore()
  const [internalOpen, setInternalOpen] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState("")
  const { globalEnabled: dutyGlobalEnabled, wecomEnabled: dutyWecomEnabled } =
    useDutyStore()

  // Support both controlled and uncontrolled modes
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = (value: boolean) => {
    if (!isControlled) {
      setInternalOpen(value)
    }
    onOpenChange?.(value)
  }

  const navigate = useNavigate()

  // Poll for status
  useProjectStatus()

  // Always fetch switchable projects when dialog opens
  React.useEffect(() => {
    fetchProjects("switchable")
  }, [fetchProjects])

  const filteredProjects = projects.filter(
    (project) =>
      project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.description?.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const handleSelect = (project: Project) => {
    // Call custom onSelect if provided
    if (onSelect) {
      onSelect(project)
      setOpen(false)
      return
    }

    // Default behavior: set project in store
    // All projects from 'switchable' filter can be selected
    // (global project is also allowed)
    setProject(project)
    setOpen(false)

    // Sync project selection to backend via ProjectSwitchedEvent
    if (project?.id) {
      import("@/client")
        .then(({ ProjectsService }) => {
          ProjectsService.switchProject({
            requestBody: {
              project_id: project.id!,
              project_name: project.name || "",
            },
          }).catch(() => {})
        })
        .catch(() => {})
    }
  }

  const handleDutyToggle = async (project: Project) => {
    const next = !project.duty_enabled
    try {
      // 读取该项目当前值守配置（保留企微参数与节奏），切换 enabled
      const res = (await ProjectsService.getProjectDuty({
        projectId: project.id,
      })) as Record<string, unknown>
      const duty = { ...res }
      await ProjectsService.updateProjectDuty({
        projectId: project.id,
        requestBody: {
          ...duty,
          enabled: next,
        },
      })
      // 更新 store 中的该项目值守状态
      useProjectStore.setState({
        projects: useProjectStore
          .getState()
          .projects.map((p) =>
            p.id === project.id ? { ...p, duty_enabled: next } : p,
          ),
      })
      if (project.id === useProjectStore.getState().currentProject?.id) {
        useProjectStore.setState({
          currentProject: {
            ...useProjectStore.getState().currentProject!,
            duty_enabled: next,
          },
        })
      }
      toast.success(
        next
          ? t("projectSwitcher.dutyStarted")
          : t("projectSwitcher.dutyStopped"),
      )
    } catch (e) {
      // 后端校验失败（ApiError.body = {detail: {message, errors}}），显示具体原因
      const body = (e as { body?: unknown })?.body as
        | { detail?: { message?: string; errors?: string[] } }
        | undefined
      const reason = body?.detail?.errors ?? []
      const message = body?.detail?.message
      if (reason.length > 0) {
        toast.error(reason.join("；"))
      } else if (message) {
        toast.error(message)
      } else {
        toast.error(t("projectSwitcher.dutyError"))
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {/* Only show trigger button in uncontrolled mode (Sidebar usage) */}
      {!isControlled && (
        <DialogTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between h-10 px-3 bg-transparent border-transparent hover:bg-muted/60 hover:border-transparent"
          >
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="flex aspect-square size-5 items-center justify-center rounded bg-muted text-muted-foreground">
                {isGlobalMode ? (
                  <Globe className="size-3.5" />
                ) : (
                  <Folder className="size-3.5" />
                )}
              </div>
              <span className="truncate font-normal text-foreground/80">
                {isGlobalMode
                  ? t("projectSwitcher.global")
                  : currentProject?.name || t("projectSwitcher.select")}
              </span>
              {(() => {
                // Don't show status badges for global mode
                if (isGlobalMode) return null

                const idxStatus = currentProject
                  ? getIndexingStatusDisplay(currentProject, t)
                  : null
                if (
                  !currentProject?.exists_locally &&
                  currentProject?.local_status === "DISCONNECTED"
                ) {
                  return (
                    <Badge
                      variant="outline"
                      className="ml-2 h-5 text-[10px] px-1.5 font-normal text-muted-foreground border-muted hidden sm:inline-flex gap-1"
                    >
                      <Unlink className="h-3 w-3" />{" "}
                      {t("projectSwitcher.disconnected")}
                    </Badge>
                  )
                }
                if (idxStatus) {
                  return (
                    <Badge
                      variant="secondary"
                      className={cn(
                        "ml-2 h-5 text-[10px] px-1.5 font-normal hidden sm:inline-flex gap-1",
                        idxStatus.className,
                      )}
                    >
                      {idxStatus.icon} {idxStatus.text}
                    </Badge>
                  )
                }
                if (
                  currentProject?.summarization_status === "running" ||
                  currentProject?.summarization_status === "summarizing"
                ) {
                  return (
                    <Badge
                      variant="secondary"
                      className="ml-2 h-5 text-[10px] px-1.5 font-normal bg-signal-purple/10 text-signal-purple hidden sm:inline-flex gap-1"
                    >
                      <ListTodo className="h-3 w-3 animate-pulse" />{" "}
                      {t("projectSwitcher.analyzing")}
                    </Badge>
                  )
                }
                if (currentProject?.status_text) {
                  return (
                    <Badge
                      variant="secondary"
                      className="ml-2 h-5 text-[10px] px-1.5 font-normal text-muted-foreground hidden sm:inline-flex"
                    >
                      {currentProject.status_text}
                    </Badge>
                  )
                }
                return null
              })()}
            </div>
            <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-4xl max-h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
        <div className="p-4 border-b border-border">
          <DialogHeader className="mb-4">
            <DialogTitle>{t("projectSwitcher.title")}</DialogTitle>
            <DialogDescription>
              {t("projectSwitcher.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t("projectSwitcher.desktopSearchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <div className="overflow-y-auto p-4 flex-1">
          {/* Global Mode Option */}
          <div
            onClick={() => handleSelect(GLOBAL_PROJECT)}
            className={cn(
              "rounded-lg border border-border shadow-sm transition-all relative group mb-4 cursor-pointer",
              isGlobalMode
                ? "border-primary ring-1 ring-primary bg-card text-card-foreground"
                : "bg-card text-card-foreground hover:border-primary hover:shadow-md",
            )}
          >
            <div className="p-3 flex items-center gap-3">
              <div className="flex aspect-square size-8 items-center justify-center rounded bg-gradient-to-br from-blue-500 to-purple-500 text-white">
                <Globe className="size-4" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-sm">
                  {t("projectSwitcher.global")}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {t("projectSwitcher.globalDesc")}
                </p>
              </div>
              {isGlobalMode && (
                <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg bg-primary" />
              )}
            </div>
          </div>

          <div className="border-t my-3" />

          {filteredProjects.length === 0 ? (
            <div className="flex h-[300px] flex-col items-center justify-center text-center text-muted-foreground">
              <Folder className="h-12 w-12 mb-2 opacity-20" />
              <p>{t("projectSwitcher.noProjects")}</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {filteredProjects.map((project) => {
                const isSelected = currentProject?.id === project.id
                return (
                  <div
                    key={project.id}
                    onClick={() => handleSelect(project)}
                    className={cn(
                      "rounded-lg border border-border shadow-sm transition-all relative group cursor-pointer hover:border-primary hover:shadow-md",
                      isSelected
                        ? "border-primary ring-1 ring-primary bg-card text-card-foreground"
                        : "bg-card text-card-foreground",
                    )}
                  >
                    <div className="p-3 flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold leading-none tracking-tight truncate">
                            {project.name}
                          </h3>
                          <Badge
                            variant={
                              project.status === 1 ? "default" : "secondary"
                            }
                            className={cn(
                              "shrink-0 capitalize text-[10px] px-1.5 py-0 h-5",
                              project.status === 1
                                ? "bg-success/15 text-success hover:bg-success/25"
                                : "",
                            )}
                          >
                            {project.status_text ||
                              t("projectSwitcher.unknown")}
                          </Badge>
                          {/* Indexing Status */}
                          {(() => {
                            const idxStatus = getIndexingStatusDisplay(
                              project,
                              t,
                            )
                            if (!idxStatus) return null
                            return (
                              <Badge
                                variant="secondary"
                                className={cn(
                                  "shrink-0 text-[10px] px-1.5 py-0 h-5 gap-1",
                                  idxStatus.className,
                                )}
                                title={
                                  project.last_indexed_at
                                    ? t("projectSwitcher.lastIndexed", {
                                        time: project.last_indexed_at,
                                      })
                                    : undefined
                                }
                              >
                                {idxStatus.icon}
                                {idxStatus.text}
                              </Badge>
                            )
                          })()}
                        </div>
                        <p
                          className="text-xs text-muted-foreground truncate font-mono"
                          title={project.path}
                        >
                          {project.path}
                        </p>
                      </div>

                      <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
                        <div
                          className="flex items-center gap-1.5 w-24"
                          title={t("projectSwitcher.tasks")}
                        >
                          <ListTodo className="h-3.5 w-3.5" />
                          <span>
                            {project.task_stats?.pending || 0} /{" "}
                            {project.task_stats?.total || 0}{" "}
                            {t("projectSwitcher.tasks")}
                          </span>
                        </div>
                        {/* 值守参与按钮（替换原日期列） */}
                        <div className="w-24 justify-end">
                          <Button
                            variant={
                              project.duty_enabled ? "secondary" : "outline"
                            }
                            size="sm"
                            className={cn(
                              "h-7 gap-1 px-2 text-xs",
                              project.duty_enabled &&
                                "bg-success/10 text-success hover:bg-success/20 border-success/20",
                            )}
                            disabled={
                              !project.duty_enabled &&
                              (!dutyGlobalEnabled || !dutyWecomEnabled)
                            }
                            title={
                              !project.duty_enabled &&
                              (!dutyGlobalEnabled || !dutyWecomEnabled)
                                ? t("projectSwitcher.dutyDisabled")
                                : undefined
                            }
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDutyToggle(project)
                            }}
                          >
                            <Headset className="h-3.5 w-3.5" />
                            {project.duty_enabled
                              ? t("projectSwitcher.dutyOn")
                              : t("projectSwitcher.dutyOff")}
                          </Button>
                        </div>
                      </div>
                    </div>

                    {isSelected && (
                      <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg bg-primary" />
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-muted/50 flex justify-between items-center text-xs text-muted-foreground">
          <span>
            {t("projectSwitcher.showing", { count: filteredProjects.length })}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => {
              setOpen(false)
              navigate({ to: "/projects" })
            }}
          >
            {t("projectSwitcher.manage")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
