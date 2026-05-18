import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  CheckCircle2,
  AlertCircle,
  Loader2,
  Layers,
  Link2,
  Clock,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Cloud,
  CloudOff,
} from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Progress } from "@evoloop/shared/components/ui/progress"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { cn } from "@evoloop/shared/lib/utils"
import { useRequirementStore, type RequirementTask } from "@/stores/requirementStore"

interface TaskVisualizationProps {
  projectId: number
  docId: string
  analysisId: string
}

export function TaskVisualization({
  projectId,
  docId,
  analysisId,
}: TaskVisualizationProps) {
  const { t } = useTranslation()
  const {
    currentTasks,
    syncProgress,
    isLoadingTasks,
    fetchAnalysisTasks,
    fetchSyncProgress,
    getTaskSyncStatusColor,
  } = useRequirementStore()

  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const [viewMode, setViewMode] = useState<"list" | "mapping">("mapping")

  useEffect(() => {
    fetchAnalysisTasks(projectId, docId, analysisId)
    fetchSyncProgress(projectId, docId, analysisId)

    // Poll for progress updates
    const interval = setInterval(() => {
      fetchSyncProgress(projectId, docId, analysisId)
    }, 5000)

    return () => clearInterval(interval)
  }, [projectId, docId, analysisId, fetchAnalysisTasks, fetchSyncProgress])

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev)
      if (next.has(taskId)) {
        next.delete(taskId)
      } else {
        next.add(taskId)
      }
      return next
    })
  }

  const getSyncStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock className="h-4 w-4 text-gray-400" />
      case "syncing":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case "synced":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case "failed":
        return <AlertCircle className="h-4 w-4 text-red-500" />
      default:
        return <Clock className="h-4 w-4 text-gray-400" />
    }
  }

  const getPriorityColor = (priority: string) => {
    const colors: Record<string, string> = {
      urgent: "bg-red-100 text-red-800",
      high: "bg-orange-100 text-orange-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-green-100 text-green-800",
    }
    return colors[priority.toLowerCase()] || "bg-gray-100 text-gray-800"
  }

  const getCategoryIcon = (category: string) => {
    const icons: Record<string, string> = {
      frontend: "🎨",
      backend: "⚙️",
      database: "🗄️",
      api: "🔌",
      test: "🧪",
      devops: "🚀",
      design: "✏️",
    }
    return icons[category.toLowerCase()] || "📋"
  }

  if (isLoadingTasks) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!currentTasks || currentTasks.tasks.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Layers className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p>{t("requirements.tasks.noTasks", "暂无任务")}</p>
        <p className="text-xs mt-1">
          {t("requirements.tasks.analysisNotConfirmed", "请先确认分析结果以生成任务")}
        </p>
      </div>
    )
  }

  const { tasks, sync_stats, requirement_mapping } = currentTasks
  const progress = syncProgress?.progress

  return (
    <div className="space-y-6">
      {/* Sync Progress Header */}
      {progress && (
        <div className="p-4 bg-muted/50 rounded-lg space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cloud className="h-5 w-5 text-primary" />
              <span className="font-medium">
                {t("requirements.tasks.syncProgress", "EvoCloud 同步进度")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {progress.is_complete ? (
                progress.has_failures ? (
                  <Badge variant="outline" className="text-orange-600">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    {t("requirements.tasks.partialSync", "部分同步")}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-green-600">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    {t("requirements.tasks.syncComplete", "同步完成")}
                  </Badge>
                )
              ) : (
                <Badge variant="outline" className="text-blue-600">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  {t("requirements.tasks.syncing", "同步中...")}
                </Badge>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => fetchSyncProgress(projectId, docId, analysisId)}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                {progress.synced}/{progress.total} {t("requirements.tasks.synced", "已同步")}
              </span>
              <span className="font-medium">{progress.percentage}%</span>
            </div>
            <Progress value={progress.percentage} className="h-2" />
          </div>

          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-gray-400" />
              <span className="text-muted-foreground">
                {t("requirements.tasks.pending", "待同步")}: {sync_stats.pending}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-muted-foreground">
                {t("requirements.tasks.syncing", "同步中")}: {sync_stats.syncing}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-muted-foreground">
                {t("requirements.tasks.synced", "已同步")}: {sync_stats.synced}
              </span>
            </div>
            {sync_stats.failed > 0 && (
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-red-600">
                  {t("requirements.tasks.failed", "失败")}: {sync_stats.failed}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* View Mode Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-muted-foreground" />
          <span className="font-medium">
            {t("requirements.tasks.title", "任务列表")}
            <span className="text-muted-foreground ml-2">({tasks.length})</span>
          </span>
        </div>
        <div className="flex gap-2">
          <Button
            variant={viewMode === "list" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setViewMode("list")}
          >
            {t("requirements.tasks.listView", "列表")}
          </Button>
          <Button
            variant={viewMode === "mapping" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setViewMode("mapping")}
          >
            <Link2 className="h-4 w-4 mr-1" />
            {t("requirements.tasks.mappingView", "映射")}
          </Button>
        </div>
      </div>

      {/* Task List */}
      {viewMode === "list" ? (
        <ScrollArea className="h-[400px]">
          <div className="space-y-3 pr-4">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                isExpanded={expandedTasks.has(task.id)}
                onToggle={() => toggleTask(task.id)}
                getSyncStatusIcon={getSyncStatusIcon}
                getPriorityColor={getPriorityColor}
                getCategoryIcon={getCategoryIcon}
                getTaskSyncStatusColor={getTaskSyncStatusColor}
              />
            ))}
          </div>
        </ScrollArea>
      ) : (
        <RequirementTaskMapping
          tasks={tasks}
          requirementMapping={requirement_mapping}
          getSyncStatusIcon={getSyncStatusIcon}
          getPriorityColor={getPriorityColor}
          getCategoryIcon={getCategoryIcon}
        />
      )}
    </div>
  )
}

interface TaskCardProps {
  task: RequirementTask
  isExpanded: boolean
  onToggle: () => void
  getSyncStatusIcon: (status: string) => React.ReactNode
  getPriorityColor: (priority: string) => string
  getCategoryIcon: (category: string) => string
  getTaskSyncStatusColor: (status: string) => string
}

function TaskCard({
  task,
  isExpanded,
  onToggle,
  getSyncStatusIcon,
  getPriorityColor,
  getCategoryIcon,
  getTaskSyncStatusColor,
}: TaskCardProps) {
  const { t } = useTranslation()

  return (
    <div className="border rounded-lg overflow-hidden">
      <div
        className="p-3 flex items-start justify-between gap-3 cursor-pointer hover:bg-muted/50"
        onClick={onToggle}
      >
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <span className="text-lg">{getCategoryIcon(task.category)}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium truncate">{task.title}</span>
              <Badge className={cn("text-xs", getPriorityColor(task.priority))}>
                {task.priority}
              </Badge>
              {task.requirement_refs.length > 0 && (
                <Badge variant="outline" className="text-xs">
                  {task.requirement_refs.join(", ")}
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground line-clamp-1 mt-1">
              {task.description}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Badge
            variant="secondary"
            className={cn("text-xs flex items-center gap-1", getTaskSyncStatusColor(task.sync_status))}
          >
            {getSyncStatusIcon(task.sync_status)}
            {task.sync_status}
          </Badge>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="px-3 pb-3 pt-0 border-t border-border bg-muted/30">
          <div className="pt-3 space-y-3">
            <p className="text-sm">{task.description}</p>

            {task.estimated_hours > 0 && (
              <div className="flex items-center gap-2 text-sm">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span>
                  {t("requirements.tasks.estimatedHours", "预计工时")}: {task.estimated_hours}h
                </span>
              </div>
            )}

            {task.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {task.tags.map((tag) => (
                  <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}

            {task.acceptance_criteria.length > 0 && (
              <div>
                <h5 className="text-sm font-medium mb-2">
                  {t("requirements.tasks.acceptanceCriteria", "验收标准")}
                </h5>
                <ul className="text-sm space-y-1">
                  {task.acceptance_criteria.map((criteria, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <CheckCircle2 className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <span>{criteria}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {task.sync_error && (
              <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 p-2 rounded">
                <CloudOff className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>{task.sync_error}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

interface RequirementTaskMappingProps {
  tasks: RequirementTask[]
  requirementMapping: {
    by_requirement: Record<string, string[]>
    by_task: Record<string, string[]>
    unmapped_tasks: string[]
  }
  getSyncStatusIcon: (status: string) => React.ReactNode
  getPriorityColor: (priority: string) => string
  getCategoryIcon: (category: string) => string
}

function RequirementTaskMapping({
  tasks,
  requirementMapping,
  getSyncStatusIcon,
  getPriorityColor,
  getCategoryIcon,
}: RequirementTaskMappingProps) {
  const { t } = useTranslation()
  const taskMap = new Map(tasks.map((t) => [t.id, t]))

  const renderTaskNode = (taskId: string) => {
    const task = taskMap.get(taskId)
    if (!task) return null

    return (
      <div
        key={taskId}
        className="flex items-center gap-2 p-2 bg-background border rounded hover:shadow-sm transition-shadow"
      >
        <span>{getCategoryIcon(task.category)}</span>
        <span className="text-sm truncate flex-1">{task.title}</span>
        {getSyncStatusIcon(task.sync_status)}
      </div>
    )
  }

  return (
    <ScrollArea className="h-[400px]">
      <div className="space-y-4 pr-4">
        {/* Mapped Requirements */}
        {Object.entries(requirementMapping.by_requirement).map(([reqRef, taskIds]) => (
          <div key={reqRef} className="border rounded-lg p-3">
            <div className="flex items-center gap-2 mb-3">
              <Badge variant="outline" className="font-mono text-xs">
                {reqRef}
              </Badge>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {taskIds.length} {t("requirements.tasks.tasks", "个任务")}
              </span>
            </div>
            <div className="space-y-2 pl-4 border-l-2 border-primary/20">
              {taskIds.map(renderTaskNode)}
            </div>
          </div>
        ))}

        {/* Unmapped Tasks */}
        {requirementMapping.unmapped_tasks.length > 0 && (
          <div className="border rounded-lg p-3 bg-muted/30">
            <div className="flex items-center gap-2 mb-3">
              <Badge variant="secondary" className="text-xs">
                {t("requirements.tasks.unmapped", "未关联需求")}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {requirementMapping.unmapped_tasks.length} {t("requirements.tasks.tasks", "个任务")}
              </span>
            </div>
            <div className="space-y-2 pl-4 border-l-2 border-muted">
              {requirementMapping.unmapped_tasks.map(renderTaskNode)}
            </div>
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
