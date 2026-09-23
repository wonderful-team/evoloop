import { useState, useMemo } from "react"
import { useNavigate } from "@tanstack/react-router"
import {
  BadgeCheck,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareX,
  Package,
  Play,
  RotateCcw,
  Scale,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"
import {
  ChatMessageItem,
  type Message,
  type MessageReference,
} from "@/components/Chat/ChatMessageItem"
import type { Attachment, ArtifactView } from "../core/types"

export function ResultCard({
  task,
  onVerdictDone,
  finalText,
  finalAttachments,
  finalMsg,
  artifacts,
  threadId: _threadId,
  onChanged,
  onViewTrace,
  traceCount,
  steps: _steps,
  doneSteps: _doneSteps,
}: {
  task: QueueTask
  onVerdictDone?: (landInTab: "done" | "active") => void
  finalText: string
  finalAttachments?: Attachment[]
  finalMsg?: any
  artifacts?: ArtifactView[]
  threadId?: string | null
  onChanged: () => void | Promise<void>
  onViewTrace?: () => void
  traceCount?: number
  steps?: Array<{ title?: string; status?: string }>
  doneSteps?: number
}) {
  const navigate = useNavigate()
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState("")
  const [busy, setBusy] = useState(false)

  const isWaiting = task.status === "waiting_acceptance"
  const isDone = task.status === "completed"
  const isFailed = task.status === "failed"
  // 评审中（原对话 Agent 核验）不是人工验收：此时开放验收/驳回按钮会让
  // 用户打断 reviewer 流程（审计断层 3.1）——只读呈现，等评审收敛
  const isReviewing = isWaiting && !!task.review_pending
  const selfNotes =
    (task.self_check as { notes?: string } | null)?.notes ?? ""

  // 构造标准的 ChatMessageItem 实体：融合最终文本、思维链、文件引用、改动快照与附件
  const chatMessage = useMemo<Message>(() => {
    const raw = (finalMsg || {}) as Record<string, any>
    const content = finalText || (typeof raw.content === "string" ? raw.content : "")

    // 汇聚 references：消息自身携带的引用 + 终态附件
    const rawRefs = Array.isArray(raw.references)
      ? (raw.references as MessageReference[])
      : []
    const attachmentRefs: MessageReference[] = (finalAttachments || []).map(
      (att, i) => ({
        id: att.id || `att-${i}`,
        type: (att.type === "image" ? "image" : "file") as MessageReference["type"],
        target_id: att.url || att.id || "",
        target_name: att.label || att.name || "附件",
      }),
    )

    const combinedRefs = [...rawRefs, ...attachmentRefs]
    const seen = new Set<string>()
    const uniqueRefs: MessageReference[] = []
    for (const ref of combinedRefs) {
      if (ref.target_id && !seen.has(ref.target_id)) {
        seen.add(ref.target_id)
        uniqueRefs.push(ref)
      }
    }

    return {
      id: raw.id ?? task.id ?? "final-output",
      role: "ai",
      content,
      thinking: typeof raw.thinking === "string" ? raw.thinking : undefined,
      timestamp: raw.created_at ?? task.updated_at ?? undefined,
      status: "completed",
      isLastInTurn: true,
      turnDuration: raw.turnDuration,
      references: uniqueRefs.length > 0 ? uniqueRefs : undefined,
      changeset_files: raw.changeset_files,
      changeset_count: raw.changeset_count ?? raw.changeset_files?.length,
    }
  }, [finalMsg, finalText, finalAttachments, task.id, task.updated_at])

  // 仅保留具有真实独立结构化数据（如选品矩阵表、定价对比表、JSON 数据集等）的成果资产
  const distinctArtifacts = useMemo(() => {
    return (artifacts || []).filter((art) => {
      if (!art) return false
      const hasDistinctData = Boolean(
        art.data &&
          (typeof art.data === "object"
            ? Object.keys(art.data).length > 0
            : true),
      )
      return hasDistinctData
    })
  }, [artifacts])

  async function accept() {
    setBusy(true)
    try {
      await TasksQueueApi.accept(task.id)
      await onChanged()
      onVerdictDone?.("done")
    } finally {
      setBusy(false)
    }
  }

  async function rerun() {
    // failed → pending：仅 failed 可重跑（后端 409 守卫），回队后由
    // supervisor 重新派发——失败详情此前无入口，用户只能去队列重建任务
    setBusy(true)
    try {
      await TasksQueueApi.rerun(task.id)
      await onChanged()
      onVerdictDone?.("active")
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
      onVerdictDone?.("active")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4 py-1 text-foreground">
      {/* ── 待商业验收操作横幅 (仅在 waiting_acceptance 时置顶高亮显示) ── */}
      {isWaiting && !isReviewing && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.08] dark:bg-amber-500/[0.12] p-3 shadow-xs">
          {!rejectOpen ? (
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 min-w-0">
                <BadgeCheck className="h-4 w-4 text-amber-500 shrink-0 animate-pulse" />
                <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">
                  任务已执行完毕 · 请验收下方的最终交付结果
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  className="h-7 gap-1 px-3 text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold cursor-pointer shadow-xs"
                  disabled={busy}
                  onClick={accept}
                >
                  <BadgeCheck className="h-3.5 w-3.5" />
                  商业验收通过
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-3 text-xs text-muted-foreground hover:text-destructive hover:border-destructive/40 cursor-pointer"
                  disabled={busy}
                  onClick={() => setRejectOpen(true)}
                >
                  <MessageSquareX className="h-3.5 w-3.5" />
                  驳回重做
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-[11px] font-semibold text-destructive flex items-center gap-1">
                <MessageSquareX className="h-3.5 w-3.5" />
                填写驳回修改意见（将反馈给 Agent 针对性重做）
              </div>
              <textarea
                className="w-full min-h-[68px] rounded-lg border border-border/80 bg-background p-2.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-destructive"
                placeholder="请输入具体的修改要求或未达标项…"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-7 px-3 text-xs font-semibold cursor-pointer"
                  disabled={!feedback.trim() || busy}
                  onClick={reject}
                >
                  确认驳回
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-3 text-xs cursor-pointer"
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

      {/* ── 评审中横幅：原对话 Agent 核验中，人工验收按钮不开放 ── */}
      {isReviewing && (
        <div className="rounded-xl border border-violet-500/30 bg-violet-500/[0.06] dark:bg-violet-500/[0.10] p-3 shadow-xs">
          <div className="flex items-center gap-2 min-w-0">
            <Loader2 className="h-4 w-4 text-violet-500 shrink-0 animate-spin" />
            <span className="text-xs font-semibold text-violet-600 dark:text-violet-300">
              结果已回灌原对话 · 评审 Agent 正在核验，请稍候（最多两轮，未通过将转人工）
            </span>
          </div>
        </div>
      )}

      {/* ── 核心最终答复：直接复用 ChatMessageItem 标准文档渲染器 ── */}
      {chatMessage.content ? (
        <div className="w-full text-foreground [&>div]:mx-0">
          <ChatMessageItem msg={chatMessage} />
        </div>
      ) : (
        <div className="text-xs text-muted-foreground/60 py-8 text-center select-none">
          （暂无最终答复文本）
        </div>
      )}

      {/* ── 结构化独立交付产物 (数据库矩阵、独立产物表等) ── */}
      {distinctArtifacts.length > 0 && (
        <div className="pt-3 border-t border-border/40 space-y-2">
          <div className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
            <Package className="h-3.5 w-3.5 text-emerald-500" />
            <span>结构化成果资产 ({distinctArtifacts.length})</span>
          </div>
          <div className="grid gap-2">
            {distinctArtifacts.map((artifact, i) => (
              <div
                key={artifact.id ?? i}
                className="rounded-lg border border-border/50 bg-muted/20 p-3 text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground text-[11.5px]">
                    {[artifact.stage, artifact.type]
                      .filter(Boolean)
                      .join(" · ") || "产出资产"}
                  </span>
                  {artifact.id && (
                    <span className="text-[10px] font-mono text-muted-foreground/70">
                      ID: {artifact.id.slice(0, 8)}
                    </span>
                  )}
                </div>
                {artifact.summary && (
                  <div className="text-muted-foreground text-xs leading-relaxed">
                    {artifact.summary}
                  </div>
                )}
                {Boolean(artifact.data) && (
                  <details className="mt-1.5 pt-1.5 border-t border-border/30">
                    <summary className="cursor-pointer text-[11px] text-muted-foreground/80 hover:text-foreground font-medium select-none">
                      查看数据详情
                    </summary>
                    <pre className="mt-1.5 max-h-40 overflow-auto rounded bg-muted/50 p-2 font-mono text-[10.5px] leading-relaxed text-foreground/90">
                      {JSON.stringify(artifact.data, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 自检报告 ── */}
      {selfNotes && (
        <div className="text-xs text-muted-foreground bg-muted/25 rounded-lg p-2.5 border border-border/30">
          <span className="font-semibold text-foreground">自检报告：</span>
          {selfNotes}
        </div>
      )}

      {/* ── 终态回执与过程跳转 ── */}
      <div className="pt-3 border-t border-border/30 flex items-center justify-between flex-wrap gap-2 text-xs text-muted-foreground select-none">
        {isDone && task.acceptance ? (
          <span className="text-[11px]">
            验收回执：
            {(task.acceptance as { by?: string }).by === "system:auto"
              ? "系统自动验收（T3/T4 低风险）"
              : (task.acceptance as { by?: string }).by === "reviewer:auto"
                ? "监察评审通过（原对话 Agent 核验）"
                : `人工验收 · ${(task.acceptance as { by?: string }).by ?? "运营者"}`}
          </span>
        ) : (
          <span />
        )}

        {onViewTrace && (
          <button
            type="button"
            className="text-xs text-primary hover:underline flex items-center gap-1 font-medium cursor-pointer ml-auto"
            onClick={onViewTrace}
          >
            查看执行过程 ({traceCount ?? 0} 步) →
          </button>
        )}
      </div>

      {/* ── 异常仲裁提示 ── */}
      {isFailed && task.escalated && (
        <div className="mt-2 rounded-lg border border-amber-400/40 bg-amber-500/[0.06] p-3 text-xs text-amber-600 dark:text-amber-400 space-y-1.5">
          <div className="font-medium flex items-center gap-1.5">
            <Scale className="h-3.5 w-3.5" />
            两轮评审未通过，已停止自动返工，转人工仲裁
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">评审意见见原对话：</span>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 underline underline-offset-2 hover:opacity-80 cursor-pointer"
              onClick={() =>
                task.origin_thread_id &&
                navigate({
                  to: "/chat",
                  search: { thread_id: task.origin_thread_id as string },
                })
              }
            >
              <ExternalLink className="h-3 w-3" />
              去仲裁处理 →
            </button>
          </div>
        </div>
      )}
      {isFailed && !task.escalated && (
        <div className="mt-2 rounded-lg border border-destructive/25 bg-destructive/[0.04] p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-xs text-destructive/90">
            {task.last_error
              ? `执行失败：${String(task.last_error).slice(0, 160)}`
              : "任务执行失败"}
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-3 text-xs text-destructive hover:text-destructive hover:border-destructive/50 cursor-pointer shrink-0"
            disabled={busy}
            onClick={rerun}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            重新执行
          </Button>
        </div>
      )}
    </div>
  )
}

/** 兼容导出：供执行流部分时间线引用使用 */
export function AttachmentStrip({ items }: { items: Attachment[] }) {
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
        ),
      )}
    </div>
  )
}
