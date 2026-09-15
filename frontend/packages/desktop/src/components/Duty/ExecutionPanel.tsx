import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  AlertTriangle,
  BadgeCheck,
  Play,
  ChevronDown,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareX,
  Package,
  Square,
  Wrench,
  XCircle,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { ConversationsService, PlanningService } from "@/client"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"
import { DEMO } from "@/components/Duty/demoData"
import {
  getDemoMessages,
  getDemoPlan,
} from "@/components/Duty/demoRuntime"

interface Attachment {
  type: "image" | "video" | "file"
  label: string
  w: number
  h: number
  duration?: number
  hue: number
}

interface Msg {
  id?: string
  role?: string
  content?: string
  name?: string
  tool_calls?: unknown
  attachments?: Attachment[]
}

interface PlanStep {
  id?: string
  title?: string
  status?: string
}

function toolNameOf(m: Msg): string {
  if (m.name) return m.name
  const tc = m.tool_calls as
    | { name?: string }[]
    | { name?: string }
    | null
    | undefined
  if (Array.isArray(tc)) return tc[0]?.name ?? ""
  if (tc && typeof tc === "object" && tc !== null) return tc.name ?? ""
  return ""
}

function textOf(m: Msg): string {
  if (typeof m.content === "string") return m.content
  try {
    return JSON.stringify(m.content) ?? ""
  } catch {
    return ""
  }
}

const ARTIFACT_RE = /(已写入|已创建|已下架|已更新|已发布|已上架|已生成|已完成)/
const ERROR_RE = /(error|failed|失败|异常|超时|timeout)/i

type NodeKind = "tool" | "think" | "artifact" | "error"

function classify(m: Msg): NodeKind {
  if (m.role === "tool") return "tool"
  const text = textOf(m)
  if (ERROR_RE.test(text)) return "error"
  if (ARTIFACT_RE.test(text)) return "artifact"
  return "think"
}

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
}

