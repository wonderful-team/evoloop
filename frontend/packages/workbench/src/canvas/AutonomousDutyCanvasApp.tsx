/* ==========================================================================
   EvoLoop 自主值守工作台 · 无限画布模式主协同容器 (AutonomousDutyCanvasApp.tsx)
   作为 EvoLoop 主线 AutonomousDutyPage 的下一代无限画布模式升级方案：
   - 通用、场景无关的 Agent 长程自主值守调度系统
   - DAG 拓扑自动分层布局引擎 (layoutEngine.ts)
   - 核心交互：「节点卡片即页面」原位对称膨胀与收缩转场
   - 动效流水线：页面执行 → 门禁完成 → 缩回卡片 → 贝塞尔连线流动光点 → 聚焦下一节点 → 原地放大进入页面
   - 拉远 LOD 语义缩放反向尺度补偿 (极度拉远 30% 依然大字纯黑锐利可读)
   - 闭环商业拍板单选 (D2)、HITL 资金安全门禁 (D5)、仲裁三键控制台 (D3)
   - 全局 Prompt 指令栏：动态向通用队列插入新任务并自适应拓扑布局
   ========================================================================== */

import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { TasksQueueApi } from "@/lib/tasksQueueApi"
import type { DutyTask } from "../core/types"

import { DutyCanvas } from "./DutyCanvas"
import {
  deriveDutyEdges,
  type LayoutDirection,
  layoutDutyTasks,
} from "./layoutEngine"
import "./styles/duty-canvas.css"

export interface AutonomousDutyCanvasAppProps {
  tasks?: DutyTask[]
  isLoading?: boolean
  externalSelectedTaskId?: string | null
  onTaskSelect?: (taskId: string | null) => void
  onApproveTask?: (
    taskId: string,
    grantMode?: "once" | "always",
  ) => void | Promise<void>
  onRejectTask?: (taskId: string, feedback: string) => void | Promise<void>
  onConfirmProposalTask?: (taskId: string) => void | Promise<void>
  onRerunTask?: (taskId: string) => void | Promise<void>
  onConfirmHitl?: (
    taskId: string,
    grantMode?: "once" | "always",
  ) => void | Promise<void>
  onCancelHitl?: (taskId: string) => void | Promise<void>
  onNodeChat?: (taskId: string, message: string, files?: any[]) => void
  highlightStatuses?: string[]
  className?: string
  /**
   * Render prop：由外层（desktop）注入真实 ChatInputArea。
   * 参数携带画布当前节点上下文（selectedTask / selectedTaskIds 等）。
   */
  renderInputBar?: (ctx: {
    selectedTask: import("../core/types").DutyTask | null
    selectedTaskIds: Set<string>
    isMultiSelected: boolean
    onFocusTask: (task: import("../core/types").DutyTask) => void
    onClearSelection: () => void
  }) => React.ReactNode
}

