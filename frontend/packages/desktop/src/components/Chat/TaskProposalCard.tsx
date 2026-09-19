import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { CalendarClock, CheckCircle2, ExternalLink, XCircle } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useNavigate } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"

import { TasksQueueApi } from "@/lib/tasksQueueApi"

interface ProposalMessage {
  id: string | number
  content: string
  input?: Record<string, unknown>
}

function parseOutput(content: string) {
  try {
    return JSON.parse(content) as Record<string, unknown>
  } catch {
    return null
  }
}

function toDatetimeLocal(value?: string | null) {
  if (!value) return ""
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

function toIso(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "" : date.toISOString()
}

export function TaskProposalCard({ msg }: { msg: ProposalMessage }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const input = msg.input || {}
  const result = useMemo(() => parseOutput(msg.content), [msg.content])

  const taskId = typeof result?.id === "string" ? result.id : null
  const initialStatus = typeof result?.status === "string" ? result.status : ""
  const initialType = input.task_type === "recurring" ? "recurring" : "once"
  const initialDueAt = typeof input.due_at === "string" ? input.due_at : null

  const [taskType, setTaskType] = useState<"once" | "recurring">(initialType)
  const [scheduleMode, setScheduleMode] = useState<"now" | "scheduled">(
    initialDueAt ? "scheduled" : "now",
  )
  const [dueAt, setDueAt] = useState(() => toDatetimeLocal(initialDueAt))
  const [triggerSpec, setTriggerSpec] = useState(
    typeof input.trigger_spec === "string" ? input.trigger_spec : "",
  )
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null)
  const [status, setStatus] = useState(initialStatus)

  const title = typeof input.title === "string" ? input.title : "未命名任务"
  const description =
    typeof input.description === "string" ? input.description : ""
  const priority = typeof input.priority === "string" ? input.priority : "medium"
  const riskLevel = typeof input.risk_level === "string" ? input.risk_level : null
  const source = typeof input.source === "string" ? input.source : "agent"

  async function refreshDuty() {
    await queryClient.invalidateQueries({ queryKey: ["dutyQueue"] })
    await queryClient.invalidateQueries({ queryKey: ["dutyDashboard"] })
  }

  async function confirm() {
    if (!taskId || busy) return
    setBusy("confirm")
    try {
      const body: Record<string, unknown> = { type: taskType }
      if (taskType === "once") {
        body.clear_trigger_spec = true
        if (scheduleMode === "scheduled") {
          const isoDueAt = toIso(dueAt)
          if (!isoDueAt) throw new Error("执行时间无效")
          body.due_at = isoDueAt
        } else {
          body.clear_due_at = true
        }
      } else {
        if (!triggerSpec.trim()) throw new Error("请填写周期规则")
        body.trigger_spec = triggerSpec.trim()
        body.clear_due_at = true
      }

      const updated = await TasksQueueApi.update(taskId, body)
      setStatus(updated.status)
      const confirmed = await TasksQueueApi.confirm(taskId)
      setStatus(confirmed.status)
      await refreshDuty()
      toast.success("任务已确认并进入值守队列")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "任务确认失败")
    } finally {
      setBusy(null)
    }
  }

  async function cancel() {
    if (!taskId || busy) return
    setBusy("cancel")
    try {
      const cancelled = await TasksQueueApi.update(taskId, { status: "cancelled" })
      setStatus(cancelled.status)
      await refreshDuty()
      toast.success("任务提案已取消")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "任务取消失败")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="my-3 w-full overflow-hidden rounded-xl border bg-background shadow-sm">
      <div className="flex items-start gap-3 border-b bg-muted/40 px-4 py-3">
        <CalendarClock className="mt-0.5 h-4 w-4 text-primary" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide text-muted-foreground">
              任务提案
            </span>
            {status && (
              <Badge variant={status === "proposed" ? "secondary" : "outline"}>
                {status}
              </Badge>
            )}
          </div>
          <h4 className="mt-1 truncate text-sm font-semibold">{title}</h4>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        {description && (
          <div className="rounded-lg border bg-muted/20 p-3 text-sm whitespace-pre-wrap text-muted-foreground">
            {description}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">{taskType === "once" ? "一次性" : "周期"}</Badge>
          <Badge variant="outline">{priority}</Badge>
          {riskLevel && <Badge variant="outline">风险 {riskLevel}</Badge>}
          <Badge variant="outline">来源 {source}</Badge>
        </div>

        {status === "proposed" && taskId ? (
          <div className="space-y-3 rounded-lg border p-3">
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
                    variant={scheduleMode === "now" ? "default" : "outline"}
                    onClick={() => setScheduleMode("now")}
                  >
                    立即执行
                  </Button>
                  <Button
                    size="sm"
                    variant={scheduleMode === "scheduled" ? "default" : "outline"}
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

            <div className="flex gap-2">
              <Button className="flex-1" onClick={confirm} disabled={busy !== null}>
                <CheckCircle2 className="mr-1 h-4 w-4" />
                确认并执行
              </Button>
              <Button
                variant="outline"
                onClick={cancel}
                disabled={busy !== null}
              >
                <XCircle className="mr-1 h-4 w-4" />
                取消
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 rounded-lg border p-3 text-xs">
            <span className="text-muted-foreground">
              {status === "pending" && "已进入值守队列"}
              {status === "in_progress" && "Agent 正在执行"}
              {status === "self_checked" && "已自检，等待验收"}
              {status === "waiting_acceptance" && "等待人工验收"}
              {status === "completed" && "任务已完成"}
              {status === "cancelled" && "任务已取消"}
              {status === "failed" && "任务失败"}
              {!status && result?.error ? String(result.error) : ""}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => navigate({ to: "/duty-autonomous" })}
            >
              <ExternalLink className="mr-1 h-3.5 w-3.5" />
              打开值守
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
