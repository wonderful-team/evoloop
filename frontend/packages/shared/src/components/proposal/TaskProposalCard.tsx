import * as React from "react"
import {Badge} from "../ui/badge"
import {Button} from "../ui/button"
import {Input} from "../ui/input"
import {MarkdownText} from "../markdown/MarkdownText"
import {BadgeCheck, CalendarClock, CheckCircle2, ExternalLink, MessageSquareX, XCircle,} from "lucide-react"
import type {ProposalScheduleParams, TaskProposalCardProps} from "./types"

function toDatetimeLocal(value?: string | null): string {
  if (!value) return ""
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

export function TaskProposalCard({
  id,
  title,
  description,
  status = "proposed",
  priority = "medium",
  riskLevel,
  category,
  source = "agent",
  sourceTaskTitle,
  error,
  variant = "default",
  allowScheduleEdit = false,
  initialTaskType = "once",
  initialDueAt,
  initialTriggerSpec = "",
  requireFeedbackOnReject = false,
  onConfirm,
  onReject,
  onOpenDuty,
}: TaskProposalCardProps) {
  const displayTitle = title || "未命名任务"
  const [taskType, setTaskType] = React.useState<"once" | "recurring">(
    initialTaskType,
  )
  const [scheduleMode, setScheduleMode] = React.useState<"now" | "scheduled">(
    initialDueAt ? "scheduled" : "now",
  )
  const [dueAt, setDueAt] = React.useState(() => toDatetimeLocal(initialDueAt))
  const [triggerSpec, setTriggerSpec] = React.useState(
    initialTriggerSpec || "",
  )
  const [busy, setBusy] = React.useState<"confirm" | "reject" | null>(null)
  const [rejectOpen, setRejectOpen] = React.useState(false)
  const [feedback, setFeedback] = React.useState("")

  const isProposed = status === "proposed"

  const handleConfirm = async () => {
    if (!onConfirm || busy) return
    setBusy("confirm")
    try {
      const params: ProposalScheduleParams = {
        taskType,
        scheduleMode,
        dueAt,
        triggerSpec,
      }
      await onConfirm(params)
    } finally {
      setBusy(null)
    }
  }

  const handleReject = async () => {
    if (!onReject || busy) return
    if (requireFeedbackOnReject && !feedback.trim()) return
    setBusy("reject")
    try {
      await onReject(feedback.trim())
      setRejectOpen(false)
      setFeedback("")
    } finally {
      setBusy(null)
    }
  }

  // --- Inline Variant ---
  if (variant === "inline") {
    return (
      <div
        className="rounded-md bg-violet-500/5 p-2.5"
        data-task-id={id || undefined}
      >
        <div className="flex items-center gap-1.5">
          <span className="shrink-0 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
            产生提案
          </span>
          <span className="text-xs font-semibold truncate">{displayTitle}</span>
          <span
            className={`shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
              isProposed
                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : status === "completed"
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "bg-muted text-muted-foreground"
            }`}
          >
            {isProposed
              ? "待确认"
              : status === "pending"
                ? "已入队"
                : status === "completed"
                  ? "已完成"
                  : status}
          </span>
        </div>
        {description && (
          <div className="mt-1 text-[11px] text-muted-foreground break-words leading-relaxed">
            <MarkdownText content={description} />
          </div>
        )}
        {isProposed && (
          <div className="mt-2">
            {!rejectOpen ? (
              <div className="flex items-center gap-1.5">
                <Button
                  size="sm"
                  className="h-6 gap-1 px-2 text-[11px]"
                  disabled={busy !== null}
                  onClick={handleConfirm}
                >
                  <BadgeCheck className="h-3 w-3" />
                  确认，加入队列
                </Button>
                {onReject && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 gap-1 px-2 text-[11px]"
                    disabled={busy !== null}
                    onClick={() => {
                      if (requireFeedbackOnReject) {
                        setRejectOpen(true)
                      } else {
                        handleReject()
                      }
                    }}
                  >
                    驳回
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                <textarea
                  className="w-full min-h-[56px] rounded-md border bg-transparent p-2 text-xs"
                  placeholder="驳回原因（必填，将反馈给 Agent 修正提案）"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="destructive"
                    className="h-6 px-2 text-[11px]"
                    disabled={!feedback.trim() || busy !== null}
                    onClick={handleReject}
                  >
                    确认驳回
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => {
                      setRejectOpen(false)
                      setFeedback("")
                    }}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // --- Default (Standard / Card) Variant ---
  // 无框设计：外层无 border/shadow，仅 header 用 muted 底色分区；内容区靠
  // 间距分层（嵌套在节点页/聊天气泡内时避免框中框噪音）。
  return (
    <div
      className="my-3 w-full overflow-hidden rounded-xl bg-background"
      data-task-id={id || undefined}
    >
      <div className="flex items-start gap-3 bg-muted/40 px-4 py-3">
        <CalendarClock className="mt-0.5 h-4 w-4 text-primary" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide text-muted-foreground">
              {isProposed ? "待确认提案" : "任务提案"}
            </span>
            {status && (
              <Badge variant={isProposed ? "secondary" : "outline"}>
                {status}
              </Badge>
            )}
            {category && (
              <span className="font-mono text-[10px] text-muted-foreground ml-auto">
                {category} {riskLevel ? `· ${riskLevel}` : ""}
              </span>
            )}
          </div>
          <h4 className="mt-1 truncate text-sm font-semibold">{displayTitle}</h4>
          {sourceTaskTitle && (
            <div className="mt-1 text-[11px] text-muted-foreground">
              产生于任务执行：{sourceTaskTitle}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        {description && (
          <div className="rounded-lg bg-muted/20 p-3 text-sm break-words min-w-0 text-muted-foreground">
            <MarkdownText content={description} />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">
            {taskType === "once" ? "一次性" : "周期"}
          </Badge>
          {priority && <Badge variant="secondary">{priority}</Badge>}
          {riskLevel && !category && (
            <Badge variant="secondary">风险 {riskLevel}</Badge>
          )}
          {source && <Badge variant="secondary">来源 {source}</Badge>}
        </div>

        {isProposed ? (
          <div className="space-y-3">
            {allowScheduleEdit && (
              <>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={taskType === "once" ? "default" : "outline"}
                    onClick={() => setTaskType("once")}
                  >
                    一次性
                  </Button>
                  <Button
                    size="sm"
                    variant={taskType === "recurring" ? "default" : "outline"}
                    onClick={() => setTaskType("recurring")}
                  >
                    周期
                  </Button>
                </div>

                {taskType === "once" ? (
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant={
                          scheduleMode === "now" ? "default" : "outline"
                        }
                        onClick={() => setScheduleMode("now")}
                      >
                        立即执行
                      </Button>
                      <Button
                        size="sm"
                        variant={
                          scheduleMode === "scheduled" ? "default" : "outline"
                        }
                        onClick={() => setScheduleMode("scheduled")}
                      >
                        定时执行
                      </Button>
                    </div>
                    {scheduleMode === "scheduled" && (
                      <Input
                        type="datetime-local"
                        value={dueAt}
                        onChange={(event) => setDueAt(event.target.value)}
                      />
                    )}
                  </div>
                ) : (
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">
                      周期规则（cron 或 interval:秒）
                    </label>
                    <Input
                      value={triggerSpec}
                      placeholder="0 9 * * * 或 interval:3600"
                      onChange={(event) => setTriggerSpec(event.target.value)}
                    />
                  </div>
                )}
              </>
            )}

            {!rejectOpen ? (
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={handleConfirm}
                  disabled={busy !== null}
                >
                  <CheckCircle2 className="mr-1 h-4 w-4" />
                  {allowScheduleEdit ? "确认并执行" : "确认，加入队列"}
                </Button>
                {onReject && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      if (requireFeedbackOnReject) {
                        setRejectOpen(true)
                      } else {
                        handleReject()
                      }
                    }}
                    disabled={busy !== null}
                  >
                    {requireFeedbackOnReject ? (
                      <MessageSquareX className="mr-1 h-4 w-4" />
                    ) : (
                      <XCircle className="mr-1 h-4 w-4" />
                    )}
                    {requireFeedbackOnReject ? "驳回" : "取消"}
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <textarea
                  className="w-full min-h-[64px] rounded-md border bg-transparent p-2 text-xs"
                  placeholder="驳回原因（必填，将反馈给 Agent 修正提案）"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    className="h-8 px-3 text-xs"
                    disabled={!feedback.trim() || busy !== null}
                    onClick={handleReject}
                  >
                    确认驳回
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 px-3 text-xs"
                    onClick={() => {
                      setRejectOpen(false)
                      setFeedback("")
                    }}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2.5 text-xs">
            <span className="text-muted-foreground">
              {status === "pending" && "已进入值守队列"}
              {status === "in_progress" && "Agent 正在执行"}
              {status === "self_checked" && "已自检，等待验收"}
              {status === "waiting_acceptance" && "等待人工验收"}
              {status === "completed" && "任务已完成"}
              {status === "cancelled" && "任务已取消"}
              {status === "failed" && "任务失败"}
              {!status && error ? String(error) : ""}
            </span>
            {onOpenDuty && (
              <Button size="sm" variant="ghost" onClick={onOpenDuty}>
                <ExternalLink className="mr-1 h-3.5 w-3.5" />
                打开值守
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