/** Execution workbench: NOW card + timeline + artifacts/cost strip. */
export function ExecutionPanel({
  task,
  runTokens,
  sourceTask,
  relatedProposals,
  onChanged,
  onConfirmed,
}: {
  task: QueueTask
  runTokens?: number | null
  sourceTask?: QueueTask | null
  relatedProposals?: QueueTask[]
  onChanged: () => void | Promise<void>
  onConfirmed: () => void | Promise<void>
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [timelineOpen, setTimelineOpen] = useState(false)
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
    refetchInterval: 5000,
  })

  const planQ = useQuery({
    queryKey: ["dutyPlan", threadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(threadId) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: threadId as string }),
    enabled: DEMO || !!threadId,
    refetchInterval: 5000,
  })

  const body = data as unknown as { messages?: Msg[] } | null
  const msgs: Msg[] = body?.messages ?? []
  const planBody = planQ.data as unknown as {
    plan?: { steps?: PlanStep[] }
  } | null
  const planSteps = planBody?.plan?.steps ?? []
  const isRunning = task.status === "in_progress"
  const isTerminal = ["waiting_acceptance", "completed", "failed"].includes(
    task.status,
  )
  const finalMsg = [...msgs]
    .reverse()
    .find((m) => (m.role === "ai" || m.role === "assistant") && !toolNameOf(m))
  const finalText = finalMsg ? textOf(finalMsg).slice(0, 2500) : ""

  const isProposal = task.status === "proposed"

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
        任务尚未派发执行
      </div>
    )
  }

  const steps = planSteps
  const doneSteps = steps.filter((s) => s.status === "completed").length
  const currentStep = steps.find((s) => s.status !== "completed")

  // last tool call (for NOW card "currently calling")
  const lastTool = [...msgs].reverse().find((m) => toolNameOf(m))
  const lastToolText = lastTool ? textOf(lastTool).slice(0, 90) : ""

  // artifacts: artifact-kind AI messages (latest 3)
  const artifacts = msgs
    .filter((m) => classify(m) === "artifact")
    .slice(-3)

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
    <div className="space-y-3">
      {/* ── ① NOW / RESULT card ────────────────────────── */}
      {isTerminal && (
        <div key={`res-${task.id}`} className="animate-in fade-in slide-in-from-bottom-1 duration-300">
        <ResultCard
          task={task}
          finalText={finalText}
          finalAttachments={finalMsg?.attachments ?? []}
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
        className={`rounded-lg p-3 ${
          isRunning ? "bg-primary/10" : "bg-muted/40"
        }`}
      >
        <div className="flex items-center gap-2">
          {isRunning ? (
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

        {steps.length > 0 && (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <div className="flex-1 h-1.5 rounded bg-muted overflow-hidden">
              <div
                className="h-full bg-primary rounded transition-all duration-500"
                style={{
                  width: `${steps.length ? (doneSteps / steps.length) * 100 : 0}%`,
                }}
              />
            </div>
            <span className="font-mono text-[11px] text-muted-foreground shrink-0">
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
              {lastTool ? `${toolNameOf(lastTool)}() → ${lastToolText}` : "等待工具调用"}
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
      )}

      {/* ── ② TIMELINE ─────────────────────────────────── */}
      {isTerminal && !timelineOpen && msgs.length > 0 && (
        <button
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-1"
          onClick={() => setTimelineOpen(true)}
        >
          <ChevronDown className="h-3.5 w-3.5" />
          展开执行过程（{msgs.length} 条节点）
        </button>
      )}
      {(timelineOpen || !isTerminal) && msgs.length === 0 && (
        <div className="text-xs text-muted-foreground p-2">暂无执行记录</div>
      )}
      {(timelineOpen || !isTerminal) && msgs.length > 0 && (
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
                    {kind === "error" && (
                      <AlertTriangle className="h-2.5 w-2.5 text-destructive" />
                    )}
                    {kind === "artifact" && (
                      <Package className="h-2.5 w-2.5 text-emerald-500" />
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
                  <div
                    className={`text-xs whitespace-pre-wrap break-words text-muted-foreground ${
                      isOpen ? "" : "line-clamp-2"
                    }`}
                  >
                    {isOpen ? full.slice(0, 2000) : preview}
                  </div>
                  {m.attachments && m.attachments.length > 0 && (
                    <AttachmentStrip items={m.attachments} />
                  )}
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
          <div ref={bottomRef} />
        </div>
      )}

      {/* ── ③ issues / cost strip（固定底部，不随滚动） */}
      <div className="sticky bottom-0 -mx-3 -mb-3 px-3 pb-3 pt-2 bg-background">
      <div className={`grid gap-2 ${isTerminal ? "grid-cols-2" : "grid-cols-3"}`}>
        {!isTerminal && (
        <div className="rounded-lg bg-muted/40 p-2 min-w-0">
          <div className="text-[10px] font-medium text-muted-foreground flex items-center gap-1 mb-1">
            <Package className="h-3 w-3 text-emerald-500" />
            产出物
          </div>
          {artifacts.length === 0 ? (
            <div className="text-[11px] text-muted-foreground/50">暂无</div>
          ) : (
            <div className="space-y-0.5">
              {artifacts.map((m, i) => (
                <div
                  key={i}
                  className="text-[11px] text-muted-foreground truncate"
                >
                  {textOf(m).slice(0, 40)}
                </div>
              ))}
            </div>
          )}
        </div>
        )}
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
          <div className="text-[10px] font-medium text-muted-foreground mb-1">
            消耗
          </div>
          <div className="space-y-0.5 font-mono text-[11px] text-muted-foreground">
            <div>步骤 {doneSteps}/{steps.length || "—"}</div>
            <div>消息 {msgs.length}</div>
            <div>调用 {toolCount}</div>
          </div>
        </div>
      </div>
      </div>
    </div>
  )
}


function ResultCard({
  task,
  finalText,
  finalAttachments,
  artifacts,
  threadId,
  onChanged,
}: {
  task: QueueTask
  finalText: string
  finalAttachments: Attachment[]
  artifacts: Msg[]
  threadId: string | null
  onChanged: () => void | Promise<void>
}) {
  const navigate = useNavigate()
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState("")
  const [busy, setBusy] = useState(false)

  const isWaiting = task.status === "waiting_acceptance"
  const isDone = task.status === "completed"
  const isFailed = task.status === "failed"
  const badgeCls = isWaiting
    ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
    : isDone
      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      : "bg-destructive/10 text-destructive"
  const statusText = isWaiting
    ? "待验收"
    : isDone
      ? "已完成"
      : "失败"
  const selfNotes =
    (task.self_check as { notes?: string } | null)?.notes ?? ""

  async function accept() {
    setBusy(true)
    try {
      await TasksQueueApi.accept(task.id)
      await onChanged()
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
    <div
      className={`rounded-lg p-3 ${
        isWaiting
          ? "bg-amber-500/5"
          : isDone
            ? "bg-emerald-500/5"
            : "bg-destructive/5"
      }`}
    >
      <div className="flex items-center gap-2">
        {isWaiting && (
          <BadgeCheck className="h-4 w-4 text-amber-500 shrink-0" />
        )}
        {isDone && (
          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
        )}
        {isFailed && (
          <XCircle className="h-4 w-4 text-destructive shrink-0" />
        )}
        <span className="text-sm font-semibold truncate">{task.title}</span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${badgeCls}`}
        >
          {statusText}
        </span>
        <span className="flex-1" />
        <Button
          size="sm"
          variant="ghost"
          className="h-6 gap-1 px-2 text-[11px] text-muted-foreground"
          onClick={() =>
            navigate({
              to: "/chat",
              search: { thread_id: (threadId ?? "") as string },
            })
          }
        >
          <ExternalLink className="h-3 w-3" />
          会话
        </Button>
      </div>

      {/* final reply */}
      <div className="mt-2 rounded-md bg-background/70 p-2.5">
        <div className="text-[10px] font-medium text-muted-foreground mb-1">
          Agent 最终回复
        </div>
        <div className="text-xs whitespace-pre-wrap break-words leading-relaxed">
          {finalText || "（无最终回复记录）"}
        </div>
        {finalAttachments.length > 0 && (
          <AttachmentStrip items={finalAttachments} />
        )}
      </div>

      {artifacts.length > 0 && (
        <div className="mt-2 rounded-md bg-background/70 p-2.5">
          <div className="text-[10px] font-medium text-muted-foreground mb-1 flex items-center gap-1">
            <Package className="h-3 w-3 text-emerald-500" />
            产出物 · {artifacts.length}
          </div>
          <div className="space-y-1.5">
            {artifacts.map((m, i) => (
              <div key={i}>
                <div className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                  <span className="text-emerald-500/70 mt-0.5">·</span>
                  <span className="truncate">{textOf(m).slice(0, 120)}</span>
                </div>
                {m.attachments && m.attachments.length > 0 && (
                  <AttachmentStrip items={m.attachments} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {task.elapsed_sec != null && (
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          总耗时：
          <span className="font-mono tabular-nums">
            {Math.floor(task.elapsed_sec / 60)}m {task.elapsed_sec % 60}s
          </span>
        </div>
      )}
      {selfNotes && (
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          自检报告：{selfNotes}
        </div>
      )}

      {/* acceptance actions */}
      {isWaiting && (
        <div className="mt-2.5">
          {!rejectOpen ? (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                className="h-7 gap-1 px-3 text-xs"
                disabled={busy}
                onClick={accept}
              >
                <BadgeCheck className="h-3.5 w-3.5" />
                验收通过
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
            <div className="space-y-1.5">
              <textarea
                className="w-full min-h-[64px] rounded-md border bg-transparent p-2 text-xs"
                placeholder="驳回原因（必填，将反馈给 Agent 修正）"
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
      )}

      {isDone && task.acceptance && (
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          验收回执：
          {(task.acceptance as { by?: string }).by === "system:auto"
            ? "系统自动验收（T3/T4 低风险）"
            : `人工验收 · ${(task.acceptance as { by?: string }).by ?? "运营者"}`}
        </div>
      )}
      {isFailed && (
        <div className="mt-1.5 text-[11px] text-destructive/80">
          可在队列中重新创建同类任务重试
        </div>
      )}
    </div>
  )
}


function AttachmentStrip({ items }: { items: Attachment[] }) {
  return (
    <div className="flex gap-2 flex-wrap mt-1.5">
      {items.map((a, i) =>
        a.type === "file" ? (
          <div
            key={i}
            className="flex items-center gap-1.5 w-full rounded-md bg-muted/40 px-2 py-1.5"
          >
            <FileText className="h-3.5 w-3.5 text-sky-500 shrink-0" />
            <span className="truncate flex-1 text-[11px] text-muted-foreground">
              {a.label}
            </span>
            <span className="text-[9px] text-muted-foreground/60 shrink-0">
              附件
            </span>
          </div>
        ) : (
        <div
          key={i}
          className="relative rounded-md overflow-hidden border-0"
          style={{
            width: a.w >= a.h ? 96 : 54,
            aspectRatio: `${a.w} / ${a.h}`,
            background: `linear-gradient(135deg, hsl(${a.hue} 70% 55%), hsl(${(a.hue + 40) % 360} 65% 38%))`,
          }}
        >
          {a.type === "video" && (
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="w-6 h-6 rounded-full bg-black/40 flex items-center justify-center">
                <Play className="h-3 w-3 text-white fill-white ml-0.5" />
              </span>
            </span>
          )}
          <span className="absolute bottom-0 inset-x-0 bg-black/45 text-white text-[8px] px-1 py-0.5 truncate">
            {a.label}
            {a.duration ? ` · ${a.duration}s` : ` · ${a.w}:${a.h}`}
          </span>
        </div>
        )
      )}
    </div>
  )
}


function ProposalCard({
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


function InlineProposal({
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