export default function AutonomousDutyCanvasApp({
  tasks: externalTasks,
  isLoading: _isLoading = false,
  externalSelectedTaskId = null,
  highlightStatuses,
  onTaskSelect,
  onApproveTask,
  onRejectTask,
  onConfirmProposalTask,
  onRerunTask: _onRerunTask,
  onConfirmHitl,
  onCancelHitl,
  onNodeChat,
  className = "",
  renderInputBar,
}: AutonomousDutyCanvasAppProps = {}) {
  /* 布局方向：默认纵向瀑布排列（Top-to-Bottom，契合鼠标滚轮自然滚动） */
  const [layoutDirection, setLayoutDirection] =
    useState<LayoutDirection>("vertical")

  /* 原始任务队列与通用脑图拓扑结果：完全由外部真实任务驱动 */
  const [rawTasks, setRawTasks] = useState<DutyTask[]>(() => {
    const initList =
      externalTasks && externalTasks.length > 0 ? externalTasks : []
    return layoutDutyTasks(initList, undefined, "vertical").tasks
  })
  const rawTasksRef = useRef(rawTasks)
  useEffect(() => {
    rawTasksRef.current = rawTasks
  }, [rawTasks])

  /* 监听外部真实任务队列变化：平滑同步，并保留已有节点拖拽坐标 */
  useEffect(() => {
    if (!externalTasks) return
    setRawTasks((prev) => {
      const prevMap = new Map(prev.map((t) => [t.id, t]))
      const tasksToLayout = externalTasks.map((t) => {
        const old = prevMap.get(t.id)
        if (old && (old.x !== 0 || old.y !== 0)) {
          return { ...t, x: old.x, y: old.y, w: old.w, h: old.h }
        }
        return t
      })
      const hasUnpositioned = tasksToLayout.some((t) => t.x === 0 && t.y === 0)
      if (hasUnpositioned || prev.length !== externalTasks.length) {
        return layoutDutyTasks(tasksToLayout, undefined, layoutDirection).tasks
      }
      return tasksToLayout
    })
  }, [externalTasks, layoutDirection])

  /* 任务与连线：支持自由拖拽实时响应与边自适应动态推导 */
  const tasks = rawTasks
  const edges = useMemo(() => deriveDutyEdges(tasks), [tasks])

  /* 状态与控制 */
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set())
  const [focusTaskId, setFocusTaskId] = useState<string | null>(null)
  const [activeFlowEdge] = useState<string | null>(null)
  const [stepIndexMap, _setStepIndexMap] = useState<Record<string, number>>({})

  const [, setStatusText] = useState("已就绪 · EvoLoop 自主值守待命中")
  const [promptText, setPromptText] = useState("")

  /* 局部更新任务字段 */
  function patchTask(id: string, partial: Partial<DutyTask>) {
    setRawTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, ...partial } : t)),
    )
  }

  /* ── 展开节点进入页面态 (原地中心对称放大) ── */
  function openTask(taskId: string) {
    setActiveTaskId(taskId)
    setFocusTaskId(taskId)
  }

  /* ── 收缩还原为普通卡片 ── */
  function closeTask() {
    setActiveTaskId(null)
  }

  /* ── 🎯 节点聚焦：自动导航居中对齐、调整缩放并原地放大为页面 ── */
  function handleFocusAndOpenTask(taskId: string) {
    setSelectedTaskId(taskId)
    setSelectedTaskIds(new Set([taskId]))
    setFocusTaskId(taskId)
    openTask(taskId)
    onTaskSelect?.(taskId)
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    setStatusText(
      `🎯 已聚焦导航至节点 #T-${task?.taskNo || taskId} 并放大为工作页面`,
    )
  }

  /* 同步外部选中的任务（如来自左侧任务队列栏的选中点击）：选中高亮并平滑飞镜平移定位 */
  useEffect(() => {
    if (externalSelectedTaskId) {
      setSelectedTaskId(externalSelectedTaskId)
      setSelectedTaskIds(new Set([externalSelectedTaskId]))
      setFocusTaskId(externalSelectedTaskId)
    }
  }, [externalSelectedTaskId])

  /* 监听来自 desktop ChatInputArea 的 CustomEvent 消息路由 */
  // biome-ignore lint/correctness/useExhaustiveDependencies: handleNodeChat is a stable local callback; we only want to subscribe once on mount.
  useEffect(() => {
    const onNodeChat = (e: Event) => {
      const { taskId, message } = (e as CustomEvent).detail as {
        taskId: string
        message: string
      }
      handleNodeChat(taskId, message)
    }
    const onTaskFinished = (e: Event) => {
      const { taskId, status } = (e as CustomEvent).detail as {
        taskId: string
        status?: string
      }
      if (!taskId || !status || status === "in_progress" || status === "waiting_acceptance") return
      // 现场审核通过打绿勾或失败红标：先就地定格，保留 500ms 视觉确认期后再平滑收缩
      setRawTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: status as DutyTask["status"] } : t)),
      )
      setTimeout(() => {
        setActiveTaskId((cur) => (cur === taskId ? null : cur))
      }, 500)
    }
    const onQueueDrained = () => {
      setActiveTaskId(null)
      setFocusTaskId(null)
      setSelectedTaskId(null)
      setSelectedTaskIds(new Set())
      setStatusText("🎉 本轮任务已全部排空完成 · 镜头平滑拉远回脑图全景全览")
    }
    window.addEventListener("canvas:node-chat", onNodeChat)
    window.addEventListener("canvas:task-finished", onTaskFinished)
    window.addEventListener("canvas:queue-drained", onQueueDrained)
    return () => {
      window.removeEventListener("canvas:node-chat", onNodeChat)
      window.removeEventListener("canvas:task-finished", onTaskFinished)
      window.removeEventListener("canvas:queue-drained", onQueueDrained)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ── 运行焦点自动跟随：任务进入 in_progress 时镜头先对焦跟随节点，随后再原地展开为页面 ──
     电影级两段式转场 (Two-stage Cinematic Transition)：
     阶段 1：镜头平移聚焦 (Pan & Focus) —— 镜头滑向目标节点（卡片保持普通未展开形态，展示全局连线与就位状态）；
     阶段 2：原地展开放大 (Expand into Page) —— 经过 300ms 运镜滑达后，卡片在视口正中原地平滑放大为 1040px 工作页面。
  */
  const lastAutoFocusTaskIdRef = useRef<string | null>(null)
  const autoExpandTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const runningTaskId = useMemo(() => {
    return externalTasks?.find((t) => t.status === "in_progress")?.id ?? null
  }, [externalTasks])

  // biome-ignore lint/correctness/useExhaustiveDependencies: onTaskSelect is stable local callback; rawTasksRef is a ref
  useEffect(() => {
    if (!runningTaskId) {
      lastAutoFocusTaskIdRef.current = null
      if (autoExpandTimerRef.current) {
        clearTimeout(autoExpandTimerRef.current)
        autoExpandTimerRef.current = null
      }
      setFocusTaskId(null)
      return
    }

    if (runningTaskId === lastAutoFocusTaskIdRef.current) return
    lastAutoFocusTaskIdRef.current = runningTaskId

    // 选中当前运行任务
    setSelectedTaskId(runningTaskId)
    setSelectedTaskIds(new Set([runningTaskId]))
    onTaskSelect?.(runningTaskId)

    // 阶段 1：先收拢所有卡片为未展开普通形态，镜头平滑滑向目标节点正中（Pan & Focus）
    setActiveTaskId(null)
    setFocusTaskId(runningTaskId)

    const task = rawTasksRef.current.find((t) => t.id === runningTaskId)
    setStatusText(
      `🎯 镜头聚焦跟随至节点 #T-${task?.taskNo || runningTaskId}...`,
    )

    // 阶段 2：等待镜头平移到位后（300ms），在视口正中原地放大展开为 1040px 工作页面
    if (autoExpandTimerRef.current) {
      clearTimeout(autoExpandTimerRef.current)
    }
    autoExpandTimerRef.current = setTimeout(() => {
      setActiveTaskId(runningTaskId)
      setStatusText(
        `🎯 已自动跟随运行节点 #T-${task?.taskNo || runningTaskId} 并放大为工作页面`,
      )
    }, 300)

    return () => {
      if (autoExpandTimerRef.current) {
        clearTimeout(autoExpandTimerRef.current)
        autoExpandTimerRef.current = null
      }
    }
  }, [runningTaskId, onTaskSelect])

  /* ==========================================================================
     ★ 核心空间转场流水线 (Spatial Transition Pipeline)：
     镜头聚焦 → 节点在画布上原地放大为 1040px 页面 → Agent 现场思考与 MCP 执行
     → 门禁确认 → 节点平滑收缩回卡片 → 镜头拉远 → 贝塞尔连线粒子流动 → 镜头平移至下游卡片 → 原地放大进页面
     ========================================================================== */

  /* 节点位置由画布拖拽实时更新 */
  function handleUpdateTaskPosition(taskId: string, x: number, y: number) {
    setRawTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, x, y } : t)),
    )
  }

  /* 框选多节点批量位移 (平移拖拽同步) */
  function handleUpdateMultipleTaskPositions(
    positions: Map<string, { x: number; y: number }>,
  ) {
    setRawTasks((prev) =>
      prev.map((t) => {
        const pos = positions.get(t.id)
        return pos ? { ...t, x: pos.x, y: pos.y } : t
      }),
    )
  }

  /* 一键恢复纯正脑图对称排版 (一键整理) */
  function handleResetAutoLayout() {
    const { tasks: freshTasks } = layoutDutyTasks(
      rawTasks,
      undefined,
      layoutDirection,
    )
    setRawTasks(freshTasks)
    setStatusText("⚡ 已一键整理节点排版，所有节点已对称归位，无任何重叠")
  }

  /* 切换横向 / 纵向排列模式 */
  function handleToggleDirection() {
    const nextDir: LayoutDirection =
      layoutDirection === "horizontal" ? "vertical" : "horizontal"
    setLayoutDirection(nextDir)
    const { tasks: freshTasks } = layoutDutyTasks(
      rawTasksRef.current,
      undefined,
      nextDir,
    )
    setRawTasks(freshTasks)
    setStatusText(
      nextDir === "vertical"
        ? "⇄ 已切换为「纵向瀑布排列」· 顺应鼠标滚轮自然滑动，上下端口与贝塞尔曲线自动对齐"
        : "⇄ 已切换为「横向脑图排列」· 左右展开经典流式布局",
    )
  }

  /* 交互式连线新增依赖 (从 fromId 输出端口拖至 toId 输入端口) */
  function handleConnect(fromId: string, toId: string) {
    if (fromId === toId) return
    setRawTasks((prev) => {
      const target = prev.find((t) => t.id === toId)
      if (!target || (target.dependencies || []).includes(fromId)) return prev

      // 检测循环依赖，防止环路
      const adj = new Map<string, string[]>()
      prev.forEach((t) => adj.set(t.id, [...(t.dependencies || [])]))
      const queue = [fromId]
      const visited = new Set<string>()
      let hasCycle = false
      while (queue.length > 0) {
        const curr = queue.shift()!
        if (curr === toId) {
          hasCycle = true
          break
        }
        visited.add(curr)
        for (const dep of adj.get(curr) || []) {
          if (!visited.has(dep)) queue.push(dep)
        }
      }
      if (hasCycle) {
        setStatusText("⚠️ 连线被拒绝：拓扑中不能存在循环依赖环路")
        return prev
      }

      const updated = prev.map((t) => {
        if (t.id === toId) {
          return {
            ...t,
            dependencies: [...(t.dependencies || []), fromId],
          }
        }
        return t
      })
      const { tasks: freshTasks } = layoutDutyTasks(
        updated,
        undefined,
        layoutDirection,
      )
      // 持久化：本地拓扑只是乐观更新，依赖必须落到任务行（刷新/重连后仍在）
      const persistTarget = updated.find((t) => t.id === toId)
      void TasksQueueApi.update(toId, {
        dependencies: persistTarget?.dependencies ?? [],
      }).catch(() => {
        setStatusText("⚠️ 连线保存失败：依赖未落库，已回滚本地拓扑")
        setRawTasks((cur) => {
          const reverted = cur.map((t) =>
            t.id === toId
              ? {
                  ...t,
                  dependencies: (t.dependencies || []).filter(
                    (d) => d !== fromId,
                  ),
                }
              : t,
          )
          const { tasks: freshTasks } = layoutDutyTasks(
            reverted,
            undefined,
            layoutDirection,
          )
          return freshTasks
        })
      })
      return freshTasks
    })

    const fromTask = rawTasksRef.current.find((t) => t.id === fromId)
    const toTask = rawTasksRef.current.find((t) => t.id === toId)
    setStatusText(
      `⚡ 已连接数据流：#T-${fromTask?.taskNo || fromId} → #T-${toTask?.taskNo || toId}，拓扑已自适应重排！`,
    )
  }

  /* 点击贝塞尔连线断开依赖 */
  function handleDisconnect(fromId: string, toId: string) {
    setRawTasks((prev) => {
      const updated = prev.map((t) => {
        if (t.id === toId) {
          return {
            ...t,
            dependencies: (t.dependencies || []).filter((d) => d !== fromId),
          }
        }
        return t
      })
      const { tasks: freshTasks } = layoutDutyTasks(
        updated,
        undefined,
        layoutDirection,
      )
      // 持久化断连：失败回滚（重新挂上依赖）
      const persistTarget = updated.find((t) => t.id === toId)
      void TasksQueueApi.update(toId, {
        dependencies: persistTarget?.dependencies ?? [],
      }).catch(() => {
        setStatusText("⚠️ 断连保存失败：依赖未落库，已回滚本地拓扑")
        setRawTasks((cur) => {
          const reverted = cur.map((t) =>
            t.id === toId
              ? { ...t, dependencies: [...(t.dependencies || []), fromId] }
              : t,
          )
          const { tasks: freshTasks } = layoutDutyTasks(
            reverted,
            undefined,
            layoutDirection,
          )
          return freshTasks
        })
      })
      return freshTasks
    })

    const fromTask = rawTasksRef.current.find((t) => t.id === fromId)
    const toTask = rawTasksRef.current.find((t) => t.id === toId)
    setStatusText(
      `✂️ 已断开数据依赖：#T-${fromTask?.taskNo || fromId} ↛ #T-${toTask?.taskNo || toId}`,
    )
  }

  /* 用户与选中节点进行交互对话/下达微调指令 */
  /* 节点对话的本地回执：真实提交由页面层完成（回应面=智能体对话），
     此处不再伪造 step/artifact/“现场响应”。 */
  function handleNodeChat(taskId: string, message: string) {
    if (onNodeChat) {
      onNodeChat(taskId, message)
    }
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    if (!task) return
    setStatusText(
      `💬 消息已提交给 #T-${task.taskNo} 的 Agent，回应见智能体对话界面`,
    )
  }

  /* 仲裁三键操作 (闭环 D3) */
  function handleArbitration(
    action: "retry_upstream" | "cancel_downstream" | "reopen_modified",
  ) {
    if (action === "retry_upstream") {
      setStatusText("仲裁生效：重新调度上游执行，下游已复位")
    } else if (action === "cancel_downstream") {
      setStatusText("仲裁生效：已截断下游阻塞分支")
    } else if (action === "reopen_modified") {
      setStatusText("仲裁生效：微调参数通过，下游已解锁就绪")
    }
  }

  /* 拍板方案选项勾选回流 (闭环 D2) */
  function handlePickOption(taskId: string, index: number) {
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    if (!task || !task.signoff) return

    const updatedOptions = (task.signoff.options || []).map((opt, i) => ({
      ...opt,
      picked: i === index,
    }))

    patchTask(taskId, {
      signoff: {
        ...task.signoff,
        options: updatedOptions,
        pickedIndex: index,
      },
    })
  }

  /* 批准方案 (支持 grantMode) */
  function handleApprove(taskId: string, grantMode?: "once" | "always") {
    if (onApproveTask) {
      void onApproveTask(taskId, grantMode)
    }

    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "completed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "completed",
            decision: {
              action: "approve",
              grantMode,
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✓ #T-${task?.taskNo || taskId} 方案已核准通过 ${grantMode === "always" ? "(总是允许)" : ""}`,
    )
  }

  /* 打回重做 (带反馈) */
  function handleReject(taskId: string, feedback?: string) {
    if (onRejectTask) {
      void onRejectTask(taskId, feedback || "方案需进一步优化")
    }

    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    const newCount = (task?.signoff?.rejectCount || 0) + 1
    patchTask(taskId, {
      status: "waiting_acceptance",
      signoff: task?.signoff
        ? {
            ...task.signoff,
            rejectCount: newCount,
            lastFeedback: feedback || "方案需进一步优化",
          }
        : undefined,
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "rejected",
            decision: {
              action: "reject",
              feedback: feedback || "方案需进一步优化",
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✕ #T-${task?.taskNo || taskId} 已打回修改：${feedback || "请重新调整"}`,
    )
  }

  /* 资金/高危操作放行 (支持 grantMode: "once" | "always") */
  function handleConfirmHitl(
    taskId: string,
    grantMode: "once" | "always" = "once",
  ) {
    if (onConfirmHitl) {
      void onConfirmHitl(taskId, grantMode)
    }

    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "completed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "completed",
            decision: {
              action: "approve",
              grantMode,
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✓ #T-${task?.taskNo || taskId} 资金与写操作已授权放行 (${grantMode === "always" ? "已设为总是允许" : "仅放行本次"})`,
    )
  }

  /* HITL 取消任务 */
  function handleCancelHitl(taskId: string) {
    if (onCancelHitl) {
      void onCancelHitl(taskId)
    }

    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "failed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "cancelled",
            decision: {
              action: "cancel",
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(`⛔ #T-${task?.taskNo || taskId} 人机治理取消操作，任务终止`)
  }

  /* HITL 单选/多选/文本提交 */
  function handleSubmitChoiceHitl(taskId: string, choice: string) {
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "completed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "completed",
            decision: {
              action: "submit_choice",
              value: choice,
              selected: [choice],
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✓ #T-${task?.taskNo || taskId} 已确认选项：「${choice}」，链路继续推进`,
    )
  }

  function handleSubmitMultiChoiceHitl(taskId: string, choices: string[]) {
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "completed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "completed",
            decision: {
              action: "submit_multi_choice",
              selected: choices,
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✓ #T-${task?.taskNo || taskId} 已提交多项选项 (${choices.length}项)，链路继续推进`,
    )
  }

  function handleSubmitTextHitl(taskId: string, value: string) {
    const task = rawTasksRef.current.find((t) => t.id === taskId)
    const prevReq = task?.humanRequest
    patchTask(taskId, {
      status: "completed",
      humanRequest: prevReq
        ? {
            ...prevReq,
            status: "completed",
            decision: {
              action: "submit_text",
              value,
              timestamp: new Date().toLocaleTimeString(),
            },
          }
        : undefined,
    })
    setStatusText(
      `✓ #T-${task?.taskNo || taskId} 已补充信息：「${value}」，Agent 恢复处理`,
    )
  }

  /* 用户通过 Prompt 指令向 Agent 派发动态新任务或与节点对话 */
  /* 选中任务卡 = 与该任务的执行 Agent 对话（handleNodeChat）。
     无选中直发需求已上移到页面层（值守 Agent 对话面板），此处只兜底。 */
  function handleSendPrompt(customText?: string) {
    const text = (customText || promptText).trim()
    if (!text) return
    if (!customText) setPromptText("")

    if (selectedTaskId) {
      handleNodeChat(selectedTaskId, text)
      return
    }

    toast.error("请先选中任务卡，或使用底部输入框直接与值守 Agent 对话")
  }

  return (
    <div className={`dc-app ${className}`}>
      {/* ── 主工作区 ── */}
      <div className="dc-main">
        {/* 中央无限任务画布：节点卡片原地放大为页面 */}
        <DutyCanvas
          tasks={tasks}
          edges={edges}
          activeTaskId={activeTaskId}
          selectedTaskId={selectedTaskId}
          selectedTaskIds={selectedTaskIds}
          layoutDirection={layoutDirection}
          activeFlowEdge={activeFlowEdge}
          stepIndexMap={stepIndexMap}
          focusTaskId={focusTaskId}
          highlightStatuses={highlightStatuses}
          onTaskClick={handleFocusAndOpenTask}
          onSelectTask={(id) => {
            setSelectedTaskId(id)
            setSelectedTaskIds(id ? new Set([id]) : new Set())
            onTaskSelect?.(id)
          }}
          onSelectTasks={(ids) => {
            setSelectedTaskIds(ids)
            if (ids.size === 1) {
              const [first] = ids
              setSelectedTaskId(first)
              onTaskSelect?.(first)
            } else {
              setSelectedTaskId(null)
              if (ids.size === 0) {
                onTaskSelect?.(null)
              }
            }
          }}
          onToggleDirection={handleToggleDirection}
          onCloseTask={closeTask}
          onUpdateTaskPosition={handleUpdateTaskPosition}
          onUpdateMultipleTaskPositions={handleUpdateMultipleTaskPositions}
          onResetAutoLayout={handleResetAutoLayout}
          onConnect={handleConnect}
          onDisconnect={handleDisconnect}
          onNodeChat={handleNodeChat}
          onConfirmProposalTask={onConfirmProposalTask}
          onSendGlobalPrompt={handleSendPrompt}
          onPickOption={handlePickOption}
          onApprove={handleApprove}
          onReject={handleReject}
          onArbitrate={handleArbitration}
          onConfirmHitl={handleConfirmHitl}
          onCancelHitl={handleCancelHitl}
          onSubmitTextHitl={handleSubmitTextHitl}
          onSubmitChoiceHitl={handleSubmitChoiceHitl}
          onSubmitMultiChoiceHitl={handleSubmitMultiChoiceHitl}
          renderInputBar={renderInputBar}
        />
      </div>
    </div>
  )
}
