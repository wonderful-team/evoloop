import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { type Task, TaskPriority, TaskStatus } from "@/types/task"

const getStatusColor = (status: number) => {
  switch (status) {
    case TaskStatus.PENDING:
      return "bg-gray-200 text-gray-700"
    case TaskStatus.IN_PROGRESS:
      return "bg-blue-100 text-blue-700"
    case TaskStatus.COMPLETED:
      return "bg-green-100 text-green-700"
    default:
      return "bg-gray-100 text-gray-600"
  }
}

// ... existing helper functions (getStatusColor, etc.) can stay or be moved inside if they need t()
// Actually, getStatusLabel and getPriorityLabel return strings that should be translated.
// So I should move them inside or pass t to them.

export const getColumns = (t: TFunction): ColumnDef<Task>[] => [
  {
    accessorKey: "task_id",
    header: t("projects.tasks.columns.id"),
    cell: ({ row }) => (
      <span className="font-medium">#{row.getValue("task_id")}</span>
    ),
  },
  {
    accessorKey: "task_title",
    header: t("projects.tasks.columns.title"),
    cell: ({ row }) => {
      const task = row.original
      return (
        <div className="max-w-[400px]">
          <div className="font-medium truncate" title={task.task_title}>
            {task.task_title}
          </div>
          {task.task_desc && (
            <div
              className="text-xs text-muted-foreground break-all line-clamp-2"
              title={task.task_desc}
            >
              {task.task_desc}
            </div>
          )}
        </div>
      )
    },
  },
  {
    accessorKey: "match_score",
    header: t("projects.tasks.columns.aiScore"),
    cell: ({ row }) => {
      const score = row.original.match_score
      if (score === undefined) return null
      return (
        <Badge variant={score > 80 ? "default" : "secondary"}>{score}%</Badge>
      )
    },
  },
  {
    accessorKey: "priority",
    header: t("projects.tasks.columns.priority"),
    cell: ({ row }) => {
      const priority = row.getValue("priority") as number
      const labelKey =
        priority === TaskPriority.URGENT
          ? "urgent"
          : priority === TaskPriority.HIGH
            ? "high"
            : priority === TaskPriority.LOW
              ? "low"
              : "normal"
      return (
        <span className="text-sm text-muted-foreground">
          {t(`projects.tasks.priorityLabel.${labelKey}`)}
        </span>
      )
    },
  },
  {
    accessorKey: "status",
    header: t("projects.tasks.columns.status"),
    cell: ({ row }) => {
      const status = row.getValue("status") as number
      const labelKey =
        status === TaskStatus.PENDING
          ? "pending"
          : status === TaskStatus.IN_PROGRESS
            ? "inProgress"
            : status === TaskStatus.COMPLETED
              ? "completed"
              : "unknown"
      return (
        <Badge className={getStatusColor(status)} variant="outline">
          {t(`projects.tasks.statusLabel.${labelKey}`)}
        </Badge>
      )
    },
  },
  {
    accessorKey: "progress",
    header: t("projects.tasks.columns.progress"),
    cell: ({ row }) => {
      const progress = (row.getValue("progress") as number) || 0
      return (
        <div>
          <div className="w-[60px] bg-secondary h-2 rounded-full overflow-hidden">
            <div
              className="bg-primary h-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="text-xs text-muted-foreground mt-1">{progress}%</div>
        </div>
      )
    },
  },
]
