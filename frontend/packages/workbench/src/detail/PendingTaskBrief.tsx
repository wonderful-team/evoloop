import {useQueryClient} from "@tanstack/react-query"
import {ArrowDown, Clock, FileText, ShieldAlert} from "lucide-react"

import type {QueueTask} from "@/lib/tasksQueueApi"
import {MessageContent} from "@/components/Chat/MessageContent.tsx";

/**
 * 待执行任务详情区（待派发任务的首屏展示）。
 * 明确呈现任务描述、目标指令、前置依赖关系与调度规则，杜绝晦涩行话。
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
    <div className="w-full space-y-4 select-none">
      {/* ── 顶栏：清晰标明「任务描述与执行指令」与就绪状态 ── */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <FileText className="h-4 w-4 text-primary shrink-0" />
          <span>任务描述与执行指令</span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground bg-muted/50 px-2.5 py-1 rounded-full border border-border/40">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse shrink-0" />
          <span>待派发调度 · 开启自主值守后将按链路推进</span>
        </div>
      </div>

      {/* ── 核心内容：任务目标与描述全文 ── */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-medium text-muted-foreground">
          任务目标与需求详情:
        </div>
        {task.description ? (
          <div className="rounded-xl border border-border/70 bg-card p-4 text-[12.5px] leading-relaxed text-foreground/90 break-words whitespace-pre-wrap font-sans selection:bg-primary/20 shadow-2xs select-text">
              <MessageContent content={task.description} />
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border/60 p-6 text-xs text-muted-foreground/70 italic text-center">
            （该任务未填写补充描述指令）
          </div>
        )}
      </div>

      {/* ── 前置依赖任务列表 ── */}
      {depTasks.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="text-xs font-semibold text-foreground/80 flex items-center gap-1.5">
            <ArrowDown className="h-3.5 w-3.5 text-primary shrink-0" />
            <span>前置依赖任务 ({depTasks.length})</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {depTasks.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-2 text-xs rounded-lg border border-border/60 bg-background/60 p-2.5 hover:bg-muted/30 transition-colors"
              >
                <span className="font-mono text-[11px] font-semibold text-primary shrink-0">
                  {t.task_no != null ? `#T-${t.task_no}` : t.id.slice(0, 8)}
                </span>
                <span className="min-w-0 truncate text-foreground/90 font-medium">
                  {t.title}
                </span>
                <span className="flex-1" />
                <span
                  className={`shrink-0 text-[10.5px] px-2 py-0.5 rounded-full font-medium ${
                    t.status === "completed"
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                      : t.status === "failed"
                      ? "bg-destructive/10 text-destructive border border-destructive/20"
                      : "bg-muted text-muted-foreground border border-border/40"
                  }`}
                >
                  {t.status === "pending"
                    ? "待执行"
                    : t.status === "completed"
                    ? "已就绪"
                    : t.status === "failed"
                    ? "依赖异常"
                    : t.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 治理与调度属性底栏 ── */}
      <div className="flex flex-wrap items-center gap-4 pt-3 text-[11px] text-muted-foreground border-t border-border/40">
        {task.risk_level && (
          <span className="inline-flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500 shrink-0" />
            <span>风险等级:</span>
            <span className="font-medium text-foreground">{task.risk_level}</span>
            {task.risk_level === "T1" || task.risk_level === "T2" ? (
              <span className="text-amber-500/90 font-sans">（涉及资金或高危敏感操作，执行时需人工拍板）</span>
            ) : null}
          </span>
        )}
        {task.trigger_spec && (
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5 text-primary shrink-0" />
            <span>调度规则:</span>
            <span className="font-medium text-foreground">{task.trigger_spec}</span>
          </span>
        )}
      </div>
    </div>
  )
}
