import { AgentExecutionTimeline, type TraceNodeItem } from "@evoloop/shared"
import { Button } from "@evoloop/shared/components/ui/button"
import { linkifyText } from "@evoloop/shared/lib/linkify"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  Activity,
  BadgeCheck,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Package,
  PauseCircle,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { AgentService, ConversationsService, PlanningService } from "@/client"
import { MessageContent } from "@/components/Chat/MessageContent"
import { type QueueTask, TasksQueueApi } from "@/lib/tasksQueueApi"
import { DEMO } from "../core/demoData"
import { getDemoMessages, getDemoPlan } from "../core/demoRuntime"
import {
  classify,
  hitlRequestFromMsg,
  type Msg,
  textOf,
  toolNameOf,
} from "../core/parse"
import type { ArtifactView, Attachment, PlanStep } from "../core/types"
import { PendingTaskBrief } from "./PendingTaskBrief"
import { InlineProposal, ProposalCard } from "./ProposalCards"
import { AttachmentStrip, ResultCard } from "./ResultCard"
import { ReviewProgressCard } from "./ReviewProgressCard"

/** Execution workbench: NOW card + timeline + artifacts/cost strip. */
export interface DutyHitlPendingItem {
  request_id: string
  thread_id: string
  type: string
  description: string
  context: string | null
  options?: string[]
  task_id?: string | null
}

