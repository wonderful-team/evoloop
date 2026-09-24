import {useQuery} from "@tanstack/react-query"
import {motion} from "framer-motion"
import {CheckCircle2, Circle, Loader2, PauseCircle} from "lucide-react"

import {PlanningService} from "@/client"
import type {QueueTask} from "@/lib/tasksQueueApi"
import {DEMO} from "../core/demoData"
import {getDemoPlan} from "../core/demoRuntime"

/** Current plan steps for the selected task's thread (1:1 with the task). */
export function PlanPanel({
  task,
  suspended = false,
}: {
  task: QueueTask
  suspended?: boolean
}) {
  const threadId = task.last_thread_id

  const { data, isLoading } = useQuery({
    queryKey: ["dutyPlan", threadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(threadId) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: threadId as string }),
    enabled: DEMO || !!threadId,
  })

  if (!threadId) {
    return (
      <div className="text-xs text-muted-foreground">
        任务尚未派发执行（无工作台）
      </div>
    )
  }
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> 加载计划…
      </div>
    )
  }

  const body = data as unknown as {
    status?: string
    plan?: { title?: string; steps?: { id: string; title: string; status: string; result?: string | null }[] }
  } | null
  const steps = body?.plan?.steps ?? []

  if (body?.status === "no_plan" || steps.length === 0) {
    return (
      <div className="text-xs text-muted-foreground">
        本任务暂无计划（Agent 会在执行时用 plan 工具建立）
      </div>
    )
  }

  const done = steps.filter((s) => s.status === "completed").length
  const percent = steps.length > 0 ? Math.round((done / steps.length) * 100) : 0
  const isAllDone = done === steps.length && steps.length > 0

  return (
    <div className="space-y-3 select-none">
      {/* ── 计划标题与动态进度条 ── */}
      <div className="space-y-1.5 pb-0.5">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-semibold text-foreground/90 truncate" title={body?.plan?.title}>
            {body?.plan?.title}
          </span>
          <span className="text-muted-foreground font-mono text-[11px] font-semibold shrink-0">
            {done}/{steps.length}
            <span className="ml-1 text-[10.5px] opacity-75">({percent}%)</span>
          </span>
        </div>
        {/* 精致动态步骤进度条 */}
        <div className="w-full h-1.5 rounded-full bg-muted/80 overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${
              isAllDone ? "bg-emerald-500" : "bg-primary"
            }`}
            initial={{ width: 0 }}
            animate={{ width: `${percent}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      </div>

      {/* ── 计划步骤列表 ── */}
      <div className="space-y-1.5">
        {steps.map((s) => (
        <motion.div
          key={s.id}
          layout
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="flex items-start gap-2 text-xs"
        >
          {s.status === "completed" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-green-600 shrink-0 mt-0.5" />
          ) : s.status === "in_progress" ? (
            suspended ? (
              <PauseCircle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
            ) : (
              <Loader2 className="h-3.5 w-3.5 text-primary animate-spin shrink-0 mt-0.5" />
            )
          ) : (
            <Circle className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <div className={`break-words line-clamp-2 ${s.status === "completed" ? "line-through text-muted-foreground" : ""}`}>
              {s.title}
            </div>
            {s.status === "completed" && s.result && (
              <div className="text-muted-foreground truncate text-[11px]">
                {s.result.slice(0, 60)}
              </div>
            )}
          </div>
        </motion.div>
      ))}
      </div>
    </div>
  )
}

/** Status chip row for a plan summary line (compact mode for cards). */
export function PlanProgressInline({
  task,
  enabled = true,
}: {
  task: QueueTask
  /** N+1 防护：卡片批量渲染时仅活任务（in_progress/等审批）拉计划；
   *  其余状态由 useQuery 缓存兜底（详情页已请求过的仍会渲染） */
  enabled?: boolean
}) {
  const threadId = task.last_thread_id
  const { data } = useQuery({
    queryKey: ["dutyPlan", threadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(threadId) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: threadId as string }),
    enabled: (DEMO || !!threadId) && enabled,
  })
  const body = data as unknown as {
    plan?: { steps?: { status: string }[] }
  } | null
  const steps = body?.plan?.steps ?? []
  if (steps.length === 0) return null
  const done = steps.filter((s) => s.status === "completed").length
  const pct = Math.round((done / steps.length) * 100)
  return (
    <div className="flex items-center gap-2 select-none">
      <div className="flex-1 h-1 rounded-full bg-muted/80 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            done === steps.length ? "bg-emerald-500" : "bg-primary"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] font-mono text-muted-foreground/80 shrink-0 font-medium">
        {done}/{steps.length} ({pct}%)
      </span>
    </div>
  )
}
