import { useEffect, useState } from "react"

import { ConversationsService, AgentService } from "@/client"
import { useQueryClient } from "@tanstack/react-query"
import { Bot } from "lucide-react"
import type { QueueTask } from "@/lib/tasksQueueApi"
import { HumanRequestCard as SharedHumanRequestCard } from "@evoloop/shared"

/**
 * 监察评审进度卡（渲染在执行时间线下方）。
 *
 * 评审 run 生活在原对话（origin thread），本卡轮询该对话的最新进展，
 * 让看板上的"评审中"不再是干等：
 * - 评审者最新发言（核验动作/结论行）实时摘要
 * - 评审者的审批请求直接在看板处理（复用 HitlApprovalCard）
 * 结论仍由 TaskReviewSubscriber 驱动状态机，本卡只做展示。
 */
export function ReviewProgressCard({
  task,
  hitlItems,
  onChanged,
}: {
  task: QueueTask
  hitlItems: Array<{
    request_id: string
    type: string
    description?: string
    context?: string | null
    options?: string[]
    thread_id?: string | null
    task_id?: string | null
  }>
  onChanged: () => void
}) {
  const origin = task.origin_thread_id
  const [latest, setLatest] = useState<string>("")
  const [tick, setTick] = useState(0)

  // 5s 轮询原对话最新 assistant 发言（评审者的动态）
  useEffect(() => {
    if (!origin) return
    let alive = true
    const iv = setInterval(async () => {
      try {
        const res = (await ConversationsService.getConversationMessages({
          threadId: origin,
          limit: 3,
          includeToolCalls: true,
        })) as { data?: Array<{ role?: string; category?: string; content?: string }> }
        if (!alive) return
        msgs = (res.data ?? []).filter(
          (m) => m.category === "assistant_response" || m.category === "assistant_tool_call",
        )
        const last = msgs[msgs.length - 1]
        setLatest((last?.content || "").trim())
        setTick((x) => x + 1)
      } catch {
        /* 后端不可达时静默 */
      }
    }, 5000)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [origin])
  void tick

  const waitingApproval = hitlItems.length > 0

  const qc = useQueryClient()

  const handleRespond = async (
    threadId: string,
    response: string,
    grantMode?: "once" | "always" | "dir" | "default",
  ) => {
    await AgentService.resumeChat({
      requestBody: {
        thread_id: threadId,
        user_input: response,
        grant_mode: grantMode ?? "once",
      },
    })
    onChanged()
    void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
    void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    void qc.invalidateQueries({ queryKey: ["dutyExec"] })
  }

  return (
    <div className="mt-2 rounded-lg border border-violet-400/40 bg-violet-500/[0.06] px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-2 text-xs">
        <Bot className="h-4 w-4 text-violet-500 shrink-0" />
        <span className="font-semibold text-violet-600 dark:text-violet-400">
          监察评审进行中
        </span>
        <span className="text-[10px] text-muted-foreground">
          执行者已交卷 · 原对话 Agent 以用户立场核验
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-muted-foreground/60">
          {origin ?? ""}
        </span>
      </div>

      {waitingApproval && (
        <div className="space-y-2">
          {hitlItems.map((h) => {
            const threadId = h.thread_id ?? origin ?? ""
            return (
              <SharedHumanRequestCard
                key={h.request_id}
                request={{
                  id: h.request_id,
                  type: h.type,
                  prompt: h.description ?? "",
                  options: h.options ?? ([] as string[]),
                  context: h.context ?? null,
                  thread_id: threadId,
                }}
                onRespond={(res, mode) => handleRespond(threadId, res, mode)}
              />
            )
          })}
        </div>
      )}

      {!waitingApproval && latest && (
        <div className="text-[11px] text-muted-foreground border-l-2 border-violet-400/40 pl-2 py-0.5 line-clamp-3 leading-relaxed">
          {latest.replace(/\n+/g, " ").slice(-400)}
        </div>
      )}

      {!waitingApproval && !latest && (
        <div className="text-[11px] text-muted-foreground/70">
          评审者正在核验（对照最初意图逐条核对、关键数字交叉验证）……
        </div>
      )}
    </div>
  )
}

let msgs: Array<{ role?: string; category?: string; content?: string }> = []
