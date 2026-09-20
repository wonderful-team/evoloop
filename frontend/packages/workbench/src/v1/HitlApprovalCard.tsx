import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  Ban,
  CheckCircle2,
  MessageSquareX,
  XCircle,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { AgentService } from "@/client"
import { TasksQueueApi } from "@/lib/tasksQueueApi"
import { MessageContent } from "@/components/Chat/MessageContent"
import type { Msg } from "./parse"
import { textOf } from "./parse"

export interface HitlRequest {
  id: string
  type: string
  prompt: string
  options: string[]
  context: string | null
  thread_id: string
}

/** HITL approval card for the duty workbench — mirrors the chat page's
 *  HumanRequestCard buttons (取消/拒绝/仅本次/总是允许) over plain HTTP. */
export function HitlApprovalCard({
  request,
  taskId,
  onChanged,
}: {
  request: HitlRequest
  taskId?: string
  onChanged: () => void | Promise<void>
}) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  async function respond(response: string, grantMode?: "once" | "always" | "default") {
    setBusy(true)
    try {
      await AgentService.resumeChat({
        requestBody: {
          thread_id: request.thread_id,
          user_input: response,
          grant_mode: grantMode ?? "once",
        },
      })
      setDone(response)
      await onChanged()
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    setBusy(true)
    try {
      // 语义 = 叫停：停掉这个任务的 Agent 会话（不是继续跑）
      await AgentService.stopChat({
        requestBody: { thread_id: request.thread_id, message: "" },
      })
      await AgentService.cancelHitlRequest({
        requestBody: { thread_id: request.thread_id, reason: "操作员叫停" },
      })
      if (taskId) {
        await TasksQueueApi.update(taskId, { status: "cancelled" })
      }
      setDone("已停止")
      await onChanged()
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
      void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    } finally {
      setBusy(false)
    }
  }

  // context carries the structured detail lines (风险等级/操作/资源…)
  const details = (request.context ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)

  return (
    <div className="rounded-md p-3 bg-amber-500/5 border border-amber-500/30">
      {request.prompt && (
        <div className="text-xs font-semibold text-foreground border-l-2 border-amber-500/50 pl-2 py-0.5 mb-1.5">
          {request.prompt}
        </div>
      )}
      {/* detail lines — one per row (markdown single-newline would collapse) */}
      <div className="text-xs leading-relaxed text-muted-foreground space-y-0.5">
        {details.map((line, i) => (
          <div key={i} className="whitespace-pre-wrap break-words [&_strong]:font-semibold">
            <MessageContent content={line} />
          </div>
        ))}
      </div>

      {done ? (
        <div className="mt-2 text-[11px] text-muted-foreground flex items-center gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          已响应：{done}
        </div>
      ) : (
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 rounded-full px-4 text-xs font-bold text-muted-foreground"
            disabled={busy}
            onClick={cancel}
          >
            <Ban className="mr-1.5 h-3.5 w-3.5" />
            取消
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-full px-5 border-destructive/20 text-destructive hover:bg-destructive/5 font-bold text-xs"
            disabled={busy}
            onClick={() => respond("拒绝")}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5" />
            拒绝
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-full px-5 font-bold text-xs"
            disabled={busy}
            onClick={() => respond("批准", "once")}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            仅本次
          </Button>
          <Button
            size="sm"
            className="h-8 rounded-full px-5 font-bold text-xs"
            disabled={busy}
            onClick={() => respond("批准", "always")}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            总是允许
          </Button>
        </div>
      )}
    </div>
  )
}

/** message → card title + detail body (for inline timeline rendering) */
export function hitlRequestFromMsg(
  m: Msg,
  threadId: string,
): { request: HitlRequest; title: string } | null {
  try {
    const payload = JSON.parse(textOf(m)) as {
      id?: string
      type?: string
      prompt?: string
      context?: string
    }
    if (!payload.id) return null
    return {
      request: {
        id: payload.id,
        type: payload.type ?? "approval",
        prompt: payload.prompt ?? "",
        options: [],
        context: payload.context ?? null,
        thread_id: threadId,
      },
      title: payload.prompt ?? "",
    }
  } catch {
    return null
  }
}

export { MessageSquareX }
