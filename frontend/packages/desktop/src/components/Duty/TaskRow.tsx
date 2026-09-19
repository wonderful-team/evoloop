import { memo } from "react"
import { Loader2, PauseCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@evoloop/shared/components/ui/badge"
import type { QueueTask } from "@/lib/tasksQueueApi"
import { RISK_STYLES } from "./styleConstants"

export const TaskRow = memo(function TaskRow({
  task,
  selected,
  onSelect,
  suspended,
  showProject,
  projectName,
}: {
  task: QueueTask
  selected: boolean
  onSelect: () => void
  suspended?: boolean
  showProject?: boolean
  projectName?: string
}) {
  const { t } = useTranslation()
  const isRunning = task.status === "in_progress"
  const isProposal = task.status === "proposed"
  const isWaiting = task.status === "waiting_acceptance"
  const isFailed = task.status === "failed"

  const riskCls = RISK_STYLES[task.risk_level ?? "T3"] ?? RISK_STYLES.T3

  const day = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`
  const hm = (d: Date) =>
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  const created = task.created_at ? new Date(task.created_at) : null
  const updated = task.updated_at ? new Date(task.updated_at) : null
  const ended =
    (task.status === "completed" || task.status === "failed") &&
    created &&
    updated
  const timeSpan = ended
    ? day(created!) === day(updated!)
      ? `${day(created!)} ${hm(created!)} → ${hm(updated!)}`
      : `${day(created!)} ${hm(created!)} → ${day(updated!)} ${hm(updated!)}`
    : created
      ? `${day(created)} ${hm(created)}`
      : null

  return (
    <div
      onClick={onSelect}
      className={`group rounded-md p-3 cursor-pointer transition-colors ${
        selected ? "bg-primary/10" : "bg-muted/30 hover:bg-muted/60"
      } ${suspended
        ? "border-l-2 border-l-amber-500"
        : isRunning
          ? "border-l-2 border-l-primary"
          : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium truncate flex items-center gap-1.5">
            {suspended ? (
              <PauseCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
            ) : isRunning ? (
              <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" />
            ) : null}
            {isProposal && (
              <span className="shrink-0 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
                提案
              </span>
            )}
            {task.title}
          </div>
          {task.description && (
            <div className="text-[11px] text-muted-foreground line-clamp-1 mt-1">
              {task.description}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {task.risk_level && (
            <Badge className={`h-4.5 px-1.5 text-[10px] font-mono ${riskCls}`}>
              {task.risk_level}
            </Badge>
          )}
          {task.type === "recurring" && (
            <Badge
              variant="outline"
              className="h-4 px-1.5 text-[9px] tracking-wide"
            >
              {t("dutyBoard.recurring")}
            </Badge>
          )}
        </div>
      </div>

      <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground font-mono whitespace-nowrap overflow-hidden">
        {timeSpan && <span className="shrink-0">{timeSpan}</span>}
        {showProject && task.project_id != null && task.project_id > 0 && (
          <span className="text-primary/70 min-w-0 truncate">
            {projectName ?? `#${task.project_id}`}
          </span>
        )}
        {task.category && (
          <span className="min-w-0 truncate">{task.category}</span>
        )}
        {task.priority && task.priority !== "medium" && (
          <Badge variant="outline" className="h-4 px-1 text-[9px] shrink-0">
            {task.priority}
          </Badge>
        )}
        {isWaiting && (
          <span className="text-amber-600 dark:text-amber-400 font-sans font-medium shrink-0">
            待验收·右侧处理
          </span>
        )}
        {isFailed && (
          <span className="text-destructive font-sans shrink-0">失败</span>
        )}
        <span className="flex-1" />
        <span className="shrink-0 opacity-0 group-hover:opacity-60 transition-opacity">
          查看 →
        </span>
      </div>
    </div>
  )
})