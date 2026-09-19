import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { motion } from "framer-motion"
import { OpenAPI } from "@/client"
import { MessageContent } from "@/components/Chat/MessageContent"
import { useNavigate } from "@tanstack/react-router"
import {
  AlertTriangle,
  BadgeCheck,
  PauseCircle,
  ExternalLink,
  ListTodo,
  Loader2,
  Package,
  Square,
  Wrench,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { ConversationsService, PlanningService } from "@/client"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"
import {
  classify,
  summarizeOutput,
  textOf,
  toolNameOf,
  type Msg,
  type NodeKind,
} from "@/components/Duty/parse"
import { DEMO } from "@/components/Duty/demoData"
import { ResultCard, AttachmentStrip } from "./ResultCard"
import { ProposalCard, InlineProposal } from "./ProposalCards"
import { HitlApprovalCard, hitlRequestFromMsg } from "./HitlApprovalCard"
import { ReviewProgressCard } from "./ReviewProgressCard"
import { PendingTaskBrief } from "./PendingTaskBrief"
import type { Attachment, ArtifactView, PlanStep } from "./types"
import {
  getDemoMessages,
  getDemoPlan,
} from "@/components/Duty/demoRuntime"





const NODE_STYLE: Record<
  NodeKind,
  { dot: string; label: string; labelCls: string }
> = {
  tool: {
    dot: "bg-sky-500",
    label: "工具",
    labelCls: "text-sky-600 dark:text-sky-400 font-mono",
  },
  think: {
    dot: "bg-muted-foreground/40",
    label: "思考",
    labelCls: "text-muted-foreground",
  },
  artifact: {
    dot: "bg-emerald-500",
    label: "产出",
    labelCls: "text-emerald-600 dark:text-emerald-400",
  },
  error: {
    dot: "bg-destructive",
    label: "异常",
    labelCls: "text-destructive",
  },
  hitl: {
    dot: "bg-amber-500",
    label: "等待人工",
    labelCls: "text-amber-600 dark:text-amber-400",
  },
  instruction: {
    dot: "bg-primary/70",
    label: "任务指令",
    labelCls: "text-primary",
  },
}

/** Execution workbench: NOW card + timeline + artifacts/cost strip. */
export function ExecutionPanel({
  task,
  runTokens,
  sourceTask,
  relatedProposals,
  hitlPending,
  onChanged,
  onConfirmed,
  onVerdictDone,
}: {
  task: QueueTask
  runTokens?: number | null
  sourceTask?: QueueTask | null
  relatedProposals?: QueueTask[]
  hitlPending?: {
    request_id: string
    thread_id: string
    type: string
    description: string
    context: string | null
    options: string[]
    task_id?: string | null
  }[]
  onChanged: () => void | Promise<void>
  onConfirmed: () => void | Promise<void>
  onVerdictDone?: (landInTab: "done" | "active") => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const threadId = task.last_thread_id

  const { data, isLoading } = useQuery({
    queryKey: ["dutyExec", threadId],
    queryFn: async () =>
      DEMO
        ? ({
            messages: getDemoMessages(threadId).messages,
          } as unknown as Awaited<
            ReturnType<typeof ConversationsService.getConversationMessages>
          >)
        : await ConversationsService.getConversationMessages({
            threadId: threadId as string,
            limit: 40,
            includeToolCalls: true,
          }),
    enabled: DEMO || !!threadId,
  })

  const planQ = useQuery({
    queryKey: ["dutyPlan", threadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(threadId) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: threadId as string }),
    enabled: DEMO || !!threadId,
  })

  const body = data as unknown as { data?: Msg[]; messages?: Msg[] } | null
  const rawMsgs: Msg[] = body?.data ?? body?.messages ?? []
  // API returns newest-first; timeline renders oldest→newest, keep latest 40
  const msgs: Msg[] = [...rawMsgs].slice(0, 40).reverse()
  const planBody = planQ.data as unknown as {
    plan?: { steps?: PlanStep[] }
  } | null
  const planSteps = planBody?.plan?.steps ?? []
  const isRunning = task.status === "in_progress"
  const hasHitl = (hitlPending ?? []).length > 0
  const isReviewing =
    task.status === "waiting_acceptance" && !!task.review_pending
  const isTerminal = ["waiting_acceptance", "completed", "failed"].includes(
    task.status,
  )
  const finalMsg =
    [...msgs].reverse().find((m) => m.category === "assistant_response") ??
    [...msgs]
      .reverse()
      .find((m) => (m.role === "ai" || m.role === "assistant") && !toolNameOf(m))
  const finalText = finalMsg ? textOf(finalMsg).slice(0, 2500) : ""

  const isProposal = task.status === "proposed"

  // reset expanded nodes when switching tasks
  useEffect(() => {
    setExpanded(new Set())
  }, [task.id])

  // thread-level SSE: message landed → refresh timeline & plan (no polling gap)
  useEffect(() => {
    if (DEMO || !threadId) return
    const source = new EventSource(
      `${OpenAPI.BASE}/api/v1/stream/thread/${threadId}`,
      { withCredentials: true },
    )
    source.addEventListener("thread_updated", () => {
      void qc.invalidateQueries({ queryKey: ["dutyExec", threadId] })
      void qc.invalidateQueries({ queryKey: ["dutyPlan", threadId] })
    })
    return () => source.close()
  }, [DEMO, threadId, qc])

  // follow new timeline nodes as they arrive (hooks must be unconditional)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [msgs.length])

  if (isProposal) {
    return (
      <div key={`prop-${task.id}`} className="animate-in fade-in slide-in-from-bottom-1 duration-300">
      <ProposalCard
        task={task}
        sourceTask={sourceTask}
        onChanged={onChanged}
        onConfirmed={onConfirmed}
      />
      </div>
    )
  }

  if (!threadId && !DEMO) {
    return (
      <div className="text-xs text-muted-foreground p-3">
        <PendingTaskBrief task={task} />
      </div>
    )
  }

  const steps = planSteps
  const doneSteps = steps.filter((s) => s.status === "completed").length
  const currentStep = steps.find((s) => s.status !== "completed")

  // last tool call (for NOW card "currently calling")
  const lastTool =
    [...msgs].reverse().find((m) => m.category === "assistant_tool_call") ??
    [...msgs].reverse().find((m) => m.role === "tool" && toolNameOf(m))

  const taskArtifacts: ArtifactView[] = (task.artifacts ?? []).map((artifact) => ({
    id: artifact.id,
    stage: artifact.stage,
    type: artifact.type,
    summary: artifact.summary,
    data: artifact.data,
  }))
  const artifacts: ArtifactView[] =
    taskArtifacts.length > 0
      ? taskArtifacts
      : msgs
          .filter((m) => classify(m) === "artifact")
          .slice(-3)
          .map((m) => ({ id: m.id, summary: textOf(m) }))

  const errors = msgs.filter((m) => classify(m) === "error").slice(-3)
  const toolCount = msgs.filter((m) => m.role === "tool").length

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground p-3">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> 加载执行过程…
      </div>
    )
  }

  async function cancelTask() {
    setBusy(true)
    try {
      await TasksQueueApi.update(task.id, { status: "cancelled" })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
    } finally {
      setBusy(false)
    }
  }

  function toggleExpand(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  return (
    <div className="space-y-3 min-h-full flex flex-col">
      {/* ── ① NOW / RESULT card ────────────────────────── */}
      {isTerminal && (
        <div key={`res-${task.id}`} className="sticky top-0 z-10 bg-background rounded-lg animate-in fade-in slide-in-from-bottom-1 duration-300">
        <ResultCard
          task={task}
          onVerdictDone={onVerdictDone}
          finalText={finalText}
          finalAttachments={(finalMsg?.attachments as Attachment[] | undefined) ?? []}
          artifacts={artifacts}
          threadId={threadId}
          onChanged={() => {
            qc.invalidateQueries({ queryKey: ["dutyQueue"] })
            qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
          }}
        />
        </div>
      )}
      {!isTerminal && (
      <div
        className={`shrink-0 sticky top-0 z-10 rounded-lg bg-background p-1`}
      >
        <div
          className={`rounded-lg p-3 ${
            isRunning ? "bg-primary/10" : "bg-muted/40"
          }`}
        >
        <div className="flex items-center gap-2">
          {isRunning && hasHitl ? (
            <PauseCircle className="h-4 w-4 text-amber-500 shrink-0" />
          ) : isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
          ) : (
            <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/30 shrink-0" />
          )}
          <span className="text-sm font-semibold truncate">{task.title}</span>
          <span className="flex-1" />
          {isRunning && (
            <span className="font-mono text-xs text-primary tabular-nums">
              RUNNING
            </span>
          )}
        </div>
        {task.description && (
          <div className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
            {task.description}
          </div>
        )}
        {steps.length > 0 && (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <div className="flex-1 h-1.5 rounded bg-muted/60 overflow-hidden">
              <div
                className="h-full bg-primary rounded transition-all duration-500"
                style={{
                  width: `${(doneSteps / steps.length) * 100}%`,
                }}
              />
            </div>
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">
              {doneSteps}/{steps.length}
            </span>
          </div>
        )}

        {currentStep?.title && (
          <div className="mt-1.5 text-xs text-muted-foreground">
            当前步骤：
            <span className="text-foreground font-medium">
              {currentStep.title}
            </span>
          </div>
        )}
        {isRunning && (
          <div className="mt-1 flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
            <Wrench className="h-3 w-3 shrink-0" />
            <span className="truncate">
              {lastTool
                ? `${toolNameOf(lastTool)}() 执行中`
                : "等待工具调用"}
            </span>
            <span className="inline-block w-1.5 h-3.5 bg-primary/80 animate-pulse shrink-0" />
          </div>
        )}
        {isRunning && runTokens != null && (
          <div className="mt-1 text-xs font-mono tabular-nums text-primary">
            本次燃耗 {runTokens.toLocaleString()} tokens
          </div>
        )}

        {/* control bar */}
        <div className="mt-2.5 flex items-center gap-1.5">
          {isRunning && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 gap-1 px-2 text-[11px] text-destructive hover:text-destructive"
              disabled={busy}
              onClick={cancelTask}
            >
              <Square className="h-3 w-3" />
              终止
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-6 gap-1 px-2 text-[11px] text-muted-foreground"
            onClick={() =>
              navigate({
                to: "/chat",
                search: { thread_id: threadId as string },
              })
            }
          >
            <ExternalLink className="h-3 w-3" />
            接管会话
          </Button>
        </div>
        </div>
      </div>
      )}

      {/* ── ② TIMELINE ─────────────────────────────────── */}
      {msgs.length === 0 && (
        <div className="text-xs text-muted-foreground p-2">暂无执行记录</div>
      )}
      {msgs.length > 0 && (
        <div className="relative pl-4 space-y-1">
          <span className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-border" />
          {msgs.map((m, i) => {
            const kind = classify(m)
            const style = NODE_STYLE[kind]
            const isOpen = expanded.has(i)
            const full = textOf(m)
            const preview = full.slice(0, 160)
            return (
              <div key={m.id || i} className="relative">
                <span
                  className={`absolute -left-4 top-1.5 h-2 w-2 rounded-full ${style.dot}`}
                />
                <div
                  className="rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/40 transition-colors"
                  onClick={() => toggleExpand(i)}
                >
                  <div className="flex items-center gap-1.5 text-[10px] mb-0.5">
                    {kind === "tool" && (
                      <Wrench className="h-2.5 w-2.5 text-sky-500" />
                    )}
                    {kind === "instruction" && (
                      <ListTodo className="h-2.5 w-2.5 text-primary" />
                    )}
                    {kind === "error" && (
                      <AlertTriangle className="h-2.5 w-2.5 text-destructive" />
                    )}
                    {kind === "artifact" && (
                      <Package className="h-2.5 w-2.5 text-emerald-500" />
                    )}
                    {kind === "hitl" && (
                      <BadgeCheck className="h-2.5 w-2.5 text-amber-500" />
                    )}
                    <span className={`font-medium ${style.labelCls}`}>
                      {kind === "tool"
                        ? `${toolNameOf(m)}()`
                        : style.label}
                    </span>
                    {!isOpen && full.length > 160 && (
                      <span className="text-muted-foreground/50">
                        展开全部 {full.length} 字
                      </span>
                    )}
                  </div>
                  {isOpen ? (
                    <div className="text-xs text-muted-foreground [&_pre]:bg-muted/60 [&_pre]:rounded-md [&_pre]:p-2 [&_pre]:text-[11px] [&_table]:my-1 [&_table]:text-[10px] [&_th]:px-1.5 [&_th]:py-0.5 [&_td]:px-1.5 [&_td]:py-0.5">
                      <MessageContent
                        content={
                          kind === "tool" || kind === "hitl"
                            ? "```json\n" + full.replace(/^```json\n|\n```$/g, "") + "\n```"
                            : full.slice(0, 2000)
                        }
                      />
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground line-clamp-2">
                      {kind === "tool" ? summarizeOutput(full) : preview}
                    </div>
                  )}
                  {((m.attachments as Attachment[] | undefined)?.length ?? 0) > 0 && (
                    <AttachmentStrip items={m.attachments as Attachment[]} />
                  )}
                  {kind === "hitl" &&
                    (() => {
                      const hitl = hitlRequestFromMsg(m, threadId ?? "")
                      return hitl ? (
                        <HitlApprovalCard
                          request={hitl.request}
                          onChanged={onChanged}
                        />
                      ) : null
                    })()}
                  {kind === "tool" && toolNameOf(m) === "create_proposal" && (
                    <div className="mt-2 space-y-2">
                      {(relatedProposals ?? []).map((pr) => (
                        <InlineProposal
                          key={pr.id}
                          proposal={pr}
                          onChanged={onChanged}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          {isReviewing && (
            <ReviewProgressCard
              task={task}
              hitlItems={(hitlPending ?? []).filter(
                (h) => h.thread_id === task.origin_thread_id,
              )}
              onChanged={onChanged}
            />
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {/* ── ③ issues / cost strip（固定底部，不随滚动） */}
      <div className="sticky bottom-0 -mx-3 -mb-3 mt-auto px-3 pb-3 pt-2 bg-background">
        {(hitlPending ?? []).length > 0 ? (
          <div className="space-y-2">
            {(hitlPending ?? []).map((h) => (
              <HitlApprovalCard
                key={h.request_id}
                request={{
                  id: h.request_id,
                  type: h.type,
                  prompt: h.description,
                  options: h.options ?? [],
                  context: h.context,
                  thread_id: h.thread_id,
                }}
                taskId={h.task_id ?? undefined}
                onChanged={onChanged}
              />
            ))}
          </div>
        ) : (
        <motion.div
          layout
          className="grid grid-cols-2 gap-2"
        >
          <div className="rounded-lg bg-muted/40 p-2 min-w-0">
            <div className="text-[10px] font-medium text-muted-foreground flex items-center gap-1 mb-1">
              <AlertTriangle
                className={`h-3 w-3 ${errors.length ? "text-destructive" : "text-muted-foreground/40"}`}
              />
              异常 {errors.length > 0 && `· ${errors.length}`}
            </div>
            {errors.length === 0 ? (
              <div className="text-[11px] text-muted-foreground/50">无</div>
            ) : (
              <div className="space-y-0.5">
                {errors.map((m, i) => (
                  <div
                    key={i}
                    className="text-[11px] text-destructive/80 truncate"
                  >
                    {textOf(m).slice(0, 40)}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="rounded-lg bg-muted/40 p-2 min-w-0">
            <div className="text-[10px] font-medium text-muted-foreground mb-1.5">
              消耗
            </div>
            <div className="flex items-center flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground tabular-nums">
              {[
                ["步骤", `${doneSteps}/${steps.length || "—"}`],
                ["消息", String(msgs.length)],
                ["工具", String(toolCount)],
                ["LLM", String(task.run?.llm_calls ?? 0)],
                [
                  "Tokens",
                  (
                    (task.run?.input_tokens ?? 0) +
                    (task.run?.output_tokens ?? 0)
                  ).toLocaleString(),
                ],
              ].map(([label, value]) => (
                <span key={label} className="whitespace-nowrap">
                  <span className="opacity-60">{label}</span>{" "}
                  <span className="text-foreground font-medium">{value}</span>
                </span>
              ))}
            </div>
          </div>
        </motion.div>
        )}
      </div>
    </div>
  )
}
