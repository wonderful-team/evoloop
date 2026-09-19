import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import {
  BadgeCheck,
  CheckCircle2,
  ExternalLink,
  FileText,
  MessageSquareX,
  Package,
  Play,
  XCircle,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { TasksQueueApi, type QueueTask } from "@/lib/tasksQueueApi"
import { MessageContent } from "@/components/Chat/MessageContent"
import type { Attachment, ArtifactView } from "./types"

export function ResultCard({
  task,
  onVerdictDone,
  finalText,
  finalAttachments,
  artifacts,
  threadId,
  onChanged,
}: {
  task: QueueTask
  onVerdictDone?: (landInTab: "done" | "active") => void
  finalText: string
  finalAttachments: Attachment[]
  artifacts: ArtifactView[]
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
      onVerdictDone?.("done")
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
        {finalText ? (
          <div className="text-xs leading-relaxed break-words [&_table]:my-2 [&_table]:w-full [&_table]:text-[11px] [&_th]:border [&_th]:border-border/60 [&_th]:bg-muted/50 [&_th]:px-1.5 [&_th]:py-1 [&_td]:border [&_td]:border-border/40 [&_td]:px-1.5 [&_td]:py-1 [&_img]:max-h-40 [&_img]:rounded-md">
            <MessageContent content={finalText} />
          </div>
        ) : (
          <div className="text-xs text-muted-foreground/60">
            （无最终回复记录）
          </div>
        )}
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
            {artifacts.map((artifact, i) => (
              <div key={artifact.id ?? i}>
                <div className="text-[11px] font-medium text-muted-foreground">
                  {[artifact.stage, artifact.type].filter(Boolean).join(" · ") || "运行产出"}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {artifact.summary.slice(0, 300)}
                </div>
                {artifact.data ? (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-[10px] text-muted-foreground/70 hover:text-foreground">
                      展开数据
                    </summary>
                    <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted/40 p-1.5 text-[10px] leading-relaxed">
                      {JSON.stringify(artifact.data, null, 2)}
                    </pre>
                  </details>
                ) : null}
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
        )
      )}
    </div>
  )
}

