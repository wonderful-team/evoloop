import { useQueryClient } from "@tanstack/react-query"
import { ArrowDown, CircleDashed, ShieldAlert } from "lucide-react"

import type { QueueTask } from "@/lib/tasksQueueApi"

/**
 * 待执行任务简报卡（pending 任务的右栏首屏）。
 *
 * pending 没有执行线程，原右栏只有一句"尚未派发执行"——但任务在建任务时
 * 写好的使用场景/目标/验收标准与依赖链恰恰是执行前最该看的信息。
 */
export function PendingTaskBrief({ task }: { task: QueueTask }) {
  const qc = useQueryClient()
  const deps = task.dependencies ?? []
  // 从看板缓存解析依赖任务的编号与状态（不额外发请求）
  const queueData = qc.getQueryData<{ items?: QueueTask[] }>([
    "dutyQueue",
    task.project_id ?? "global",
  ])
  const all = queueData?.items ?? []
  const depTasks = deps
    .map((id) => all.find((t) => t.id === id))
    .filter(Boolean) as QueueTask[]

  return (
    <div className="mt-2 rounded-lg border border-border/60 bg-muted/20 p-3 space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <CircleDashed className="h-3.5 w-3.5" />
        待执行简报 · 值守开启后按依赖链派发
      </div>

      {task.description && (
        <div className="text-[12px] leading-relaxed text-foreground/90 break-words whitespace-pre-wrap">
          {task.description}
        </div>
      )}

      {depTasks.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-medium text-muted-foreground flex items-center gap-1">
            <ArrowDown className="h-3 w-3" />
            上游依赖（{depTasks.length}）
          </div>
          <div className="space-y-1">
            {depTasks.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-2 text-[11px] rounded bg-background/60 px-2 py-1"
              >
                <span className="font-mono text-[10px] text-muted-foreground/70">
                  {t.task_no != null ? `#T-${t.task_no}` : t.id.slice(0, 8)}
                </span>
                <span className="min-w-0 truncate text-foreground/80">
                  {t.title}
                </span>
                <span className="flex-1" />
                <span
                  className={`shrink-0 text-[10px] px-1.5 rounded ${
                    t.status === "completed"
                      ? "bg-green-500/10 text-green-600"
                      : t.status === "failed"
                        ? "bg-destructive/10 text-destructive"
                        : "bg-muted text-muted-foreground"
                  }`}
                >
                  {t.status === "pending"
                    ? "待执行"
                    : t.status === "completed"
                      ? "已完成"
                      : t.status === "failed"
                        ? "失败"
                        : t.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(deps.length > 0 || task.risk_level) && (
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground/70">
          {task.risk_level && (
            <span className="flex items-center gap-1">
              <ShieldAlert className="h-3 w-3" />
              风险档 {task.risk_level}
              {task.risk_level === "T1" || task.risk_level === "T2"
                ? "· 执行涉及资金/敏感操作将转提案等确认"
                : ""}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
