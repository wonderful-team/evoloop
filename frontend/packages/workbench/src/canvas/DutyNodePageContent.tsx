/* ==========================================================================
   EvoLoop 自主值守工作台 · 节点卡片即页面内页组件 (DutyNodePageContent.tsx)
   嵌入在画布任务卡片节点内部，实现「节点原地放大为页面」的现场级工作体验：
   - 顶部导航：收起为卡片 (Esc)、#T-n 编号、标题、血统徽标、状态胶囊
   - 四问全景关系区：一屏回答 因谁而生 / 输入是谁 / 产出喂谁 / 结果谁背书
   - 左右双栏直接平移 v1 成熟组件：
     - 左栏：当前计划 (PlanPanel)
     - 右栏：执行过程与交付工作台 (ExecutionPanel)，未派发任务自动呈现成熟的待执行简报
   ========================================================================== */

import { MarkdownText } from "@evoloop/shared/components/markdown/MarkdownText"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  AlertTriangle,
  Ban,
  Edit3,
  ExternalLink,
  FileText,
  ListTodo,
  Maximize2,
  Minimize2,
  RotateCcw,
  Square,
  X,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { AgentService, PlanningService } from "@/client"
import { type QueueTask, TasksQueueApi } from "@/lib/tasksQueueApi"
import { useChatStore } from "@/stores/chatStore"
import { DEMO } from "../core/demoData"
import { getDemoPlan } from "../core/demoRuntime"
import { statusMeta } from "../core/statusMeta"
import type { DutyTask } from "../core/types"
import { ExecutionPanel } from "../detail/ExecutionPanel"
import { PlanPanel } from "../detail/PlanPanel"
import { DutyHitlInputCard, type DutyHitlItem } from "./DutyHitlInputCard"

interface DutyNodePageContentProps {
  task: DutyTask
  allTasks?: DutyTask[]
  stepIndex?: number
  onClose: () => void
  isFullscreen?: boolean
  onToggleFullscreen?: () => void
  onApprove?: (taskId: string, grantMode?: "once" | "always") => void
  /** proposed 提案确认（加入执行队列）——此前 UI 无确认入口，唯一出口是裸 API */
  onConfirmProposal?: (taskId: string) => void | Promise<void>
  onReject?: (taskId: string, reason?: string) => void
  onArbitrate?: (
    action: "retry_upstream" | "cancel_downstream" | "reopen_modified",
    taskId?: string,
    modifiedParams?: { description?: string },
  ) => void | Promise<void>
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
  onConfirmProposal,
  onArbitrate,
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
    if (!allTasks || !task.dependencies || task.dependencies.length === 0)
      return null
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

  /* 稳健解析任务血统与四问关系，提供强类型防空兜底，杜绝 undefined 异常 */
  const provenance = useMemo(() => {
    const raw = task.provenance || (task as any).fourQuestions
    return {
      sourceRef:
        raw?.sourceRef ||
        (task.source === "chat" ? "用户对话派发" : "自主值守调度"),
      upstreamSummary: raw?.upstreamSummary || "根任务 · 独立启动",
      downstreamTargets: Array.isArray(raw?.downstreamTargets)
        ? raw.downstreamTargets
        : [],
      endorsement: raw?.endorsement || "自动化安全审计",
      originMessageId: raw?.originMessageId,
    }
  }, [task])

  /* 目标关联会话 ID（优先 lastThreadId，其次 originMessageId） */
  const targetThreadId =
    task.lastThreadId ||
    (task.source === "chat" ? provenance.originMessageId : null)

  /* Canvas→Chat 血统回跳：origin 线程 id（消息转化类任务 provenance.kind==="message"
     的 ref 即对话线程；评审/代发链路另存 origin_thread_id） */
  const originThreadId = useMemo(() => {
    const raw = queueTask as unknown as {
      origin_thread_id?: string | null
      provenance?: { kind?: string; ref?: string } | null
    }
    if (raw.origin_thread_id) return raw.origin_thread_id
    const pv = raw.provenance
    if (
      pv &&
      typeof pv === "object" &&
      pv.kind === "message" &&
      typeof pv.ref === "string"
    ) {
      return pv.ref
    }
    return null
  }, [queueTask])

