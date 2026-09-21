import { useEffect, useMemo, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { OpenAPI } from "@/client"
import { MessageContent } from "@/components/Chat/MessageContent"
import { useNavigate } from "@tanstack/react-router"
import {
  PauseCircle,
  ExternalLink,
  Loader2,
  Square,
  Wrench,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { ConversationsService, PlanningService } from "@/client"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"
import {
  classify,
  textOf,
  toolNameOf,
  type Msg,
} from "../core/parse"
import { DEMO } from "../core/demoData"
import { ResultCard, AttachmentStrip } from "./ResultCard"
import { ProposalCard, InlineProposal } from "./ProposalCards"
import { hitlRequestFromMsg } from "../core/parse"
import {
  AgentExecutionTimeline,
  type TraceNodeItem,
} from "@evoloop/shared"
import { ReviewProgressCard } from "./ReviewProgressCard"
import { PendingTaskBrief } from "./PendingTaskBrief"
import type { Attachment, ArtifactView, PlanStep } from "../core/types"
import {
  getDemoMessages,
  getDemoPlan,
} from "../core/demoRuntime"





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

  // SSE 独驱：thread_updated/hitl 事件 + onopen 重连对账，不设周期轮询
  const hitlQ = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
  })
  const allHitl: DutyHitlPendingItem[] = (hitlPending ?? hitlQ.data?.items ?? []) as DutyHitlPendingItem[]
  const taskHitl = useMemo<DutyHitlPendingItem[]>(() => {
    return allHitl.filter(
      (h) =>
        (task.id && h.task_id === task.id) ||
        (threadId && h.thread_id === threadId)
    )
  }, [allHitl, task.id, threadId])

  const isRunning = task.status === "in_progress"
  const hasHitl = taskHitl.length > 0
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

  // thread-level SSE: message landed → refresh timeline & plan (no polling gap)
  useEffect(() => {
    if (DEMO || !threadId) return
    const source = new EventSource(
      `${OpenAPI.BASE}/api/v1/stream/thread/${threadId}`,
      { withCredentials: true },
    )
    // 连接建立/每次重连 → 对账一次（收敛断线窗口漏掉的事件）
    source.onopen = () => {
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
      void qc.invalidateQueries({ queryKey: ["dutyExec", threadId] })
      void qc.invalidateQueries({ queryKey: ["dutyPlan", threadId] })
    }
    source.addEventListener("thread_updated", () => {
      void qc.invalidateQueries({ queryKey: ["dutyExec", threadId] })
      void qc.invalidateQueries({ queryKey: ["dutyPlan", threadId] })
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
    })
    return () => source.close()
  }, [DEMO, threadId, qc])

  // follow new timeline nodes as they arrive (hooks must be unconditional)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [msgs.length])

  // 统一构建时间线 items（必须置于任何条件 return 之前，遵守 React Hook 规则）
  const timelineItems = useMemo<TraceNodeItem[]>(() => {
    return msgs.map((m, i) => {
      const kind = classify(m)
      const full = textOf(m)
      const toolName = kind === "tool" ? toolNameOf(m) : undefined
      let toolData = undefined
      if (kind === "tool") {
        let inputObj = undefined
        const rawM = m as any
        try {
          if (typeof rawM.input === "object") inputObj = rawM.input
          else if (typeof rawM.input === "string") inputObj = JSON.parse(rawM.input)
        } catch {}
        toolData = {
          toolName: toolName || "tool",
          input: inputObj as Record<string, unknown> | undefined,
          output: rawM.output,
          status: "success" as const,
        }
      }
      return {
        id: m.id || i,
        kind: (kind === "instruction" || kind === "think" || kind === "tool" || kind === "artifact" || kind === "error" || kind === "hitl" ? kind : "system"),
        title: kind === "tool" ? `${toolName}()` : undefined,
        content: full,
        toolData,
        raw: m,
      }
    })
  }, [msgs])

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

  return (
    <div className="space-y-3 min-h-full flex flex-col">
      {/* ── ① NOW / RESULT card ────────────────────────── */}
      {!hideNowCard && isTerminal && (
        <div key={`res-${task.id}`} className="sticky top-0 z-10 bg-background rounded-lg animate-in fade-in slide-in-from-bottom-1 duration-300">
        <ResultCard
          task={task}
          onVerdictDone={onVerdictDone}
          finalText={finalText}
          finalAttachments={(finalMsg?.attachments as Attachment[] | undefined) ?? []}
          artifacts={artifacts}
          threadId={threadId}
          steps={steps}
          doneSteps={doneSteps}
          onChanged={() => {
            qc.invalidateQueries({ queryKey: ["dutyQueue"] })
            qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
          }}
        />
        </div>
      )}
      {!hideNowCard && !isTerminal && (
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
            hasHitl ? (
              <span className="font-mono text-xs text-amber-500 font-semibold flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping" />
                WAITING HITL
              </span>
            ) : (
              <span className="font-mono text-xs text-primary tabular-nums">
                RUNNING
              </span>
            )
          )}
        </div>
        {task.description && (
          <div className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
            {task.description}
          </div>
        )}
        {hasHitl && (
          <div className="mt-2 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
            <span className="h-2 w-2 rounded-full bg-amber-500 animate-ping shrink-0" />
            <span>Agent 遇到待决策项 · 正在等待您的决策指示（请在下方卡片处理）</span>
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
      <AgentExecutionTimeline
        items={timelineItems}
        renderContent={(c) => <MessageContent content={c} />}
        renderNodeExtra={(node) => {
          const m = node.raw as Msg
          const kind = node.kind
          return (
            <>
              {((m.attachments as Attachment[] | undefined)?.length ?? 0) > 0 && (
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
      {isReviewing && (
        <ReviewProgressCard
          task={task}
          hitlItems={taskHitl}
          onChanged={onChanged}
        />
      )}
      <div ref={bottomRef} />
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
  onVerdictDone,
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
        ? (getDemoPlan(actualThreadId) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: actualThreadId as string }),
    enabled: DEMO || !!actualThreadId,
  })

  const body = data as unknown as { data?: Msg[]; messages?: Msg[] } | null
  const rawMsgs: Msg[] = body?.data ?? body?.messages ?? []
  const msgs: Msg[] = [...rawMsgs].slice(0, 40).reverse()
  const planBody = planQ.data as unknown as {
    plan?: { steps?: PlanStep[] }
  } | null
  const planSteps = planBody?.plan?.steps ?? []

  const hitlQ = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
  })
  const allHitl: DutyHitlPendingItem[] = (hitlPending ?? hitlQ.data?.items ?? []) as DutyHitlPendingItem[]
  const taskHitl = useMemo<DutyHitlPendingItem[]>(() => {
    return allHitl.filter(
      (h) =>
        (task.id && h.task_id === task.id) ||
        (actualThreadId && h.thread_id === actualThreadId)
    )
  }, [allHitl, task.id, actualThreadId])

  const isRunning = task.status === "in_progress"
  const hasHitl = taskHitl.length > 0
  const isTerminal = ["waiting_acceptance", "completed", "failed"].includes(
    task.status,
  )
  const finalMsg =
    [...msgs].reverse().find((m) => m.category === "assistant_response") ??
    [...msgs]
      .reverse()
      .find((m) => (m.role === "ai" || m.role === "assistant") && !toolNameOf(m))
  const finalText = finalMsg ? textOf(finalMsg).slice(0, 2500) : ""

  const steps = planSteps
  const doneSteps = steps.filter((s) => s.status === "completed").length
  const currentStep = steps.find((s) => s.status !== "completed")

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

  async function cancelTask() {
    setBusy(true)
    try {
      await TasksQueueApi.update(task.id, { status: "cancelled" })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  // 终态：完整 ResultCard（最终回复、结果产物、附件、验收/打回）
  if (isTerminal) {
    return (
      <div key={`res-top-${task.id}`} className="bg-background rounded-xl border border-border/80 p-3 shadow-sm animate-in fade-in slide-in-from-top-1 duration-300">
        <ResultCard
          task={task}
          onVerdictDone={onVerdictDone}
          finalText={finalText}
          finalAttachments={(finalMsg?.attachments as Attachment[] | undefined) ?? []}
          artifacts={artifacts}
          threadId={actualThreadId ?? null}
          steps={steps}
          doneSteps={doneSteps}
          onChanged={() => {
            qc.invalidateQueries({ queryKey: ["dutyQueue"] })
            qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
            onChanged()
          }}
        />
      </div>
    )
  }

  // 进行时 / 待执行：精炼紧凑的任务执行概览（去重复标题与粗暴黄框，优雅展示描述、进度、当前步骤与控制）
  return (
    <div className="rounded-xl bg-muted/25 dark:bg-muted/15 border border-border/60 p-3 space-y-2 select-none">
      {/* ── 任务描述（做两行优雅截断，避免大段文字霸屏） ── */}
      {task.description && (
        <div className="text-xs text-muted-foreground/90 leading-relaxed line-clamp-2" title={task.description}>
          {task.description}
        </div>
      )}

      {/* ── 进度条与执行步骤 ── */}
      {steps.length > 0 && (
        <div className="flex items-center gap-2 text-xs">
          <div className="flex-1 h-1 rounded bg-muted/70 overflow-hidden">
            <div
              className="h-full bg-primary rounded transition-all duration-500"
              style={{
                width: `${(doneSteps / steps.length) * 100}%`,
              }}
            />
          </div>
          <span className="font-mono text-[10.5px] text-muted-foreground shrink-0 font-medium">
            {doneSteps}/{steps.length}
          </span>
        </div>
      )}

      {/* ── 产物快速预览条 ── */}
      {artifacts.length > 0 && (
        <div className="rounded-md bg-muted/40 px-2.5 py-1.5 text-xs flex items-center gap-2">
          <span className="font-medium text-muted-foreground shrink-0 text-[11px]">交付物 ({artifacts.length}):</span>
          <span className="text-foreground truncate text-[11px]">{artifacts.map(a => a.summary || a.type).join(" · ")}</span>
        </div>
      )}

      {/* ── 状态与当前执行信息 ── */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs pt-1 border-t border-border/40">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground text-[11px]">
          {hasHitl && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
              <span>等待决策指示（见底栏）</span>
            </span>
          )}
          {currentStep?.title && (
            <div>
              当前步骤：
              <span className="text-foreground font-medium">
                {currentStep.title}
              </span>
            </div>
          )}
          {isRunning && (
            <div className="flex items-center gap-1 font-mono text-[11px]">
              <Wrench className="h-3 w-3 shrink-0" />
              <span className="truncate max-w-[200px]">
                {lastTool ? `${toolNameOf(lastTool)}()` : "等待工具调用"}
              </span>
            </div>
          )}
          {isRunning && runTokens != null && (
            <div className="font-mono tabular-nums text-primary text-[11px]">
              {runTokens.toLocaleString()} tokens
            </div>
          )}
        </div>

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
  )
}
