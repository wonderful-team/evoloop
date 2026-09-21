/* ==========================================================================
   EvoLoop 自主值守工作台 · 节点卡片即页面内页组件 (DutyNodePageContent.tsx)
   嵌入在画布任务卡片节点内部，实现「节点原地放大为页面」的现场级工作体验：
   - 顶部导航：收起为卡片 (Esc)、#T-n 编号、标题、血统徽标、状态胶囊
   - 四问全景关系区：一屏回答 因谁而生 / 输入是谁 / 产出喂谁 / 结果谁背书
   - 左右双栏直接平移 v1 成熟组件：
     - 左栏：当前计划 (PlanPanel)
     - 右栏：执行过程与交付工作台 (ExecutionPanel)，未派发任务自动呈现成熟的待执行简报
   ========================================================================== */

import { useEffect, useMemo } from "react"
import {
  X,
  Wrench,
  AlertTriangle,
  Maximize2,
  Minimize2,
  ListTodo,
  ExternalLink,
} from "lucide-react"
import { useNavigate } from "@tanstack/react-router"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useChatStore } from "@/stores/chatStore"
import { PlanningService } from "@/client"
import { DEMO } from "../core/demoData"
import { getDemoPlan } from "../core/demoRuntime"
import type { DutyTask } from "../core/types"
import type { QueueTask } from "@/lib/tasksQueueApi"
import { PlanPanel } from "../detail/PlanPanel"
import { ExecutionPanel, TaskExecutionOverviewCard } from "../detail/ExecutionPanel"

interface DutyNodePageContentProps {
  task: DutyTask
  allTasks?: DutyTask[]
  stepIndex?: number
  onClose: () => void
  isFullscreen?: boolean
  onToggleFullscreen?: () => void
  onPickOption?: (taskId: string, index: number) => void
  onApprove?: (taskId: string, grantMode?: "once" | "always") => void
  onReject?: (taskId: string, reason?: string) => void
  onArbitrate?: (action: "retry_upstream" | "cancel_downstream" | "reopen_modified") => void
  onConfirmHitl?: (taskId: string, grantMode?: "once" | "always") => void
  onCancelHitl?: (taskId: string) => void
  onSubmitTextHitl?: (taskId: string, value: string) => void
  onSubmitChoiceHitl?: (taskId: string, choice: string) => void
  onSubmitMultiChoiceHitl?: (taskId: string, choices: string[]) => void
}

