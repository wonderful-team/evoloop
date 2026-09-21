import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useNavigate } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import {
  TaskProposalCard as SharedTaskProposalCard,
  type ProposalScheduleParams,
} from "@evoloop/shared"

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
  const [status, setStatus] = useState(initialStatus)

  const title = typeof input.title === "string" ? input.title : "未命名任务"
  const description =
    typeof input.description === "string" ? input.description : ""
  const priority = typeof input.priority === "string" ? input.priority : "medium"
  const riskLevel = typeof input.risk_level === "string" ? input.risk_level : null
  const source = typeof input.source === "string" ? input.source : "agent"
  const initialType = input.task_type === "recurring" ? "recurring" : "once"
  const initialDueAt = typeof input.due_at === "string" ? input.due_at : null
  const initialTriggerSpec =
    typeof input.trigger_spec === "string" ? input.trigger_spec : ""

  async function refreshDuty() {
    await queryClient.invalidateQueries({ queryKey: ["dutyQueue"] })
    await queryClient.invalidateQueries({ queryKey: ["dutyDashboard"] })
  }

  async function handleConfirm(params?: ProposalScheduleParams) {
    if (!taskId) return
    const taskType = params?.taskType || initialType
    const scheduleMode = params?.scheduleMode || "now"
    const dueAt = params?.dueAt || ""
    const triggerSpec = params?.triggerSpec || ""

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
      throw error
    }
  }

  async function handleCancel() {
    if (!taskId) return
    try {
      const cancelled = await TasksQueueApi.update(taskId, { status: "cancelled" })
      setStatus(cancelled.status)
      await refreshDuty()
      toast.success("任务提案已取消")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "任务取消失败")
      throw error
    }
  }

  return (
    <SharedTaskProposalCard
      id={taskId}
      title={title}
      description={description}
      status={status}
      priority={priority}
      riskLevel={riskLevel}
      source={source}
      error={typeof result?.error === "string" ? result.error : null}
      variant="default"
      allowScheduleEdit={true}
      initialTaskType={initialType}
      initialDueAt={initialDueAt}
      initialTriggerSpec={initialTriggerSpec}
      requireFeedbackOnReject={false}
      onConfirm={handleConfirm}
      onReject={handleCancel}
      onOpenDuty={() => navigate({ to: "/duty-autonomous" })}
    />
  )
}