export function ExecutionPanel({
  task,
  runTokens,
  sourceTask,
  relatedProposals,
  hitlPending,
  hideNowCard = false,
  onChanged,
  onConfirmed,
  onVerdictDone,
}: {
  task: QueueTask
  runTokens?: number | null
  sourceTask?: QueueTask | null
  relatedProposals?: QueueTask[]
  hitlPending?: DutyHitlPendingItem[]
  hideNowCard?: boolean
  onChanged: () => void | Promise<void>
  onConfirmed: () => void | Promise<void>
  onVerdictDone?: (landInTab: "done" | "active") => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
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
        ? (getDemoPlan(threadId) as unknown as Awaited<
            ReturnType<typeof PlanningService.getPlan>
          >)
        : await PlanningService.getPlan({ threadId: threadId as string }),
    enabled: DEMO || !!threadId,
  })

  const body = data as unknown as { data?: Msg[]; messages?: Msg[] } | null
  const rawMsgs: Msg[] = body?.data ?? body?.messages ?? []

  // 严格按时间先后正序排列：第 1 步在最上方，最新步在最下方，严禁使用 .reverse()
  const msgs: Msg[] = useMemo(() => {
    const list = [...rawMsgs]
    list.sort((a, b) => {
      const seqA = (a as any).sequence_number ?? (a as any).seq ?? 0
      const seqB = (b as any).sequence_number ?? (b as any).seq ?? 0
      if (seqA !== seqB) return seqA - seqB
      const timeA = new Date(
        (a as any).created_at || (a as any).timestamp || 0,
      ).getTime()
      const timeB = new Date(
        (b as any).created_at || (b as any).timestamp || 0,
      ).getTime()
      return timeA - timeB
    })
    return list.slice(-50)
  }, [rawMsgs])

  const planBody = planQ.data as unknown as {
    plan?: { steps?: PlanStep[] }
  } | null
  const planSteps = planBody?.plan?.steps ?? []

  // SSE 独驱：thread_updated/hitl 事件 + onopen 重连对账，不设周期轮询
  const hitlQ = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
  })
  const allHitl: DutyHitlPendingItem[] = (hitlPending ??
    hitlQ.data?.items ??
    []) as DutyHitlPendingItem[]
  const taskHitl = useMemo<DutyHitlPendingItem[]>(() => {
    return allHitl.filter(
      (h) =>
        (task.id && h.task_id === task.id) ||
        (threadId && h.thread_id === threadId),
    )
  }, [allHitl, task.id, threadId])

  const isRunning = task.status === "in_progress"
  const hasHitl = taskHitl.length > 0
  const isReviewing =
    task.status === "waiting_acceptance" && !!task.review_pending
  const isTerminal = [
    "waiting_acceptance",
    "completed",
    "failed",
    "cancelled",
  ].includes(task.status)
  const finalMsg =
    [...msgs].reverse().find((m) => m.category === "assistant_response") ??
    [...msgs]
      .reverse()
      .find(
        (m) => (m.role === "ai" || m.role === "assistant") && !toolNameOf(m),
      )
  const finalText = finalMsg ? textOf(finalMsg) : ""

  const isProposal = task.status === "proposed"
  const hasResult = isTerminal && Boolean(finalText)

  // 🌟 Hooks 顶层无条件声明：严格遵循 React Rules of Hooks
  const [activeTab, setActiveTab] = useState<"result" | "timeline">(
    hasResult ? "result" : "timeline",
  )

  useEffect(() => {
    if (hasResult) {
      setActiveTab("result")
    }
  }, [hasResult])

  // thread 级实时刷新：复用页面级 /stream/tasks 单连接（dutySse 对每个
  // 事件 invalidate dutyExec/dutyPlan 前缀，task_pulse 带 thread_id）。
  // 此前本组件为每个 wakeup 线程独立开 SSE——每次派发换新线程 id，画布
  // 聚焦循环下每分钟开关 20+ 条连接，客户端断连取消正是连接池孤儿
  // fairy 的主要制造者（sqlalchemy#12710，2026-09-24 探针实锤），故移除。
  useEffect(() => {
    if (DEMO || !threadId) return
    void qc.invalidateQueries({ queryKey: ["dutyExec", threadId] })
    void qc.invalidateQueries({ queryKey: ["dutyPlan", threadId] })
  }, [threadId, qc])

  // 新步骤推进时平滑跟随滚动至最底部（最新步）
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [])

  // 统一构建时间线 items（必须置于任何条件 return 之前，遵守 React Hook 规则）
  const timelineItems = useMemo<TraceNodeItem[]>(() => {
    return msgs.map((m, i) => {
      const kind = classify(m)
      const full = textOf(m)
      const toolName = kind === "tool" ? toolNameOf(m) : undefined
      let toolData
      if (kind === "tool") {
        let inputObj
        const rawM = m as any
        try {
          if (typeof rawM.input === "object") inputObj = rawM.input
          else if (typeof rawM.input === "string")
            inputObj = JSON.parse(rawM.input)
        } catch {}
        toolData = {
          toolName: toolName || "tool",
          // 后端 tool_meta.display_name（evoloop.tool_summary.* i18n，落库即有）
          // ——与聊天流同一展示体系；键白名单降级为缺席时的兜底
          displayName:
            typeof rawM.tool_meta?.display_name === "string"
              ? rawM.tool_meta.display_name
              : undefined,
          input: inputObj as Record<string, unknown> | undefined,
          output: rawM.output,
          status: "success" as const,
        }
      }
      return {
        id: m.id || i,
        kind:
          kind === "instruction" ||
          kind === "think" ||
          kind === "tool" ||
          kind === "artifact" ||
          kind === "error" ||
          kind === "hitl"
            ? kind
            : "system",
        title: kind === "tool" ? `${toolName}()` : undefined,
        content: full,
        toolData,
        raw: m,
      }
    })
  }, [msgs])

  const steps = planSteps
  const doneSteps = steps.filter((s) => s.status === "completed").length
  const currentStep = steps.find((s) => s.status !== "completed")

  // last tool call (for NOW card "currently calling")
  const lastTool =
    [...msgs].reverse().find((m) => m.category === "assistant_tool_call") ??
    [...msgs].reverse().find((m) => m.role === "tool" && toolNameOf(m))

  const taskArtifacts: ArtifactView[] = (task.artifacts ?? []).map(
    (artifact) => ({
      id: artifact.id,
      stage: artifact.stage,
      type: artifact.type,
      summary: artifact.summary,
      data: artifact.data,
    }),
  )
  const artifacts: ArtifactView[] = taskArtifacts

  async function cancelTask() {
    setBusy(true)
    try {
      if (threadId) {
        try {
          await AgentService.stopChat({
            requestBody: { thread_id: threadId, message: "" },
          })
        } catch {}
      }
      await TasksQueueApi.update(task.id, { status: "cancelled" })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      if (threadId) {
        await qc.invalidateQueries({ queryKey: ["dutyExec", threadId] })
      }
      await onChanged?.()
    } finally {
      setBusy(false)
    }
  }

  // ── 必须在所有 Hooks 执行完毕之后，才执行条件分支返回（杜绝 Rules of Hooks 违背） ──
  if (isProposal) {
    return (
      <div
        key={`prop-${task.id}`}
        className="animate-in fade-in slide-in-from-bottom-1 duration-300"
      >
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
      <div className="p-4 w-full animate-in fade-in duration-200">
        <PendingTaskBrief task={task} />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground p-3">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />{" "}
        加载执行过程…
      </div>
    )
  }

  return (
    <div className="space-y-3 min-h-full flex flex-col">
      {/* ── 顶部视图切换栏 (交付结果 ↔ 执行过程) ── */}
      {hasResult ? (
        <div className="flex items-center justify-between pb-2 mb-1 border-b border-border/40 shrink-0 select-none">
          <div className="flex items-center gap-1 bg-muted/60 p-0.5 rounded-lg border border-border/40">
            <button
              type="button"
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                activeTab === "result"
                  ? "bg-background text-foreground shadow-2xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("result")}
            >
              <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
              <span>交付结果</span>
              {task.status === "waiting_acceptance" && (
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping" />
              )}
            </button>

            <button
              type="button"
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                activeTab === "timeline"
                  ? "bg-background text-foreground shadow-2xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("timeline")}
            >
              <Activity className="h-3.5 w-3.5 text-primary" />
              <span>执行过程</span>
              {timelineItems.length > 0 && (
                <span className="text-[10px] font-mono px-1 rounded bg-muted text-muted-foreground">
                  {timelineItems.length}
                </span>
              )}
            </button>
          </div>

          <div className="flex items-center gap-3 text-[11px] font-mono text-muted-foreground/80 tabular-nums">
            {((task.run?.input_tokens ?? 0) + (task.run?.output_tokens ?? 0) >
              0 ||
              (runTokens ?? 0) > 0) && (
              <span>
                <span className="opacity-60 font-sans">燃耗:</span>{" "}
                <span className="text-foreground/90 font-medium">
                  {(
                    (task.run?.input_tokens ?? 0) +
                      (task.run?.output_tokens ?? 0) ||
                    (runTokens ?? 0)
                  ).toLocaleString()}
                </span>{" "}
                Tokens
              </span>
            )}
            {(task.run?.llm_calls ?? 0) > 0 && (
              <span>
                <span className="opacity-60 font-sans">LLM:</span>{" "}
                <span className="text-foreground/90 font-medium">
                  {task.run?.llm_calls}
                </span>
              </span>
            )}
            {task.elapsed_sec != null && (
              <span>
                <span className="opacity-60 font-sans">耗时:</span>{" "}
                <span className="text-foreground/90 font-medium">
                  {task.elapsed_sec}s
                </span>
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between pb-2 mb-1 border-b border-border/40 shrink-0 select-none">
          <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
            <Activity className="h-3.5 w-3.5 text-primary" />
            <span>执行过程</span>
            {timelineItems.length > 0 && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {timelineItems.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] font-mono text-muted-foreground/80 tabular-nums">
            {isRunning && (
              <span className="text-[10.5px] text-primary flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                实时执行流
              </span>
            )}
            {((task.run?.input_tokens ?? 0) + (task.run?.output_tokens ?? 0) >
              0 ||
              (runTokens ?? 0) > 0) && (
              <span>
                <span className="opacity-60 font-sans">燃耗:</span>{" "}
                <span className="text-foreground/90 font-medium">
                  {(
                    (task.run?.input_tokens ?? 0) +
                      (task.run?.output_tokens ?? 0) ||
                    (runTokens ?? 0)
                  ).toLocaleString()}
                </span>{" "}
                Tokens
              </span>
            )}
            {task.elapsed_sec != null && (
              <span>
                <span className="opacity-60 font-sans">耗时:</span>{" "}
                <span className="text-foreground/90 font-medium">
                  {task.elapsed_sec}s
                </span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── 视图 A：交付成果模式（完全扁平文档流，绝无外层卡片框套框） ── */}
      {hasResult && activeTab === "result" && (
        <div className="animate-in fade-in duration-200">
          <ResultCard
            task={task}
            onVerdictDone={onVerdictDone}
            finalText={finalText}
            finalMsg={finalMsg}
            finalAttachments={
              (finalMsg?.attachments as Attachment[] | undefined) ?? []
            }
            artifacts={artifacts}
            threadId={threadId}
            steps={steps}
            doneSteps={doneSteps}
            onViewTrace={() => setActiveTab("timeline")}
            traceCount={timelineItems.length}
            onChanged={() => {
              qc.invalidateQueries({ queryKey: ["dutyQueue"] })
              qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
              onChanged()
            }}
          />
        </div>
      )}

      {/* ── 视图 B：执行过程轨迹模式 ── */}
      {(!hasResult || activeTab === "timeline") && (
        <div className="space-y-3 animate-in fade-in duration-200">
          {!hideNowCard && !isTerminal && (
            <div className="shrink-0 sticky top-0 z-10 rounded-lg bg-background p-1">
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
                  <span className="text-sm font-semibold truncate">
                    {task.title}
                  </span>
                  <span className="flex-1" />
                  {isRunning &&
                    (hasHitl ? (
                      <span className="font-mono text-xs text-amber-500 font-semibold flex items-center gap-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping" />
                        WAITING HITL
                      </span>
                    ) : (
                      <span className="font-mono text-xs text-primary tabular-nums">
                        RUNNING
                      </span>
                    ))}
                </div>
                {task.description && (
                  <div className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                    {linkifyText(task.description)}
                  </div>
                )}
                {hasHitl && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                    <span className="h-2 w-2 rounded-full bg-amber-500 animate-ping shrink-0" />
                    <span>
                      Agent 遇到待决策项 ·
                      正在等待您的决策指示（请在下方卡片处理）
                    </span>
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

          {/* ── TIMELINE ── */}
          <AgentExecutionTimeline
            items={timelineItems}
            renderContent={(c) => <MessageContent content={c} />}
            renderNodeExtra={(node) => {
              const m = node.raw as Msg
              const kind = node.kind
              return (
                <>
                  {((m.attachments as Attachment[] | undefined)?.length ?? 0) >
                    0 && (
                    <AttachmentStrip items={m.attachments as Attachment[]} />
                  )}
                  {kind === "hitl" &&
                    (() => {
                      const hitlReq = hitlRequestFromMsg(m, threadId ?? "")
                      if (!hitlReq) return null
                      return (
                        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs space-y-1.5 my-1">
                          <div className="flex items-center gap-1.5 font-semibold text-amber-600 dark:text-amber-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
                            <span>待处理决策事项</span>
                          </div>
                          <div className="text-foreground leading-relaxed break-words font-medium">
                            {hitlReq.prompt}
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            💡 请在屏幕底部的决策卡片中完成选项指示与授权
                          </div>
                        </div>
                      )
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
                </>
              )
            }}
          />

          {hasResult && (
            <div className="pt-2 flex justify-center pb-2">
              <Button
                variant="outline"
                size="sm"
                className="text-xs gap-1.5 font-medium cursor-pointer"
                onClick={() => setActiveTab("result")}
              >
                <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
                返回查看最终交付结果
              </Button>
            </div>
          )}

          {isReviewing && (
            <ReviewProgressCard
              task={task}
              hitlItems={taskHitl}
              onChanged={onChanged}
            />
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}

/**
 * 顶部任务执行与交付总览卡片 (TaskExecutionOverviewCard)
 * 供顶栏横跨展示：
 * - 终态：完整 ResultCard（最终回复、最终产物 artifacts、附件、验收/打回操作）
 * - 运行中/待执行：完整 NOW 卡片（任务描述、步骤进度条、当前步骤、当前工具、燃耗、终止/接管会话）
 */
export function TaskExecutionOverviewCard({
  task,
  threadId,
  runTokens,
  hitlPending,
  onChanged,
  onVerdictDone: _onVerdictDone,
}: {
  task: QueueTask
  threadId?: string | null
  runTokens?: number | null
  hitlPending?: DutyHitlPendingItem[]
  onChanged: () => void | Promise<void>
  onVerdictDone?: (landInTab: "done" | "active") => void
}) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const actualThreadId = threadId ?? task.last_thread_id

  const { data } = useQuery({
    queryKey: ["dutyExec", actualThreadId],
    queryFn: async () =>
      DEMO
        ? ({
            messages: getDemoMessages(actualThreadId).messages,
          } as unknown as Awaited<
            ReturnType<typeof ConversationsService.getConversationMessages>
          >)
        : await ConversationsService.getConversationMessages({
            threadId: actualThreadId as string,
            limit: 40,
            includeToolCalls: true,
          }),
    enabled: DEMO || !!actualThreadId,
  })

  const planQ = useQuery({
    queryKey: ["dutyPlan", actualThreadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(actualThreadId) as unknown as Awaited<
            ReturnType<typeof PlanningService.getPlan>
          >)
        : await PlanningService.getPlan({ threadId: actualThreadId as string }),
    enabled: DEMO || !!actualThreadId,
  })

  const body = data as unknown as { data?: Msg[]; messages?: Msg[] } | null
  const rawMsgs: Msg[] = body?.data ?? body?.messages ?? []
  const msgs: Msg[] = useMemo(() => {
    const list = [...rawMsgs]
    list.sort((a, b) => {
      const seqA = (a as any).sequence_number ?? (a as any).seq ?? 0
      const seqB = (b as any).sequence_number ?? (b as any).seq ?? 0
      if (seqA !== seqB) return seqA - seqB
      const timeA = new Date(
        (a as any).created_at || (a as any).timestamp || 0,
      ).getTime()
      const timeB = new Date(
        (b as any).created_at || (b as any).timestamp || 0,
      ).getTime()
      return timeA - timeB
    })
    return list.slice(-50)
  }, [rawMsgs])
  const planBody = planQ.data as unknown as {
    plan?: { steps?: PlanStep[] }
  } | null
  const planSteps = planBody?.plan?.steps ?? []

  const hitlQ = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
  })
  const allHitl: DutyHitlPendingItem[] = (hitlPending ??
    hitlQ.data?.items ??
    []) as DutyHitlPendingItem[]
  const taskHitl = useMemo<DutyHitlPendingItem[]>(() => {
    return allHitl.filter(
      (h) =>
        (task.id && h.task_id === task.id) ||
        (actualThreadId && h.thread_id === actualThreadId),
    )
  }, [allHitl, task.id, actualThreadId])

  const isRunning = task.status === "in_progress"
  const hasHitl = taskHitl.length > 0
  const isTerminal = [
    "waiting_acceptance",
    "completed",
    "failed",
    "cancelled",
  ].includes(task.status)
  const steps = planSteps
  const doneSteps = steps.filter((s) => s.status === "completed").length
  const currentStep = steps.find((s) => s.status !== "completed")

  const lastTool =
    [...msgs].reverse().find((m) => m.category === "assistant_tool_call") ??
    [...msgs].reverse().find((m) => m.role === "tool" && toolNameOf(m))

  const taskArtifacts: ArtifactView[] = (task.artifacts ?? []).map(
    (artifact) => ({
      id: artifact.id,
      stage: artifact.stage,
      type: artifact.type,
      summary: artifact.summary,
      data: artifact.data,
    }),
  )
  const artifacts: ArtifactView[] = taskArtifacts

  async function cancelTask() {
    setBusy(true)
    try {
      if (actualThreadId) {
        try {
          await AgentService.stopChat({
            requestBody: { thread_id: actualThreadId, message: "" },
          })
        } catch {}
      }
      await TasksQueueApi.update(task.id, { status: "cancelled" })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      if (actualThreadId) {
        await qc.invalidateQueries({ queryKey: ["dutyExec", actualThreadId] })
      }
      await onChanged?.()
    } finally {
      setBusy(false)
    }
  }

  // 始终保持紧凑优雅的 Executive 概览条（严格高度 ≤ 68px，杜绝终态巨型卡片压死下方工作台）
  return (
    <div className="rounded-xl bg-muted/30 dark:bg-muted/15 border border-border/60 px-3.5 py-2 space-y-1.5 select-none animate-in fade-in duration-200">
      {/* ── 任务描述（单行优雅截断，带 tooltip 提示） ── */}
      {task.description && (
        <div
          className="text-xs text-muted-foreground/90 leading-relaxed truncate"
          title={task.description}
        >
          {linkifyText(task.description)}
        </div>
      )}

      {/* ── 进度条、步骤状态与产物指标条 ── */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {/* 步骤进度 */}
          {steps.length > 0 && (
            <div className="flex items-center gap-2">
              <div className="w-20 h-1.5 rounded-full bg-muted/80 overflow-hidden shrink-0">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    isTerminal && task.status === "completed"
                      ? "bg-emerald-500"
                      : "bg-primary"
                  }`}
                  style={{
                    width: `${(doneSteps / steps.length) * 100}%`,
                  }}
                />
              </div>
              <span className="font-mono text-[11px] font-medium text-foreground shrink-0">
                {doneSteps}/{steps.length} 步骤
              </span>
            </div>
          )}

          {/* 终态已完成标志 */}
          {isTerminal && task.status === "completed" && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[11px] font-medium border border-emerald-500/20">
              <CheckCircle2 className="h-3 w-3" />
              <span>评审通过</span>
            </span>
          )}

          {/* 待验收状态提醒 */}
          {task.status === "waiting_acceptance" && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[11px] font-medium border border-amber-500/20 animate-pulse">
              <BadgeCheck className="h-3 w-3" />
              <span>待验收（见右栏报告）</span>
            </span>
          )}

          {/* HITL 决策等待 */}
          {hasHitl && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
              <span>等待决策授权（见底栏）</span>
            </span>
          )}

          {/* 运行中当前步骤与工具 */}
          {isRunning && currentStep?.title && (
            <div className="text-[11px] text-muted-foreground truncate max-w-[200px]">
              <span className="opacity-70">进行中:</span>{" "}
              <span className="text-foreground font-medium">
                {currentStep.title}
              </span>
            </div>
          )}

          {isRunning && lastTool && (
            <div className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground">
              <Wrench className="h-3 w-3 shrink-0 text-primary" />
              <span className="truncate max-w-[160px]">
                {toolNameOf(lastTool)}()
              </span>
            </div>
          )}

          {/* 交付物胶囊 */}
          {artifacts.length > 0 && (
            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-foreground text-[11px] font-medium border border-border/40">
              <Package className="h-3 w-3 text-emerald-500 shrink-0" />
              <span className="truncate max-w-[200px]">
                交付物 ({artifacts.length}):{" "}
                {artifacts.map((a) => a.summary || a.type).join(" · ")}
              </span>
            </div>
          )}
        </div>

        {/* 右侧：统计度量与控制 */}
        <div className="flex items-center gap-3 shrink-0 text-[11px] font-mono text-muted-foreground tabular-nums ml-auto">
          {task.elapsed_sec != null && (
            <span>
              <span className="opacity-60 font-sans">耗时:</span>{" "}
              <span className="text-foreground font-medium">
                {task.elapsed_sec}s
              </span>
            </span>
          )}

          {runTokens != null && runTokens > 0 && (
            <span>
              <span className="opacity-60 font-sans">燃耗:</span>{" "}
              <span className="text-primary font-medium">
                {runTokens.toLocaleString()}
              </span>
            </span>
          )}

          {/* 终止按钮 */}
          {isRunning && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px] text-destructive hover:text-destructive hover:bg-destructive/10 cursor-pointer shrink-0"
              disabled={busy}
              onClick={cancelTask}
            >
              <Square className="h-3 w-3 mr-1 fill-current" />
              终止
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