export const DutyNodePageContent = ({
  task,
  allTasks,
  onClose,
  isFullscreen,
  onToggleFullscreen,
}: DutyNodePageContentProps) => {
  const navigate = useNavigate()
  const qc = useQueryClient()

  /* 转换为与 v1 100% 兼容的 QueueTask 真实实体 */
  const queueTask = useMemo<QueueTask>(() => {
    if (task.rawQueueTask) return task.rawQueueTask as QueueTask
    return {
      id: task.id,
      task_no: task.taskNo,
      title: task.title,
      description: task.description,
      category: task.category,
      status: task.status,
      priority: task.priority,
      risk_level: task.riskLevel,
      source: task.source,
      dependencies: task.dependencies,
      last_thread_id: task.lastThreadId,
      project_id: task.projectId ?? undefined,
      artifacts: task.artifact
        ? [
            {
              id: task.artifact.id,
              stage: task.category,
              type: task.artifact.type,
              summary: task.artifact.summary,
              data: task.artifact.data as any,
            },
          ]
        : [],
    } as QueueTask
  }, [task])

  /* 上游依赖源任务（用于在 ExecutionPanel 待执行简报中展示依赖项信息） */
  const sourceTask = useMemo<QueueTask | null>(() => {
    if (!allTasks || !task.dependencies || task.dependencies.length === 0) return null
    const dep = allTasks.find((t) => t.id === task.dependencies[0])
    return (dep?.rawQueueTask as QueueTask) ?? null
  }, [allTasks, task.dependencies])

  /* 关联 Agent 提案列表 */
  const relatedProposals = useMemo<QueueTask[]>(() => {
    if (!allTasks) return []
    return allTasks
      .filter((t) => t.source === "agent_proposal" && t.status === "proposed")
      .map((t) => t.rawQueueTask as QueueTask)
      .filter(Boolean)
  }, [allTasks])

  /* 目标关联会话 ID（优先 lastThreadId，其次 sourceRefId） */
  const targetThreadId =
    task.lastThreadId ||
    (task.source === "chat" ? task.provenance.originMessageId : null)

  /* Esc 快捷键收起回卡片 */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  /* 查询本任务是否有执行计划项（无计划项时自动隐藏左栏并全宽展开执行轨迹） */
  const planQ = useQuery({
    queryKey: ["dutyPlan", targetThreadId],
    queryFn: async () =>
      DEMO
        ? (getDemoPlan(targetThreadId ?? null) as unknown as Awaited<ReturnType<typeof PlanningService.getPlan>>)
        : await PlanningService.getPlan({ threadId: targetThreadId as string }),
    enabled: DEMO || !!targetThreadId,
  })
  const planBody = planQ.data as unknown as {
    status?: string
    plan?: { steps?: Array<{ id: string; title: string; status: string }> }
  } | null
  const planSteps = planBody?.plan?.steps ?? []
  // 🌟 平滑加载：加载期间保持计划栏就位（由 PlanPanel 展示骨架），仅在确定无步骤项时才折叠为单栏，杜绝页面剧烈抖动
  const hasPlan = planQ.isLoading ? true : planSteps.length > 0

  const handleDataRefresh = () => {
    qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
  }

  return (
    <div
      className={`dc-page-inner ${isFullscreen ? "is-fullscreen" : ""}`}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* ── 页面顶部条：元数据、状态、接管会话、全屏与关闭 ── */}
      <header
        className="dc-page-header"
        onDoubleClick={(e) => {
          const target = e.target as HTMLElement
          if (!target.closest("button, a, input, select")) {
            onToggleFullscreen?.()
          }
        }}
      >
        <div className="dc-page-title-group">
          <span className="dc-badge-no">#T-{task.taskNo}</span>
          <span className="dc-page-title">{task.title}</span>

          <span className={`dc-badge dc-badge-${task.source}`}>
            {task.source === "chat"
              ? "💬 对话产生"
              : task.source === "agent_proposal"
              ? "🤖 Agent提案"
              : task.source === "cron"
              ? "⏰ 周期巡检"
              : "⛓ 依赖派生"}
          </span>

          <span className="dc-badge dc-badge-category">{task.category}</span>

          {task.signoff && (task.signoff.rejectCount ?? 0) > 0 && (
            <span className="dc-badge-reject">已打回 {task.signoff.rejectCount} 次</span>
          )}
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <span className={`dc-status-pill ${task.status}`}>
            {task.status === "completed"
              ? "✓ 监察评审通过"
              : task.status === "in_progress"
              ? "⟳ Agent 现场执行中"
              : task.status === "proposed"
              ? "💡 Agent 待确认提案"
              : task.status === "waiting_acceptance"
              ? "⏸ 等你商业拍板"
              : task.status === "confirm"
              ? "⏸ 资金安全授权"
              : task.status === "blocked"
              ? "🔒 上游断链锁定"
              : task.status === "failed"
              ? "⛔ 执行异常/打回"
              : "○ 待派发调度"}
          </span>

          {targetThreadId && (
            <button
              type="button"
              className="dc-open-chat-btn"
              onClick={(e) => {
                e.stopPropagation()
                useChatStore.getState().setThread(targetThreadId, task.projectId ?? null)
                navigate({ to: "/chat" })
              }}
              title="在对话面板中打开此任务并接管会话"
            >
              <ExternalLink size={12} />
              <span>接管会话</span>
            </button>
          )}

          {onToggleFullscreen && (
            <button
              type="button"
              className="dc-fullscreen-toggle-btn"
              onClick={(e) => {
                e.stopPropagation()
                onToggleFullscreen()
              }}
              title={isFullscreen ? "恢复到现有画布放大效果" : "扩展到整个右侧面板"}
            >
              {isFullscreen ? (
                <>
                  <Minimize2 size={13} />
                  <span>画布</span>
                </>
              ) : (
                <>
                  <Maximize2 size={13} />
                  <span>全屏</span>
                </>
              )}
            </button>
          )}

          <button
            className="dc-icon-btn"
            onClick={(e) => {
              e.stopPropagation()
              onClose()
            }}
            title="关闭卡片 (Esc)"
          >
            <X size={15} />
          </button>
        </div>
      </header>

      {/* ── 页面核心视口容器 ── */}
      <div className="dc-page-body">
        {/* ── ① 顶部横跨总览区：任务描述、步骤进度条、终态结果产物、最终回复全部完整置顶 ── */}
        <div className="dc-page-top-overview">
          <TaskExecutionOverviewCard
            task={queueTask}
            threadId={targetThreadId}
            onChanged={handleDataRefresh}
            onVerdictDone={handleDataRefresh}
          />
        </div>
        {/* ── 核心工作区：有计划时自适应展开左栏 (PlanPanel)，无计划时执行过程自动 100% 满宽展开 ── */}
        <div className={`dc-page-columns ${!hasPlan ? "no-plan" : ""}`}>
          {/* 左栏：仅在有步骤计划时展示 */}
          {hasPlan && (
            <div className="dc-timeline-panel animate-in fade-in slide-in-from-left-2 duration-300">
              <div className="dc-panel-head">
                <ListTodo size={13} />
                <span>
                  当前计划 ({planSteps.filter((s) => s.status === "completed").length}/{planSteps.length})
                </span>
              </div>
              <div className="dc-panel-content">
                <PlanPanel task={queueTask} />
              </div>
            </div>
          )}

          {/* 右栏：执行过程与交付工作台 */}
          <div className="dc-artifact-panel">
            <div className="dc-panel-head">
              <Wrench size={13} />
              <span>执行过程与交付工作台</span>
            </div>
            <div className="dc-artifact-view">
              <ExecutionPanel
                task={queueTask}
                sourceTask={sourceTask}
                relatedProposals={relatedProposals}
                hideNowCard={true}
                onChanged={handleDataRefresh}
                onConfirmed={handleDataRefresh}
                onVerdictDone={handleDataRefresh}
              />
            </div>
          </div>
        </div>

        {/* ====================================================================
           ★ 底部轻量关系与度量底栏 (四问全景 + 运行度量，无多余外框与标题)
           ==================================================================== */}
        <div className="mt-auto pt-2.5 border-t border-border/40 flex flex-wrap items-center justify-between gap-3 text-xs select-none">
          {/* 左侧：四问全景关系 */}
          <div className="flex items-center flex-wrap gap-x-4 gap-y-1 text-muted-foreground text-[11px] min-w-0">
            <span className="truncate max-w-[200px]" title={`因谁而生: ${task.provenance.sourceRef}`}>
              <span className="opacity-60">因谁而生:</span>{" "}
              <span className="text-foreground/90 font-medium">{task.provenance.sourceRef}</span>
            </span>
            <span className="truncate max-w-[240px]" title={`输入是谁: ${task.provenance.upstreamSummary}`}>
              <span className="opacity-60">输入:</span>{" "}
              <span className="text-foreground/90 font-medium">{task.provenance.upstreamSummary}</span>
            </span>
            <span className="truncate max-w-[220px]" title={`产出喂谁: ${task.provenance.downstreamTargets.join(" · ") || "终局闭环"}`}>
              <span className="opacity-60">产出:</span>{" "}
              <span className="text-foreground/90 font-medium">
                {task.provenance.downstreamTargets.join(" · ") || "终局闭环"}
              </span>
            </span>
            <span className="truncate max-w-[200px]" title={`结果谁背书: ${task.provenance.endorsement}`}>
              <span className="opacity-60">背书:</span>{" "}
              <span className="text-foreground/90 font-medium">{task.provenance.endorsement}</span>
            </span>
          </div>

          {/* 右侧：全局度量统计指标（Tokens、耗时、异常） */}
          <div className="flex items-center gap-x-3 text-[11px] font-mono text-muted-foreground tabular-nums shrink-0 ml-auto">
            {(queueTask.run?.tool_errors ?? 0) > 0 ? (
              <span className="inline-flex items-center gap-1 text-destructive font-semibold">
                <AlertTriangle className="h-3 w-3" />
                异常 · {queueTask.run?.tool_errors}
              </span>
            ) : (
              <span className="text-muted-foreground/50">无异常</span>
            )}

            <span className="h-2.5 w-px bg-border/60" />

            <span>
              <span className="opacity-60 font-sans">燃耗:</span>{" "}
              <span className="text-primary font-medium">
                {(
                  (queueTask.run?.input_tokens ?? 0) +
                  (queueTask.run?.output_tokens ?? 0)
                ).toLocaleString()} Tokens
              </span>
            </span>

            {(queueTask.run?.llm_calls ?? 0) > 0 && (
              <span>
                <span className="opacity-60 font-sans">LLM:</span>{" "}
                <span className="text-foreground font-medium">{queueTask.run?.llm_calls}</span>
              </span>
            )}

            {queueTask.elapsed_sec != null && (
              <span>
                <span className="opacity-60 font-sans">耗时:</span>{" "}
                <span className="text-foreground font-medium">{queueTask.elapsed_sec}s</span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
