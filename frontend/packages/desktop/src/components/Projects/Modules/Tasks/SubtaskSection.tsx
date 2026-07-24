import { Badge } from "@evoloop/shared/components/ui/badge"
import { cn } from "@evoloop/shared/lib/utils"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { SubtasksService } from "@/client"
import { TaskProgressEdit } from "./TaskProgressEdit"

interface SubtaskSectionProps {
  projectId: number
  taskId: number
}

interface TaskTreeNode {
  id: number
  title: string
  description?: string
  status: string
  progress: number
  priority?: string
  estimated_hours?: number
  children?: TaskTreeNode[]
}

export function SubtaskSection({ projectId, taskId }: SubtaskSectionProps) {
  const { t } = useTranslation()
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const {
    data: taskTree,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["task-tree", projectId, taskId],
    queryFn: async () => {
      const res: any = await SubtasksService.getTaskTree({
        projectId,
        taskId: String(taskId),
        maxDepth: 10,
      })
      return res as TaskTreeNode
    },
  })

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: "bg-gray-100 text-gray-700",
      in_progress: "bg-blue-100 text-blue-700",
      completed: "bg-green-100 text-green-700",
      blocked: "bg-red-100 text-red-700",
    }
    return colors[status] || "bg-gray-100 text-gray-700"
  }

  const getStatusText = (status: string) => {
    const texts: Record<string, string> = {
      pending: t("projects.tasks.statusLabel.pending"),
      in_progress: t("projects.tasks.statusLabel.inProgress"),
      completed: t("projects.tasks.statusLabel.completed"),
      blocked: t("projects.tasks.statusLabel.blocked"),
    }
    return texts[status] || status
  }

  const renderTaskNode = (node: TaskTreeNode, level: number = 0) => {
    const isExpanded = expandedIds.has(node.id)
    const hasChildren = node.children && node.children.length > 0

    return (
      <div key={node.id} className="select-none">
        <div
          className={cn(
            "flex items-center gap-2 p-3 rounded-lg border transition-colors",
            level === 0 ? "bg-muted/30" : "bg-background",
            "hover:border-primary/30",
          )}
          style={{ marginLeft: level * 24 }}
        >
          {/* Expand/Collapse Button */}
          {hasChildren ? (
            <button
              onClick={() => toggleExpand(node.id)}
              className="p-1 hover:bg-muted rounded"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          ) : (
            <span className="w-6" />
          )}

          {/* Task Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium truncate">{node.title}</span>
              <Badge
                variant="secondary"
                className={cn("text-xs", getStatusColor(node.status))}
              >
                {getStatusText(node.status)}
              </Badge>
            </div>
            {node.description && (
              <p className="text-sm text-muted-foreground truncate mt-0.5">
                {node.description}
              </p>
            )}
          </div>

          {/* Progress Edit */}
          <div className="flex items-center gap-4">
            {node.estimated_hours && (
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {node.estimated_hours}h
              </span>
            )}
            <TaskProgressEdit
              projectId={projectId}
              taskId={node.id}
              currentProgress={node.progress}
              onSuccess={() => refetch()}
            />
          </div>
        </div>

        {/* Children */}
        {hasChildren && isExpanded && (
          <div className="mt-1 space-y-1">
            {node.children!.map((child) => renderTaskNode(child, level + 1))}
          </div>
        )}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!taskTree || taskTree.children?.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>{t("projects.tasks.noSubtasks")}</p>
        <p className="text-sm mt-1">{t("projects.tasks.subtasksWillAppear")}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Root Task Info */}
      <div className="flex items-center justify-between p-3 bg-primary/5 rounded-lg border border-primary/20">
        <div>
          <h4 className="font-medium">{taskTree.title}</h4>
          <p className="text-sm text-muted-foreground">
            {taskTree.children?.length || 0} {t("projects.tasks.subtasks")}
          </p>
        </div>
        <Badge variant="outline" className="text-xs">
          {Math.round(taskTree.progress || 0)}%{" "}
          {t("projects.tasks.totalProgress")}
        </Badge>
      </div>

      {/* Subtasks List */}
      <div className="space-y-1 pt-2">
        {taskTree.children?.map((child) => renderTaskNode(child, 0))}
      </div>
    </div>
  )
}
