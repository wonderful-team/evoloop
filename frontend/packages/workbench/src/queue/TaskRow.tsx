import { memo } from "react"
import { useNavigate } from "@tanstack/react-router"
import { ArrowRight, Bell, Bot, Loader2, PauseCircle, Scale } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@evoloop/shared/components/ui/badge"
import type { QueueTask } from "@/lib/tasksQueueApi"
import { RISK_STYLES } from "../core/styleConstants"

export const TaskRow = memo(function TaskRow({
  task,
  selected,
  onSelect,
  onDoubleClick,
  suspended,
  showProject,
  projectName,
}: {
  task: QueueTask
  selected: boolean
  onSelect: () => void
  onDoubleClick?: () => void
  suspended?: boolean
  showProject?: boolean
  projectName?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isRunning = task.status === "in_progress"
  const isProposal = task.status === "proposed"
  const isWaiting = task.status === "waiting_acceptance"
  const isFailed = task.status === "failed"
  const isReviewing = isWaiting && !!task.review_pending
  const isArbitration = isFailed && !!task.escalated

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
      id={`duty-task-row-${task.id}`}
      onClick={onSelect}
      onDoubleClick={onDoubleClick}
      className={`group rounded-md p-2.5 cursor-pointer transition-all space-y-1.5 border ${
        selected
          ? "bg-primary/10 border-primary/40 shadow-xs"
          : "bg-card/40 border-border/40 hover:bg-card/80 hover:border-border/80 shadow-2xs"
      } ${suspended
        ? "border-l-2 border-l-amber-500"
        : isRunning
          ? "border-l-2 border-l-primary"
          : isReviewing
            ? "border-l-2 border-l-violet-500"
            : isWaiting
              ? "border-l-2 border-l-amber-400"
              : isFailed
                ? "border-l-2 border-l-destructive/70"
                : ""}`}
    >
      {/* 头：编号 + 徽标 */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10px] text-muted-foreground/60">
          {task.task_no != null ? `#T-${task.task_no}` : "\u00a0"}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {isProposal && (
            <span className="rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
              提案
            </span>
          )}
          {task.type === "recurring" && (
            <Badge variant="outline" className="h-4 px-1.5 text-[9px] tracking-wide">
              {t("dutyBoard.recurring")}
            </Badge>
          )}
          {task.risk_level && (
            <Badge className={`h-4.5 px-1.5 text-[10px] font-mono ${riskCls}`}>
              {task.risk_level}
            </Badge>
          )}
        </div>
      </div>

      {/* 标题 */}
      <div className="text-[13px] font-medium leading-snug break-words flex items-start gap-1.5">
        {suspended ? (
          <PauseCircle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
        ) : isRunning ? (
          <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0 mt-0.5" />
        ) : null}
        <span className="min-w-0">{task.title}</span>
      </div>

      {/* 描述放宽到两行 */}
      {task.description && (
        <div className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
          {task.description}
        </div>
      )}

      {/* 底部：归属与状态，各占一行，宽松 */}
      <div className="pt-1.5 border-t border-border/50 space-y-1">
        {(task.subtasks_count ?? 0) > 0 && (
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-primary/90 bg-primary/5 rounded px-1.5 py-0.5">
            <span className="text-[11px]">⛓</span>
            <span>
              {task.subtasks_completed != null && task.subtasks_completed > 0
                ? `${task.subtasks_completed}/${task.subtasks_count} 个子步骤已完成`
                : `含 ${task.subtasks_count} 个执行子步骤`}
            </span>
          </div>
        )}
        {(task.dependencies?.length ?? 0) > 0 && !(task.subtasks_count && task.subtasks_count > 0) && (
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground/80">
            <ArrowRight className="h-3 w-3 shrink-0 rotate-90" />
            依赖 {task.dependencies!.length} 项 · 上游完成后自动推进
          </div>
        )}
        <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-muted-foreground whitespace-nowrap">
          <span className="shrink-0">{timeSpan}</span>
          {isReviewing ? (
            <span className="text-violet-500 font-sans font-medium shrink-0 flex items-center gap-1">
              <Bot className="h-3 w-3" />
              评审中
            </span>
          ) : isWaiting ? (
            <span className="text-amber-500 font-sans font-medium shrink-0 flex items-center gap-1">
              <Bell className="h-3 w-3" />
              待人工验收
            </span>
          ) : isArbitration ? (
            <button
              type="button"
              className="text-amber-500 font-sans font-medium shrink-0 flex items-center gap-1 hover:underline underline-offset-2"
              onClick={(e) => {
                e.stopPropagation()
                if (task.origin_thread_id) {
                  navigate({
                    to: "/chat",
                    search: { thread_id: task.origin_thread_id as string },
                  })
                }
              }}
            >
              <Scale className="h-3 w-3" />
              转人工仲裁·去处理
              <ArrowRight className="h-3 w-3" />
            </button>
          ) : isFailed ? (
            <span className="text-destructive font-sans shrink-0">失败</span>
          ) : (
            <span className="shrink-0 opacity-0 group-hover:opacity-60 transition-opacity text-[10px]">
              查看 →
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono whitespace-nowrap overflow-hidden">
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
        </div>
      </div>
    </div>
  )
})