  const [isStopping, setIsStopping] = useState(false)
  const handleStopTask = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isStopping) return
    setIsStopping(true)
    try {
      if (targetThreadId) {
        try {
          await AgentService.stopChat({
            requestBody: { thread_id: targetThreadId, message: "" },
          })
        } catch {}
      }
      await TasksQueueApi.update(task.id, { status: "cancelled" })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      if (targetThreadId) {
        await qc.invalidateQueries({ queryKey: ["dutyExec", targetThreadId] })
      }
      handleDataRefresh()
    } catch (err) {
      console.error("Failed to stop duty task:", err)
    } finally {
      setIsStopping(false)
    }
  }

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
        ? (getDemoPlan(targetThreadId ?? null) as unknown as Awaited<
            ReturnType<typeof PlanningService.getPlan>
          >)
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
  const donePlanSteps = planSteps.filter((s) => s.status === "completed").length
  const planPercent =
    planSteps.length > 0
      ? Math.round((donePlanSteps / planSteps.length) * 100)
      : 0

  const handleDataRefresh = () => {
    qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
    if (targetThreadId) {
      qc.invalidateQueries({ queryKey: ["dutyExec", targetThreadId] })
    }
  }

  /* 本任务的挂起 HITL：全屏页底部输入 dock 被隐藏，审批入口必须在页内
     自渲染（否则选中等审批节点进全屏后用户无从应答——审计断层 #5.1） */
  const hitlQ = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
    enabled: !DEMO,
  })
  const taskHitl = useMemo<DutyHitlItem | null>(() => {
    const items = (hitlQ.data?.items ?? []) as DutyHitlItem[]
    return (
      items.find(
        (h) =>
          h.task_id === task.id ||
          (targetThreadId && h.thread_id === targetThreadId),
      ) ?? null
    )
  }, [hitlQ.data, task.id, targetThreadId])

  /* 人工仲裁状态与交互逻辑 */
  const [isModifying, setIsModifying] = useState(false)
  const [modifyDescription, setModifyDescription] = useState(
    task.description || "",
  )
  const [isArbitrating, setIsArbitrating] = useState(false)

  useEffect(() => {
    setModifyDescription(task.description || "")
  }, [task.description])

  const isArbitrationNeeded =
    task.status === "failed" ||
    task.status === "blocked" ||
    Boolean(queueTask.escalated) ||
    Boolean(task.arbitration)

  const upstreamTasks = useMemo(() => {
    if (!allTasks || !task.dependencies) return []
    return allTasks.filter((t) => task.dependencies.includes(t.id))
  }, [allTasks, task.dependencies])

  const failedUpstream = useMemo(() => {
    return upstreamTasks.filter(
      (t) =>
        t.status === "failed" ||
        t.status === "blocked" ||
        t.status === "cancelled",
    )
  }, [upstreamTasks])

  const downstreamTasks = useMemo(() => {
    if (!allTasks) return []
    return allTasks.filter((t) => t.dependencies?.includes(task.id))
  }, [allTasks, task.id])

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
          <span
            className="dc-page-title"
            title={task.description || task.title}
          >
            {task.title}
          </span>

          <span className={`dc-badge dc-badge-${task.source}`}>
            {task.source === "chat"
              ? "💬 对话产生"
              : task.source === "agent_proposal"
                ? "🤖 Agent提案"
                : task.source === "cron"
                  ? "⏰ 周期巡检"
                  : task.source === "event"
                    ? "🔗 外部事件"
                    : task.source === "chain"
                      ? "⛓ 依赖派生"
                      : "👤 用户创建"}
          </span>

          {task.category && (
            <span className="dc-badge dc-badge-category">{task.category}</span>
          )}

          {task.signoff && (task.signoff.rejectCount ?? 0) > 0 && (
            <span className="dc-badge-reject">
              已打回 {task.signoff.rejectCount} 次
            </span>
          )}
        </div>

        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          {/* 状态胶囊：词汇/图形统一走 statusMeta（节点页仅加长文案后缀） */}
          <span className={`dc-status-pill ${task.status}`}>
            {statusMeta(task.status).glyph} {statusMeta(task.status).label}
            {task.status === "in_progress" && "（Agent 现场执行）"}
            {task.status === "proposed" && "（Agent 待确认）"}
            {task.status === "waiting_acceptance" && "（等你商业拍板）"}
            {task.status === "completed" && "（监察评审通过）"}
            {task.status === "failed" && "（执行异常/打回）"}
            {task.status === "cancelled" && "（不再执行）"}
          </span>

          {task.status === "proposed" && onConfirmProposal && (
            <button
              type="button"
              className="dc-stop-btn"
              data-test="confirm-proposal"
              onClick={() => void onConfirmProposal(task.id)}
              title="确认提案：任务加入执行队列，值守按依赖顺序派发"
            >
              <span>✓ 确认提案，加入执行队列</span>
            </button>
          )}

          {task.status === "in_progress" && (
            <button
              type="button"
              className="dc-stop-btn"
              disabled={isStopping}
              onClick={handleStopTask}
              title="立即终止正在执行的任务与后台 Agent"
            >
              <Square size={11} className="fill-current" />
              <span>{isStopping ? "终止中…" : "终止任务"}</span>
            </button>
          )}

          {(targetThreadId || originThreadId) && (
            <button
              type="button"
              className="dc-open-chat-btn"
              onClick={(e) => {
                e.stopPropagation()
                // 单一会话入口（替代此前"接管会话/来源回跳"两个叠加入口）：
                // 执行中 → 执行线程（接管指挥）；其余 → 来源对话（需求与
                // 评审语境，锚点高亮）。目标重合时走原 setThread 直开。
                const goExecutor =
                  task.status === "in_progress" && !!targetThreadId
                const target =
                  goExecutor
                    ? targetThreadId
                    : originThreadId || targetThreadId
                if (!target) return
                if (target === originThreadId && originThreadId !== targetThreadId) {
                  try {
                    sessionStorage.setItem("chat:focus-thread", target)
                  } catch {
                    // ignore
                  }
                  navigate({
                    to: "/chat",
                    search: { thread_id: target } as any,
                  })
                } else {
                  useChatStore
                    .getState()
                    .setThread(target, task.projectId ?? null)
                  navigate({ to: "/chat" })
                }
              }}
              title={
                task.status === "in_progress" && targetThreadId
                  ? "在对话面板中打开执行会话并接管"
                  : "在对话面板中打开来源对话（需求与评审现场）"
              }
            >
              <ExternalLink size={12} />
              <span>
                {task.status === "in_progress" && targetThreadId
                  ? "接管会话"
                  : "打开会话"}
              </span>
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
              title={
                isFullscreen ? "恢复到现有画布放大效果" : "扩展到整个右侧面板"
              }
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

      {/* ── 顶栏全景进度指示条 (当有计划步骤时呈现，清晰指示任务整体完成度) ── */}
      {planSteps.length > 0 && (
        <div className="w-full h-[2.5px] bg-border/40 overflow-hidden shrink-0">
          <div
            className={`h-full transition-all duration-500 ease-out ${
              task.status === "completed" || donePlanSteps === planSteps.length
                ? "bg-emerald-500"
                : task.status === "failed"
                  ? "bg-destructive"
                  : "bg-primary"
            }`}
            style={{ width: `${planPercent}%` }}
          />
        </div>
      )}

      {/* ── 任务描述栏（markdown 渲染，完整展开不折叠） ── */}
      {task.description && (hasPlan || Boolean(targetThreadId)) && (
        <div className="dc-task-desc-strip">
          <div className="dc-desc-prefix">
            <FileText size={12} className="text-primary shrink-0" />
            <span>任务描述:</span>
          </div>
          <div className="dc-desc-content">
            {/* 任务描述是 Agent 可执行指令，常带 markdown 结构——shared 轻量
                渲染（GFM autolink + URL 白名单），不再裸文本拍平 */}
            <MarkdownText content={task.description} />
          </div>
        </div>
      )}

      {/* ── 页面核心视口容器 ── */}
      <div className="dc-page-body">
        {/* ★ 人工仲裁控制台（当任务阻断、失败、监察熔断或需要仲裁介入时常驻展示） */}
        {isArbitrationNeeded && (
          <div className="dc-governance-box arbitration shrink-0 mb-1 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-rose-500/15 flex items-center justify-center text-rose-600 shrink-0 mt-0.5">
                  <AlertTriangle size={15} />
                </div>
                <div>
                  <div className="text-xs font-bold text-rose-700 flex items-center flex-wrap gap-2">
                    <span>执行阻断 · 人工仲裁控制台</span>
                    {queueTask.escalated && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 font-semibold border border-rose-200">
                        监察评审未收敛 (2轮驳回)
                      </span>
                    )}
                    {task.status === "blocked" && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold border border-amber-200">
                        上游断链阻断
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                    {queueTask.escalated
                      ? "本任务在监察评审中经历连续 2 轮驳回未收敛，系统自主重试已熔断挂起，需由人工仲裁裁定走向。"
                      : queueTask.last_error
                        ? `阻断原因: ${queueTask.last_error}`
                        : task.status === "blocked"
                          ? "前序依赖任务执行异常，本任务已挂起等待前序决策恢复。"
                          : "任务执行异常中断，已暂停后续自动化流转。"}
                  </div>
                </div>
              </div>

              {/* 去原对话查看完整上下文链接 */}
              {originThreadId && (
                <button
                  type="button"
                  className="text-[11px] text-rose-600 hover:text-rose-700 hover:underline shrink-0 flex items-center gap-1 font-medium mt-0.5"
                  onClick={() => {
                    sessionStorage.setItem("chat:focus-thread", originThreadId)
                    navigate({
                      to: "/chat",
                      search: { thread_id: originThreadId } as any,
                    })
                  }}
                  title="在对话面板中打开来源现场查看完整上下文"
                >
                  <span>查看对话现场</span>
                  <ExternalLink size={11} />
                </button>
              )}
            </div>

            {/* DAG 影响诊断与流向统计 */}
            <div className="mt-2.5 pt-2 border-t border-rose-200/60 flex items-center justify-between text-[11px] text-muted-foreground">
              <div className="flex items-center gap-4">
                <span>
                  前序依赖:{" "}
                  <strong className="text-foreground">
                    {upstreamTasks.length} 个
                    {failedUpstream.length > 0 &&
                      ` (${failedUpstream.length} 异常)`}
                  </strong>
                </span>
                <span>
                  下游影响:{" "}
                  <strong className="text-foreground">
                    {downstreamTasks.length} 个子任务受阻
                  </strong>
                </span>
              </div>
              <span className="text-[10px] opacity-75">
                执行仲裁后调度引擎将级联推导 DAG 拓扑状态
              </span>
            </div>

            {/* 仲裁三键操作区 */}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isArbitrating}
                className="h-7 px-3 rounded-md bg-rose-600 hover:bg-rose-700 text-white text-[11px] font-medium transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-50"
                onClick={async () => {
                  setIsArbitrating(true)
                  try {
                    await onArbitrate?.("retry_upstream", task.id)
                  } finally {
                    setIsArbitrating(false)
                  }
                }}
                title="重新触发前序依赖节点执行，清空本节点阻断"
              >
                <RotateCcw size={12} />
                <span>重跑上游</span>
              </button>

              <button
                type="button"
                disabled={isArbitrating}
                className="h-7 px-3 rounded-md bg-white hover:bg-rose-50 border border-rose-300 text-rose-700 text-[11px] font-medium transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-50"
                onClick={async () => {
                  setIsArbitrating(true)
                  try {
                    await onArbitrate?.("cancel_downstream", task.id)
                  } finally {
                    setIsArbitrating(false)
                  }
                }}
                title="终止后续受阻依赖子任务，避免级联资源浪费"
              >
                <Ban size={12} />
                <span>截断下游</span>
              </button>

              <button
                type="button"
                disabled={isArbitrating}
                className="h-7 px-3 rounded-md bg-white hover:bg-muted border border-border text-foreground text-[11px] font-medium transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-50"
                onClick={() => setIsModifying((prev) => !prev)}
                title="微调任务参数/提示词并重新激活排队"
              >
                <Edit3 size={12} />
                <span>{isModifying ? "取消改参" : "改参重开"}</span>
              </button>
            </div>

            {/* 改参微调输入抽屉 */}
            {isModifying && (
              <div className="mt-3 pt-3 border-t border-rose-200/60 animate-in fade-in duration-200">
                <div className="text-[11px] font-medium text-foreground mb-1.5">
                  微调任务执行指令 / 需求参数:
                </div>
                <textarea
                  className="w-full h-20 p-2 text-xs rounded-md bg-white border border-rose-200 focus:outline-none focus:ring-1 focus:ring-rose-500 font-mono resize-y text-foreground"
                  value={modifyDescription}
                  onChange={(e) => setModifyDescription(e.target.value)}
                  placeholder="输入针对此任务的补充修正指令或调整后的参数描述..."
                />
                <div className="mt-2 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    className="h-6 px-2.5 rounded text-[11px] text-muted-foreground hover:bg-rose-100/50"
                    onClick={() => setIsModifying(false)}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={isArbitrating}
                    className="h-6 px-3 rounded bg-primary text-primary-foreground text-[11px] font-medium hover:bg-primary/90 disabled:opacity-50"
                    onClick={async () => {
                      setIsArbitrating(true)
                      try {
                        await onArbitrate?.("reopen_modified", task.id, {
                          description: modifyDescription,
                        })
                        setIsModifying(false)
                      } finally {
                        setIsArbitrating(false)
                      }
                    }}
                  >
                    保存并重新排队
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── 核心工作区：左栏计划与血统，右栏成果与执行流 ── */}
        <div className={`dc-page-columns ${!hasPlan ? "no-plan" : ""}`}>
          {/* 左栏：仅在有步骤计划时展示 */}
          {hasPlan && (
            <div className="dc-timeline-panel animate-in fade-in slide-in-from-left-2 duration-300">
              <div className="dc-panel-head">
                <ListTodo size={13} />
                <span>
                  当前计划 ({donePlanSteps}/{planSteps.length})
                </span>
                {planSteps.length > 0 && (
                  <span className="ml-auto font-mono text-[11px] text-primary font-semibold">
                    {planPercent}%
                  </span>
                )}
              </div>
              <div className="dc-panel-content">
                <PlanPanel task={queueTask} />
              </div>
            </div>
          )}

          {/* 右栏：执行流与成果工作台 (核心要素：过程与结果) */}
          <div className="dc-artifact-panel">
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

            {/* 🌟 全屏模式专属：底部常驻待审批决策卡片（对齐聊天输入框上方心智，绝不遮挡顶部描述与左侧计划） */}
            {isFullscreen && taskHitl && (
              <div className="shrink-0 pt-3 border-t border-border/40 animate-in fade-in slide-in-from-bottom-2 duration-200">
                <DutyHitlInputCard
                  hitl={taskHitl}
                  onResolved={async () => {
                    handleDataRefresh()
                    await qc.invalidateQueries({ queryKey: ["dutyHitl"] })
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* ====================================================================
           ★ 附加信息极简底栏 (输入、输出、归属 + 运行统计度量)
           单行平铺，极简半透明，无外框外壳，永不抢占主业务视口
           ==================================================================== */}
        <div className="mt-auto pt-2 pb-0.5 border-t border-border/40 flex flex-wrap items-center justify-between gap-3 text-[11px] text-muted-foreground/80 select-none shrink-0">
          {/* 左侧：输入/输出与血统归属 */}
          <div className="flex items-center flex-wrap gap-x-4 gap-y-1 min-w-0">
            <span
              className="truncate max-w-[200px]"
              title={`来源: ${provenance.sourceRef}`}
            >
              <span className="opacity-60">来源:</span>{" "}
              <span className="text-foreground/90 font-medium">
                {provenance.sourceRef}
              </span>
            </span>
            {provenance.upstreamSummary &&
              provenance.upstreamSummary !== "根任务 · 独立启动" && (
                <span
                  className="truncate max-w-[220px]"
                  title={`输入: ${provenance.upstreamSummary}`}
                >
                  <span className="opacity-60">输入:</span>{" "}
                  <span className="text-foreground/90 font-medium">
                    {provenance.upstreamSummary}
                  </span>
                </span>
              )}
            {provenance.downstreamTargets.length > 0 &&
              provenance.downstreamTargets[0] !== "终局闭环 · 产物反哺资产" && (
                <span
                  className="truncate max-w-[220px]"
                  title={`流向: ${provenance.downstreamTargets.join(" · ")}`}
                >
                  <span className="opacity-60">流向:</span>{" "}
                  <span className="text-foreground/90 font-medium">
                    {provenance.downstreamTargets.join(" · ")}
                  </span>
                </span>
              )}
            <span
              className="truncate max-w-[200px]"
              title={`背书: ${provenance.endorsement}`}
            >
              <span className="opacity-60">背书:</span>{" "}
              <span className="text-foreground/90 font-medium">
                {provenance.endorsement}
              </span>
            </span>
          </div>

          {/* 右侧：统计度量指标 (Tokens、耗时、异常) */}
          <div className="flex items-center gap-x-3 text-[11px] font-mono text-muted-foreground tabular-nums shrink-0 ml-auto">
            {(queueTask.run?.tool_errors ?? 0) > 0 && (
              <span className="inline-flex items-center gap-1 text-destructive font-semibold">
                <AlertTriangle className="h-3 w-3" />
                异常 · {queueTask.run?.tool_errors}
              </span>
            )}
            {((queueTask.run?.input_tokens ?? 0) +
              (queueTask.run?.output_tokens ?? 0) >
              0 ||
              queueTask.elapsed_sec != null) && (
              <>
                {(queueTask.run?.input_tokens ?? 0) +
                  (queueTask.run?.output_tokens ?? 0) >
                  0 && (
                  <span>
                    <span className="opacity-60 font-sans">燃耗:</span>{" "}
                    <span className="text-foreground/90 font-medium">
                      {(
                        (queueTask.run?.input_tokens ?? 0) +
                        (queueTask.run?.output_tokens ?? 0)
                      ).toLocaleString()}
                    </span>{" "}
                    Tokens
                  </span>
                )}
                {queueTask.elapsed_sec != null && (
                  <span>
                    <span className="opacity-60 font-sans">耗时:</span>{" "}
                    <span className="text-foreground/90 font-medium">
                      {queueTask.elapsed_sec}s
                    </span>
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
