import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { BadgeCheck, MessageSquareX } from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"

export function ProposalCard({
  task,
  sourceTask,
  onChanged,
  onConfirmed,
}: {
  task: QueueTask
  sourceTask?: QueueTask | null
  onChanged: () => void | Promise<void>
  onConfirmed: () => void | Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState("")

  async function confirm() {
    setBusy(true)
    try {
      await TasksQueueApi.confirm(task.id)
      await onChanged()
      await onConfirmed()
    } finally {
      setBusy(false)
    }
  }
  async function reject() {
    if (!feedback.trim()) return
    setBusy(true)
    try {
      await TasksQueueApi.reject(task.id, feedback)
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg bg-violet-500/5 p-3">
      <div className="flex items-center gap-2">
        <span className="shrink-0 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[10px] font-bold px-2 py-0.5">
          待确认提案
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-muted-foreground">
          {task.category} · {task.risk_level}
        </span>
      </div>

      <div className="mt-2 text-sm font-semibold">{task.title}</div>

      {sourceTask && (
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          产生于任务执行：{sourceTask.title}
        </div>
      )}

      {/* full proposal rationale */}
      <div className="mt-2 rounded-md bg-background/70 p-2.5">
        <div className="text-[10px] font-medium text-muted-foreground mb-1">
          提案说明 / 依据
        </div>
        <div className="text-xs whitespace-pre-wrap break-words leading-relaxed">
          {task.description || "（无说明）"}
        </div>
      </div>

      {!rejectOpen ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            size="sm"
            className="h-7 gap-1 px-3 text-xs"
            disabled={busy}
            onClick={confirm}
          >
            <BadgeCheck className="h-3.5 w-3.5" />
            确认，加入队列
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-3 text-xs"
            disabled={busy}
            onClick={() => setRejectOpen(true)}
          >
            <MessageSquareX className="h-3.5 w-3.5" />
            驳回
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-1.5">
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
              className="h-7 px-3 text-xs"
              disabled={!feedback.trim() || busy}
              onClick={reject}
            >
              确认驳回
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-3 text-xs"
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
  )
}


export function InlineProposal({
  proposal,
  onChanged,
}: {
  proposal: QueueTask
  onChanged: () => void | Promise<void>
}) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState("")
  const pending = proposal.status === "proposed"

  async function confirm() {
    setBusy(true)
    try {
      await TasksQueueApi.confirm(proposal.id)
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      await onChanged()
    } finally {
      setBusy(false)
    }
  }
  async function reject() {
    if (!feedback.trim()) return
    setBusy(true)
    try {
      await TasksQueueApi.reject(proposal.id, feedback)
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-md bg-violet-500/5 p-2.5">
      <div className="flex items-center gap-1.5">
        <span className="shrink-0 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
          产生提案
        </span>
        <span className="text-xs font-semibold truncate">{proposal.title}</span>
        <span
          className={`shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
            pending
              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
              : proposal.status === "completed"
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-muted text-muted-foreground"
          }`}
        >
          {pending
            ? "待确认"
            : proposal.status === "pending"
              ? "已入队"
              : proposal.status === "completed"
                ? "已完成"
                : proposal.status}
        </span>
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground whitespace-pre-wrap break-words leading-relaxed">
        {proposal.description}
      </div>
      {pending && (
        <div className="mt-2">
          {!rejectOpen ? (
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                className="h-6 gap-1 px-2 text-[11px]"
                disabled={busy}
                onClick={confirm}
              >
                <BadgeCheck className="h-3 w-3" />
                确认，加入队列
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-6 gap-1 px-2 text-[11px]"
                disabled={busy}
                onClick={() => setRejectOpen(true)}
              >
                驳回
              </Button>
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
                  disabled={!feedback.trim() || busy}
                  onClick={reject}
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