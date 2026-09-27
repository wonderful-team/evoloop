/* ==========================================================================
   EvoLoop 自主值守工作台 · 无限画布交互引擎 (DutyCanvas.tsx)
   设计理念：
   - 纯正二维空间镜头缩放与流程跟随 (Continuous Cinematic Camera in 2D Plane)
   - 单击选中节点，双击或点击按钮展开为 1040px 现场工作页面
   - 关闭节点原地收缩还原，绝不强行拉回全览！
   - 卡片主体任意位置按住拖动节点坐标，画布空白处拖动平移视口
   - 端口交互式拖拽拉线 (从右端口拉到左端口) 与点击连线一键断开
   - 贝塞尔连线常态流动虚线与箭头，清晰示意数据流向
   - Ctrl / ⌘ + 滚轮缩放，局部容器内部正常自然滚动
   ========================================================================== */

import { cn } from "@evoloop/shared/lib/utils"
import { BoxSelect, Hand, Workflow, X } from "lucide-react"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { CanvasViewport, DutyEdge, DutyTask } from "../core/types"
import {
  DutyNodeCard,
  EXPANDED_CARD_HEIGHT,
  EXPANDED_CARD_WIDTH,
} from "./DutyNodeCard"
import { DutyNodePageContent } from "./DutyNodePageContent"

interface DutyCanvasProps {
  tasks: DutyTask[]
  edges: DutyEdge[]
  activeTaskId: string | null
  selectedTaskId?: string | null
  selectedTaskIds?: Set<string>
  layoutDirection?: "horizontal" | "vertical"
  activeFlowEdge: string | null // e.g. "task-1>task-4"
  stepIndexMap: Record<string, number>
  focusTaskId?: string | null
  highlightStatuses?: string[]
  onTaskClick: (taskId: string) => void // 展开节点为 1040px 页面
  onSelectTask?: (taskId: string | null) => void // 单击选中节点
  onSelectTasks?: (taskIds: Set<string>) => void // 多选节点更新
  onToggleDirection?: () => void // 切换横向/纵向排列
  onCloseTask: () => void // 原地收缩卡片，绝不飞回全览
  onUpdateTaskPosition?: (taskId: string, x: number, y: number) => void
  onUpdateMultipleTaskPositions?: (
    positions: Map<string, { x: number; y: number }>,
  ) => void
  onResetAutoLayout?: () => void
  onConnect?: (fromId: string, toId: string) => void
  onDisconnect?: (fromId: string, toId: string) => void
  onTaskFission?: (parentTaskId?: string) => void
  onNodeChat?: (taskId: string, message: string) => void
  onSendGlobalPrompt?: (text: string) => void
  onPickOption?: (taskId: string, index: number) => void
  onApprove?: (taskId: string, grantMode?: "once" | "always") => void
  onConfirmProposalTask?: (taskId: string) => void | Promise<void>
  onReject?: (taskId: string, reason?: string) => void
  onArbitrate?: (
    action: "retry_upstream" | "cancel_downstream" | "reopen_modified",
  ) => void
  onConfirmHitl?: (taskId: string, grantMode?: "once" | "always") => void
  onCancelHitl?: (taskId: string) => void
  onSubmitTextHitl?: (taskId: string, value: string) => void
  onSubmitChoiceHitl?: (taskId: string, choice: string) => void
  onSubmitMultiChoiceHitl?: (taskId: string, choices: string[]) => void
  /**
   * Render prop：由外层（desktop 侧）注入真实的 ChatInputArea 实例。
   * 参数携带画布当前的节点上下文，供上层包一个节点感知上下文 header。
   * 若未提供，画布不渲染输入栏。
   */
  renderInputBar?: (ctx: {
    selectedTask: DutyTask | null
    selectedTaskIds: Set<string>
    isMultiSelected: boolean
    onFocusTask: (task: DutyTask) => void
    onClearSelection: () => void
  }) => React.ReactNode
}

const clamp = (v: number, min: number, max: number) =>
  Math.min(Math.max(v, min), max)

export const DutyCanvas = ({
  tasks,
  edges,
  activeTaskId,
  selectedTaskId = null,
  selectedTaskIds,
  layoutDirection = "vertical",
  activeFlowEdge,
  stepIndexMap,
  focusTaskId,
  highlightStatuses,
  onTaskClick,
  onSelectTask,
  onSelectTasks,
  onToggleDirection,
  onCloseTask,
  onUpdateTaskPosition,
  onUpdateMultipleTaskPositions,
  onResetAutoLayout,
  onConnect,
  onDisconnect,
  onTaskFission,
  onNodeChat: _onNodeChat,
  onSendGlobalPrompt: _onSendGlobalPrompt,
  onPickOption,
  onApprove,
  onConfirmProposalTask,
  onReject,
  onArbitrate,
  onConfirmHitl,
  onCancelHitl,
  onSubmitTextHitl,
  onSubmitChoiceHitl,
  onSubmitMultiChoiceHitl,
  renderInputBar,
}: DutyCanvasProps) => {
  const containerRef = useRef<HTMLDivElement>(null)

  // 工具模式：hand (默认抓手平移) vs select (框选优先)
  const [toolMode, setToolMode] = useState<"select" | "hand">("hand")

  // 画框多选状态 (Marquee)
  const [marquee, setMarquee] = useState<{
    startX: number
    startY: number
    currentX: number
    currentY: number
  } | null>(null)

  const isMultiSelected = (selectedTaskIds && selectedTaskIds.size > 1) || false

  const selectedTask = useMemo(() => {
    if (selectedTaskId) {
      return tasks.find((t) => t.id === selectedTaskId) || null
    }
    if (selectedTaskIds && selectedTaskIds.size === 1) {
      const firstId = Array.from(selectedTaskIds)[0]
      return tasks.find((t) => t.id === firstId) || null
    }
    return null
  }, [tasks, selectedTaskId, selectedTaskIds])

  // 动态计算 SVG 连线层边界，避免任务多时连线被硬编码 12000×8000 裁掉
  const svgBounds = useMemo(() => {
    if (tasks.length === 0) {
      return { minX: 0, minY: 0, width: 12000, height: 8000 }
    }
    const padding = 400
    const minX = Math.min(...tasks.map((t) => t.x)) - padding
    const minY = Math.min(...tasks.map((t) => t.y)) - padding
    const maxX = Math.max(...tasks.map((t) => t.x + (t.w || 420))) + padding
    const maxY = Math.max(...tasks.map((t) => t.y + (t.h || 280))) + padding
    return { minX, minY, width: maxX - minX, height: maxY - minY }
  }, [tasks])

  // 视口摄像机状态：默认 100% 缩放比例
  const [view, setView] = useState<CanvasViewport>({ x: 0, y: 0, k: 1.0 })
  const viewRef = useRef<CanvasViewport>(view)

  // 节点全屏（扩展到整个右侧面板）与现有画布放大效果切换状态
  const [isNodeFullscreen, setIsNodeFullscreen] = useState(false)

  // 当 activeTaskId 被清空（收起回普通卡片）时，复位全屏状态
  useEffect(() => {
    if (!activeTaskId) {
      setIsNodeFullscreen(false)
    }
  }, [activeTaskId])

  // 🌟 监听任务多级状态跃迁事件（聚焦 -> 放大 -> 全屏）：支持从左侧任务列表双击驱动
  useEffect(() => {
    const handleAdvanceState = (e: Event) => {
      const { taskId } = (e as CustomEvent).detail as { taskId: string }
      if (!taskId) return

      if (activeTaskId !== taskId) {
        // 第 1 步：若该任务未处于放大状态，先原地放大为大任务工作页面（展开）
        setIsNodeFullscreen(false)
        onTaskClick(taskId)
      } else if (!isNodeFullscreen) {
        // 第 2 步：若该任务已处于放大状态，再次双击则扩展为全屏工作页面
        setIsNodeFullscreen(true)
      } else {
        // 第 3 步：若该任务已全屏，再次双击退出全屏回退为放大状态
        setIsNodeFullscreen(false)
      }
    }

    window.addEventListener("canvas:advance-task-state", handleAdvanceState)
    return () => {
      window.removeEventListener(
        "canvas:advance-task-state",
        handleAdvanceState,
      )
    }
  }, [activeTaskId, isNodeFullscreen, onTaskClick])

  const updateView = useCallback(
    (next: CanvasViewport | ((prev: CanvasViewport) => CanvasViewport)) => {
      setView((prev) => {
        const resolved = typeof next === "function" ? next(prev) : next
        viewRef.current = resolved
        return resolved
      })
    },
    [],
  )

  const hasInitializedRef = useRef(false)
  const lastDirectionRef = useRef(layoutDirection)

  const animFrameRef = useRef<number | null>(null)
  const [autoFollow] = useState(true)
  const [isPanning, setIsPanning] = useState(false)
  const [spacePressed, setSpacePressed] = useState(false)

  // 节点拖拽移动状态 (支持成组多选拖动)
  const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null)
  const nodeDragRef = useRef<{
    taskId: string
    sx: number
    sy: number
    ox: number
    oy: number
    moved: boolean
    groupOrigins: Map<string, { x: number; y: number }>
  } | null>(null)

  const isTaskSelected = useCallback(
    (id: string) => {
      if (selectedTaskIds && selectedTaskIds.size > 0) {
        return selectedTaskIds.has(id)
      }
      return id === selectedTaskId
    },
    [selectedTaskIds, selectedTaskId],
  )

  // 画布平移状态
  const panRef = useRef<{
    sx: number
    sy: number
    ox: number
    oy: number
    moved: boolean
  } | null>(null)

  // 端口交互式拉线状态
  const [wireDrag, setWireDrag] = useState<{
    fromTaskId: string
    sx: number
    sy: number
    curX: number
    curY: number
  } | null>(null)

  // 选中连线状态 (用于高亮或断开)
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null)

  /* 缩放动画缓动执行 (三次减速曲线) */
  const animateTo = useCallback(
    (targetView: CanvasViewport, durationMs = 480) => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current)
        animFrameRef.current = null
      }
      const fromView = { ...viewRef.current }
      const startTime = performance.now()

      const tick = (now: number) => {
        const progress = Math.min(1, (now - startTime) / durationMs)
        const ease = 1 - (1 - progress) ** 3
        const curView: CanvasViewport = {
          x: fromView.x + (targetView.x - fromView.x) * ease,
          y: fromView.y + (targetView.y - fromView.y) * ease,
          k: fromView.k + (targetView.k - fromView.k) * ease,
        }
        viewRef.current = curView
        setView(curView)
        if (progress < 1) {
          animFrameRef.current = requestAnimationFrame(tick)
        } else {
          animFrameRef.current = null
        }
      }
      animFrameRef.current = requestAnimationFrame(tick)
    },
    [],
  )

  /* ★ 镜头放大聚焦指定卡片：居中对准展开后的 1040px 页面，自适应合适缩放比，左边缘严格安全防线 */
  const flyToCard = useCallback(
    (
      task: DutyTask,
      targetK?: number,
      durationMs = 480,
      willExpand?: boolean,
    ) => {
      const el = containerRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return

      const isExpandedCard = willExpand || task.id === activeTaskId
      const cardW = isExpandedCard ? EXPANDED_CARD_WIDTH : task.w
      const cardH = isExpandedCard ? EXPANDED_CARD_HEIGHT : task.h || 280

      // 自适应计算缩放比例：
      // 当视口宽裕时，锁定在原生 1.0 (100% 物理点阵)，杜绝非 1:1 亚像素拉伸引起的字体模糊；
      // 当视口较窄时，自适应缩放到合理尺寸，绝不强制 clamp 到过大的 0.72 导致卡片被挤出视口左边缘
      const optimalK = clamp(
        Math.min((rect.width * 0.9) / cardW, (rect.height * 0.9) / cardH),
        0.35,
        1.0, // 封顶 100%，绝不超比例虚化放大
      )
      const k = targetK ?? optimalK
      const centerX = task.x + task.w / 2
      const centerY = task.y + (task.h || 280) / 2
      let targetX = Math.round(rect.width / 2 - centerX * k)
      let targetY = Math.round(rect.height / 2 - centerY * k)

      // ★ 核心边界安全防线 (Left & Top Boundary Protection)：
      // 展开卡片实际在画布坐标系中的左边界与顶边界：
      const cardLeft = isExpandedCard
        ? task.x - (EXPANDED_CARD_WIDTH - task.w) / 2
        : task.x
      const cardTop = isExpandedCard
        ? task.y - (EXPANDED_CARD_HEIGHT - (task.h || 280)) / 2
        : task.y
      const screenCardLeft = cardLeft * k + targetX
      const screenCardTop = cardTop * k + targetY

      // 无论视口多窄，确保卡片左边缘距离视口左侧边栏至少保留 32px 舒适间距，绝不挤压到边栏底下
      if (screenCardLeft < 32) {
        targetX += Math.round(32 - screenCardLeft)
      }
      // 顶部至少保留 20px 间距
      if (screenCardTop < 20) {
        targetY += Math.round(20 - screenCardTop)
      }

      if (durationMs > 0) {
        animateTo({ x: targetX, y: targetY, k }, durationMs)
      } else {
        if (animFrameRef.current !== null) {
          cancelAnimationFrame(animFrameRef.current)
          animFrameRef.current = null
        }
        viewRef.current = { x: targetX, y: targetY, k }
        setView({ x: targetX, y: targetY, k })
      }
    },
    [activeTaskId, animateTo],
  )

  /* 镜头平滑拉远回脑图全览视角 (仅供用户显式点击触发，收起卡片时绝不擅自调用) */
  const flyToOverview = useCallback(
    (durationMs = 450) => {
      const el = containerRef.current
      if (!el || tasks.length === 0) return
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const minX = Math.min(...tasks.map((t) => t.x))
      const maxX = Math.max(...tasks.map((t) => t.x + t.w))
      const minY = Math.min(...tasks.map((t) => t.y))
      const maxY = Math.max(...tasks.map((t) => t.y + (t.h || 280)))

      const graphW = maxX - minX + 260
      const graphH = maxY - minY + 260

      const scale = clamp(
        Math.min(rect.width / graphW, rect.height / graphH),
        0.18,
        0.7,
      )
      let targetX = (rect.width - (maxX + minX) * scale) / 2
      let targetY = (rect.height - (maxY + minY) * scale) / 2

      // 安全边界防线：全览下最左/最上节点绝不超出边缘
      if (minX * scale + targetX < 40) {
        targetX = Math.round(40 - minX * scale)
      }
      if (minY * scale + targetY < 40) {
        targetY = Math.round(40 - minY * scale)
      }

      animateTo({ x: targetX, y: targetY, k: scale }, durationMs)
    },
    [tasks, animateTo],
  )

  /* 值守排空（本轮全部任务终态）→ 镜头回到全览：战报时刻用户该看到的是
     整张作战图，而不是停留在某个局部。若有展开的节点页先原地收起。 */
  useEffect(() => {
    const onQueueDrained = () => {
      if (activeTaskId) {
        onCloseTask()
      }
      flyToOverview(600)
    }
    window.addEventListener("canvas:queue-drained", onQueueDrained)
    return () => {
      window.removeEventListener("canvas:queue-drained", onQueueDrained)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTaskId, onCloseTask, flyToOverview])

  // 方案 A：首屏自适应对齐与安全边距 (100% 比例，对齐顶层根任务群)
  const centerInitialView = useCallback(() => {
    const el = containerRef.current
    if (!el || tasks.length === 0) return false
    const rect = el.getBoundingClientRect()
    if (rect.width < 100 || rect.height < 100) return false

    // 如果当前已有激活展开的卡片，优先安全对焦该卡片，绝不暴力打乱用户视野
    if (activeTaskId) {
      const activeTask = tasks.find((t) => t.id === activeTaskId)
      if (activeTask) {
        flyToCard(activeTask, undefined, 0, true)
        return true
      }
    }

    const minX = Math.min(...tasks.map((t) => t.x))
    const minY = Math.min(...tasks.map((t) => t.y))

    if (layoutDirection === "vertical") {
      // 纵向瀑布流：顶层根任务群
      const topRowTasks = tasks.filter((t) => Math.abs(t.y - minY) < 30)
      const topMinX = Math.min(...topRowTasks.map((t) => t.x))
      const topMaxX = Math.max(...topRowTasks.map((t) => t.x + t.w))
      const rowWidth = topMaxX - topMinX

      // 关键修复：当任务行宽度小于视口时居中对齐；当任务行超出视口时，靠左保留舒适留白 (60px)
      // 绝对不能把超宽行强行居中而导致最前排的根节点被负坐标推移到左侧屏幕外！
      let targetX: number
      if (rowWidth + 120 <= rect.width) {
        targetX = Math.round((rect.width - rowWidth) / 2 - topMinX)
      } else {
        targetX = Math.round(60 - topMinX)
      }
      const targetY = Math.round(60 - minY)

      setView({ x: targetX, y: targetY, k: 1.0 })
      viewRef.current = { x: targetX, y: targetY, k: 1.0 }
    } else {
      // 横向排列：最左侧起点任务离左边 60px
      const maxY = Math.max(...tasks.map((t) => t.y + (t.h || 280)))
      const graphHeight = maxY - minY
      const targetX = Math.round(60 - minX)

      let targetY: number
      if (graphHeight + 120 <= rect.height) {
        targetY = Math.round((rect.height - graphHeight) / 2 - minY)
      } else {
        targetY = Math.round(60 - minY)
      }

      setView({ x: targetX, y: targetY, k: 1.0 })
      viewRef.current = { x: targetX, y: targetY, k: 1.0 }
    }
    return true
  }, [tasks, layoutDirection, activeTaskId, flyToCard])

  // 首屏挂载（或切换方向时）自动计算应用方案 A 居中
  useEffect(() => {
    if (tasks.length === 0) return
    if (
      !hasInitializedRef.current ||
      lastDirectionRef.current !== layoutDirection
    ) {
      if (activeTaskId) {
        const task = tasks.find((t) => t.id === activeTaskId)
        if (task) {
          flyToCard(task, undefined, 0, true)
          hasInitializedRef.current = true
          lastDirectionRef.current = layoutDirection
          return
        }
      }
      const ok = centerInitialView()
      if (ok) {
        hasInitializedRef.current = true
        lastDirectionRef.current = layoutDirection
      }
    }
  }, [tasks, layoutDirection, centerInitialView, activeTaskId, flyToCard])

  // 跟踪用户是否已主动平移/缩放/拖拽，若已主动交互则不强行覆盖用户视野
  const hasUserInteractedRef = useRef<boolean>(false)
  const lastViewportWidthRef = useRef<number>(0)

  // 监听画布视口真实尺寸变化（窗口缩放、左侧任务面板拖动调节、页面路由切入滑入完成）
  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === "undefined") return

    let prevW = 0
    let prevH = 0

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const { width, height } = entry.contentRect
      if (width < 100 || height < 100) return

      if (!hasInitializedRef.current && tasks.length > 0) {
        if (activeTaskId) {
          const task = tasks.find((t) => t.id === activeTaskId)
          if (task) flyToCard(task, undefined, 0, true)
        } else {
          centerInitialView()
        }
        hasInitializedRef.current = true
      } else if (
        activeTaskId &&
        (Math.abs(width - prevW) > 8 || Math.abs(height - prevH) > 8)
      ) {
        const task = tasks.find((t) => t.id === activeTaskId)
        if (task) {
          flyToCard(task, undefined, 120, true)
        }
      } else if (
        !activeTaskId &&
        !hasUserInteractedRef.current &&
        lastViewportWidthRef.current > 0 &&
        Math.abs(width - lastViewportWidthRef.current) > 30
      ) {
        lastViewportWidthRef.current = width
        centerInitialView()
      }

      if (lastViewportWidthRef.current === 0) {
        lastViewportWidthRef.current = width
      }
      prevW = width
      prevH = height
    })

    ro.observe(el)
    return () => ro.disconnect()
  }, [tasks, activeTaskId, centerInitialView, flyToCard])

  // 页面路由转场入场阶段（0 ~ 300ms 滑动过渡）：
  // 在滑动彻底结束（350ms）后执行一次精确视口尺寸对焦校准，确保 100% 居中无错位
  useEffect(() => {
    if (tasks.length === 0) return
    const timer = setTimeout(() => {
      if (
        !hasUserInteractedRef.current &&
        !activeTaskId &&
        !hasInitializedRef.current
      ) {
        centerInitialView()
      }
    }, 350)
    return () => clearTimeout(timer)
  }, [centerInitialView, activeTaskId, tasks.length])

  /* ★ 镜头焦点跟踪：在展开任务或聚焦目标切换时平滑对焦 */
  const lastActiveTaskIdRef = useRef<string | null>(null)
  const lastFocusTaskIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (activeTaskId) {
      const task = tasks.find((t) => t.id === activeTaskId)
      if (task && activeTaskId !== lastActiveTaskIdRef.current) {
        lastActiveTaskIdRef.current = activeTaskId
        flyToCard(task, undefined, 480, true)
      }
      return
    }
    lastActiveTaskIdRef.current = null

    if (autoFollow && focusTaskId) {
      const task = tasks.find((t) => t.id === focusTaskId)
      if (task && focusTaskId !== lastFocusTaskIdRef.current) {
        lastFocusTaskIdRef.current = focusTaskId
        flyToCard(task)
      }
      return
    }
    lastFocusTaskIdRef.current = null
  }, [activeTaskId, focusTaskId, autoFollow, flyToCard, tasks])

  /* 全局键盘快捷键监听 (Spacebar 平移模式, Esc 原地关闭展开卡片) */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.code === "Space" &&
        !(e.target as HTMLElement).closest(
          "input, textarea, select, [contenteditable]",
        )
      ) {
        setSpacePressed(true)
      }
      if (e.key === "Escape") {
        if (activeTaskId) {
          // 【核心纠偏】按 Esc 原地收起展开卡片，绝不拉回全览！
          setIsNodeFullscreen(false)
          onCloseTask()
        }
        setSelectedEdgeKey(null)
      }
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        setSpacePressed(false)
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    window.addEventListener("keyup", handleKeyUp)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      window.removeEventListener("keyup", handleKeyUp)
    }
  }, [activeTaskId, onCloseTask])

  /* ★ 滚轮交互：Ctrl / ⌘ + 滚轮缩放；未按时局部容器自然滚动，画布空白处平移 */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const handleWheel = (e: WheelEvent) => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current)
        animFrameRef.current = null
      }

      const isZoomGesture = e.ctrlKey || e.metaKey

      if (isZoomGesture) {
        hasUserInteractedRef.current = true
        e.preventDefault()
        const rect = el.getBoundingClientRect()
        const px = e.clientX - rect.left
        const py = e.clientY - rect.top

        const isPinch = Math.abs(e.deltaY) < 40 && !Number.isInteger(e.deltaY)
        const factor = isPinch ? 0.993 ** e.deltaY : e.deltaY < 0 ? 1.12 : 0.89

        const curK = viewRef.current.k
        const nextK = clamp(curK * factor, 0.15, 3.0)

        updateView((prev) => ({
          k: nextK,
          x: px - (px - prev.x) * (nextK / prev.k),
          y: py - (py - prev.y) * (nextK / prev.k),
        }))
        return
      }

      const target = e.target as HTMLElement
      const scrollable = target.closest(
        ".dc-page-body, .dc-timeline-panel, .dc-artifact-panel, .dc-artifact-view, .dc-sidebar, .dc-phone-screen-body",
      )

      if (scrollable) {
        // 允许局部容器正常滚动内容
        return
      }

      // 画布空白处：平移画布
      hasUserInteractedRef.current = true
      e.preventDefault()
      const deltaX = e.shiftKey ? e.deltaY : e.deltaX
      const deltaY = e.shiftKey ? 0 : e.deltaY

      updateView((prev) => ({
        ...prev,
        x: prev.x - deltaX,
        y: prev.y - deltaY,
      }))
    }

    el.addEventListener("wheel", handleWheel, { passive: false })
    return () => el.removeEventListener("wheel", handleWheel)
  }, [updateView])

  /* 从端口开始拖拽拉线 (支持左右与上下端口) */
  const handlePortPointerDown = (
    _e: React.PointerEvent,
    taskId: string,
    side: "left" | "right" | "top" | "bottom",
  ) => {
    const task = tasks.find((t) => t.id === taskId)
    if (!task) return
    const isExp = task.id === activeTaskId
    const w = isExp ? EXPANDED_CARD_WIDTH : task.w
    const h = isExp ? EXPANDED_CARD_HEIGHT : task.h || 280
    const x = isExp ? task.x - (EXPANDED_CARD_WIDTH - task.w) / 2 : task.x
    const y = isExp
      ? task.y - (EXPANDED_CARD_HEIGHT - (task.h || 280)) / 2
      : task.y

    let portX = x + w
    let portY = y + h / 2

    if (side === "bottom") {
      portX = x + w / 2
      portY = y + h
    } else if (side === "top") {
      portX = x + w / 2
      portY = y
    } else if (side === "left") {
      portX = x
      portY = y + h / 2
    }

    if (side === "right" || side === "bottom") {
      setWireDrag({
        fromTaskId: taskId,
        sx: portX,
        sy: portY,
        curX: portX,
        curY: portY,
      })
    }
  }

  /* 全局统一 PointerDown 处理 */
  const handlePointerDown = (e: React.PointerEvent) => {
    const target = e.target as HTMLElement

    // 1. 表单交互控件与底部对话框直接透传
    if (
      target.closest(
        "button, input, select, textarea, a, .dc-btn-sm, .dc-card-tab, .dc-canvas-controls, .dc-card-action-btn, .dc-bottom-prompt-bar, .dc-edge-popover",
      )
    ) {
      return
    }

    // 2. 如果点击在端口上，已由 handlePortPointerDown 优先处理
    if (target.closest(".dc-port")) {
      return
    }

    // 3. 点击卡片内部：
    const card = target.closest(".dc-card") as HTMLElement
    if (card) {
      if (card.classList.contains("expanded")) {
        // 展开卡片内部的任何交互绝不穿透到底层画布！绝不触发画布背景平移或误触发收起！
        return
      }

      const taskId = card.getAttribute("data-task-id")
      const task = tasks.find((t) => t.id === taskId)
      if (task) {
        if (animFrameRef.current !== null) {
          cancelAnimationFrame(animFrameRef.current)
          animFrameRef.current = null
        }

        // 处理 Shift / Cmd 多选反选
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          const currentSet = new Set(
            selectedTaskIds || (selectedTaskId ? [selectedTaskId] : []),
          )
          if (currentSet.has(task.id)) {
            currentSet.delete(task.id)
          } else {
            currentSet.add(task.id)
          }
          onSelectTasks?.(currentSet)
          onSelectTask?.(currentSet.size > 0 ? Array.from(currentSet)[0] : null)
          return
        }

        // 构建成组多选拖动集合
        const groupOrigins = new Map<string, { x: number; y: number }>()
        const isCurrentInMulti =
          selectedTaskIds &&
          selectedTaskIds.has(task.id) &&
          selectedTaskIds.size > 1

        if (isCurrentInMulti) {
          selectedTaskIds!.forEach((id) => {
            const t = tasks.find((item) => item.id === id)
            if (t) groupOrigins.set(id, { x: t.x, y: t.y })
          })
        } else {
          groupOrigins.set(task.id, { x: task.x, y: task.y })
          onSelectTasks?.(new Set([task.id]))
          onSelectTask?.(task.id)
        }

        nodeDragRef.current = {
          taskId: task.id,
          sx: e.clientX,
          sy: e.clientY,
          ox: task.x,
          oy: task.y,
          moved: false,
          groupOrigins,
        }
        return
      }
    }

    // 4. 点击画布空白背景：
    // 如果是框选模式 (toolMode === "select") 或按住了 Shift，启动画框选择 (Marquee)
    // 否则为抓手模式 (toolMode === "hand") 或默认平移画布 (Pan)
    if (toolMode === "select" || e.shiftKey) {
      if (!e.shiftKey) {
        onSelectTasks?.(new Set())
        onSelectTask?.(null)
      }
      setSelectedEdgeKey(null)

      const canvasX = (e.clientX - viewRef.current.x) / viewRef.current.k
      const canvasY = (e.clientY - viewRef.current.y) / viewRef.current.k

      setMarquee({
        startX: canvasX,
        startY: canvasY,
        currentX: canvasX,
        currentY: canvasY,
      })
      return
    }

    // 平移画布
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }

    panRef.current = {
      sx: e.clientX,
      sy: e.clientY,
      ox: viewRef.current.x,
      oy: viewRef.current.y,
      moved: false,
    }
    setIsPanning(true)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    // A. 正在拖拽拉线
    if (wireDrag) {
      const curCanvasX = (e.clientX - viewRef.current.x) / viewRef.current.k
      const curCanvasY = (e.clientY - viewRef.current.y) / viewRef.current.k
      setWireDrag((prev) =>
        prev ? { ...prev, curX: curCanvasX, curY: curCanvasY } : null,
      )
      return
    }

    // B. 正在画框多选
    if (marquee) {
      const curCanvasX = (e.clientX - viewRef.current.x) / viewRef.current.k
      const curCanvasY = (e.clientY - viewRef.current.y) / viewRef.current.k
      setMarquee((prev) =>
        prev ? { ...prev, currentX: curCanvasX, currentY: curCanvasY } : null,
      )

      const minX = Math.min(marquee.startX, curCanvasX)
      const maxX = Math.max(marquee.startX, curCanvasX)
      const minY = Math.min(marquee.startY, curCanvasY)
      const maxY = Math.max(marquee.startY, curCanvasY)

      const intersected = tasks
        .filter((t) => {
          const tw = t.w || 420
          const th = t.h || 280
          return !(
            t.x + tw < minX ||
            t.x > maxX ||
            t.y + th < minY ||
            t.y > maxY
          )
        })
        .map((t) => t.id)

      const nextSet = new Set(intersected)
      onSelectTasks?.(nextSet)
      onSelectTask?.(intersected.length > 0 ? intersected[0] : null)
      return
    }

    // C. 正在拖动节点位置 (单节点或成组多选协同移动)
    const nodeDrag = nodeDragRef.current
    if (nodeDrag) {
      const dx = (e.clientX - nodeDrag.sx) / viewRef.current.k
      const dy = (e.clientY - nodeDrag.sy) / viewRef.current.k
      if (!nodeDrag.moved && Math.hypot(dx, dy) > 3) {
        nodeDrag.moved = true
        hasUserInteractedRef.current = true
        setDraggingTaskId(nodeDrag.taskId)
      }
      if (nodeDrag.moved) {
        if (nodeDrag.groupOrigins.size > 1 && onUpdateMultipleTaskPositions) {
          const newPosMap = new Map<string, { x: number; y: number }>()
          for (const [id, orig] of nodeDrag.groupOrigins) {
            newPosMap.set(id, {
              x: Math.round(orig.x + dx),
              y: Math.round(orig.y + dy),
            })
          }
          onUpdateMultipleTaskPositions(newPosMap)
        } else if (onUpdateTaskPosition) {
          onUpdateTaskPosition(
            nodeDrag.taskId,
            Math.round(nodeDrag.ox + dx),
            Math.round(nodeDrag.oy + dy),
          )
        }
      }
      return
    }

    // D. 正在平移画布
    const pan = panRef.current
    if (pan) {
      const dx = e.clientX - pan.sx
      const dy = e.clientY - pan.sy
      if (!pan.moved && Math.hypot(dx, dy) > 3) {
        pan.moved = true
        hasUserInteractedRef.current = true
      }
      if (pan.moved) {
        updateView((prev) => ({
          ...prev,
          x: pan.ox + dx,
          y: pan.oy + dy,
        }))
      }
    }
  }

  const handlePointerUp = (e: React.PointerEvent) => {
    // 释放拉线
    if (wireDrag) {
      const target = document.elementFromPoint(e.clientX, e.clientY)
      const targetCard = target?.closest(".dc-card")
      const targetTaskId = targetCard?.getAttribute("data-task-id")
      if (targetTaskId && targetTaskId !== wireDrag.fromTaskId) {
        onConnect?.(wireDrag.fromTaskId, targetTaskId)
      }
      setWireDrag(null)
      return
    }

    // 释放画框多选
    if (marquee) {
      setMarquee(null)
      return
    }

    // 释放节点拖拽
    if (nodeDragRef.current) {
      const { taskId, moved } = nodeDragRef.current
      nodeDragRef.current = null
      setDraggingTaskId(null)
      if (!moved) {
        // 单击卡片未移动：单选节点
        onSelectTasks?.(new Set([taskId]))
        onSelectTask?.(taskId)
      }
      return
    }

    // 释放画布平移
    if (panRef.current) {
      const { moved } = panRef.current
      panRef.current = null
      setIsPanning(false)

      if (!moved) {
        // 点击画布纯空白处：取消选中
        // 【关键保护】：若点击目标在展开的卡片内部，绝不触发收起，避免误操作！
        const pointerTarget = e.target as HTMLElement
        const isInsideExpandedCard =
          !!pointerTarget.closest?.(".dc-card.expanded")

        onSelectTasks?.(new Set())
        onSelectTask?.(null)
        setSelectedEdgeKey(null)
        if (activeTaskId && !isInsideExpandedCard) {
          onCloseTask()
        }
      }
    }
  }

  const handlePointerCancel = () => {
    setWireDrag(null)
    setMarquee(null)
    nodeDragRef.current = null
    setDraggingTaskId(null)
    panRef.current = null
    setIsPanning(false)
  }

  return (
    <div
      className={`dc-canvas-viewport ${toolMode === "select" ? "mode-select" : "mode-hand"} ${
        isPanning ? "is-panning" : ""
      } ${spacePressed ? "space-pressed" : ""}`}
      ref={containerRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onDoubleClick={(e) => {
        const target = e.target as HTMLElement
        if (
          !target.closest(
            ".dc-card, .dc-canvas-controls, .dc-bottom-prompt-bar",
          )
        ) {
          flyToOverview()
        }
      }}
    >
      {/* 空间网格点阵底纹 */}
      <div
        className="dc-canvas-grid-bg"
        style={{
          backgroundSize: `${32 * view.k}px ${32 * view.k}px`,
          backgroundPosition: `${view.x}px ${view.y}px`,
        }}
      />

      {/* 画框多选半透明矩形框 (Marquee Box) */}
      {marquee && (
        <div
          className="dc-marquee-box"
          style={{
            left: Math.min(marquee.startX, marquee.currentX) * view.k + view.x,
            top: Math.min(marquee.startY, marquee.currentY) * view.k + view.y,
            width: Math.abs(marquee.currentX - marquee.startX) * view.k,
            height: Math.abs(marquee.currentY - marquee.startY) * view.k,
          }}
        />
      )}

      {/* 画布主缩放变换层 */}
      <div
        className="dc-canvas-stage"
        style={{
          transform: `translate(${Math.round(view.x)}px, ${Math.round(view.y)}px) scale(${view.k})`,
        }}
      >
        {/* 全局 SVG 拓扑依赖连线图层：动态边界，跟随任务坐标延展 */}
        <svg
          className="dc-canvas-svg-layer"
          style={{
            left: svgBounds.minX,
            top: svgBounds.minY,
            width: svgBounds.width,
            height: svgBounds.height,
          }}
        >
          <defs>
            <marker
              id="dc-arrowhead"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path
                d="M 0 1.5 L 8 5 L 0 8.5 z"
                fill="var(--line-hover, #94a3b8)"
              />
            </marker>
            <marker
              id="dc-arrowhead-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="var(--pri, #2dd4bf)" />
            </marker>
            <marker
              id="dc-arrowhead-blocked"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--red, #f43f5e)" />
            </marker>
          </defs>

          {/* 1. 正常拓扑依赖连线 (自适应横向 LR 与纵向 TB) */}
          {edges.map((edge, idx) => {
            const fromTask = tasks.find((t) => t.id === edge.from)
            const toTask = tasks.find((t) => t.id === edge.to)
            if (!fromTask || !toTask) return null

            const fromExpanded = fromTask.id === activeTaskId
            const toExpanded = toTask.id === activeTaskId

            const fromW = fromExpanded ? EXPANDED_CARD_WIDTH : fromTask.w
            const fromH = fromExpanded
              ? EXPANDED_CARD_HEIGHT
              : fromTask.h || 280
            const fromX = fromExpanded
              ? fromTask.x - (EXPANDED_CARD_WIDTH - fromTask.w) / 2
              : fromTask.x
            const fromY = fromExpanded
              ? fromTask.y - (EXPANDED_CARD_HEIGHT - (fromTask.h || 280)) / 2
              : fromTask.y

            const toW = toExpanded ? EXPANDED_CARD_WIDTH : toTask.w
            const toH = toExpanded ? EXPANDED_CARD_HEIGHT : toTask.h || 280
            const toX = toExpanded
              ? toTask.x - (EXPANDED_CARD_WIDTH - toTask.w) / 2
              : toTask.x
            const toY = toExpanded
              ? toTask.y - (EXPANDED_CARD_HEIGHT - (toTask.h || 280)) / 2
              : toTask.y

            const isVertical = layoutDirection === "vertical"
            const bx = svgBounds.minX
            const by = svgBounds.minY
            let x1: number, y1: number, x2: number, y2: number
            let pathD = ""

            if (isVertical) {
              // 纵向连接：从父节点底部中心到子节点顶部中心
              x1 = fromX + fromW / 2 - bx
              y1 = fromY + fromH - by
              x2 = toX + toW / 2 - bx
              y2 = toY - by

              const deltaY = y2 - y1
              const dy = Math.max(50, Math.abs(deltaY) * 0.48)
              pathD =
                deltaY >= 0
                  ? `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
                  : `M ${x1} ${y1} C ${x1} ${y1 + 80}, ${x2} ${y2 - 80}, ${x2} ${y2}`
            } else {
              // 横向连接：从父节点右侧中心到子节点左侧中心
              x1 = fromX + fromW - bx
              y1 = fromY + fromH / 2 - by
              x2 = toX - bx
              y2 = toY + toH / 2 - by

              const deltaX = x2 - x1
              const dx = Math.max(50, Math.abs(deltaX) * 0.48)
              pathD =
                deltaX >= 0
                  ? `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
                  : `M ${x1} ${y1} C ${x1 + 80} ${y1}, ${x2 - 80} ${y2}, ${x2} ${y2}`
            }

            const isFlowing = activeFlowEdge === `${edge.from}>${edge.to}`
            const isBlocked =
              toTask.status === "blocked" || fromTask.status === "failed"
            const isEdgeSelected = selectedEdgeKey === `${edge.from}>${edge.to}`

            return (
              <g key={`${edge.from}-${edge.to}-${idx}`}>
                {isFlowing && (
                  <path className="dc-bezier-path-glow" d={pathD} />
                )}
                <path
                  className={`dc-bezier-path ${isFlowing ? "active-flow" : ""} ${
                    isBlocked ? "blocked-flow" : ""
                  } ${isEdgeSelected ? "selected-edge" : ""}`}
                  d={pathD}
                  onClick={(e) => {
                    e.stopPropagation()
                    setSelectedEdgeKey(
                      isEdgeSelected ? null : `${edge.from}>${edge.to}`,
                    )
                  }}
                  markerEnd={
                    isBlocked
                      ? "url(#dc-arrowhead-blocked)"
                      : isFlowing || isEdgeSelected
                        ? "url(#dc-arrowhead-active)"
                        : "url(#dc-arrowhead)"
                  }
                />
                {isFlowing && (
                  <circle r="5" className="dc-flow-particle">
                    <animateMotion dur="0.55s" repeatCount="1" path={pathD} />
                  </circle>
                )}
              </g>
            )
          })}

          {/* 2. 交互式拖拽拉线临时虚线 (Ghost Wire) */}
          {wireDrag && (
            <path
              className="dc-ghost-wire"
              d={
                layoutDirection === "vertical"
                  ? `M ${wireDrag.sx - svgBounds.minX} ${wireDrag.sy - svgBounds.minY} C ${wireDrag.sx - svgBounds.minX} ${
                      wireDrag.sy + 60 - svgBounds.minY
                    }, ${wireDrag.curX - svgBounds.minX} ${wireDrag.curY - 60 - svgBounds.minY}, ${wireDrag.curX - svgBounds.minX} ${
                      wireDrag.curY - svgBounds.minY
                    }`
                  : `M ${wireDrag.sx - svgBounds.minX} ${wireDrag.sy - svgBounds.minY} C ${wireDrag.sx + 60 - svgBounds.minX} ${
                      wireDrag.sy - svgBounds.minY
                    }, ${wireDrag.curX - 60 - svgBounds.minX} ${wireDrag.curY - svgBounds.minY}, ${wireDrag.curX - svgBounds.minX} ${
                      wireDrag.curY - svgBounds.minY
                    }`
              }
            />
          )}
        </svg>

        {/* 悬浮在脑图连线中点的产出语义标签与断开菜单 */}
        {edges.map((edge, idx) => {
          const fromTask = tasks.find((t) => t.id === edge.from)
          const toTask = tasks.find((t) => t.id === edge.to)
          if (!fromTask || !toTask) return null

          const fromExpanded = fromTask.id === activeTaskId
          const toExpanded = toTask.id === activeTaskId

          const fromW = fromExpanded ? EXPANDED_CARD_WIDTH : fromTask.w
          const fromH = fromExpanded ? EXPANDED_CARD_HEIGHT : fromTask.h || 280
          const fromX = fromExpanded
            ? fromTask.x - (EXPANDED_CARD_WIDTH - fromTask.w) / 2
            : fromTask.x
          const fromY = fromExpanded
            ? fromTask.y - (EXPANDED_CARD_HEIGHT - (fromTask.h || 280)) / 2
            : fromTask.y

          const toW = toExpanded ? EXPANDED_CARD_WIDTH : toTask.w
          const toH = toExpanded ? EXPANDED_CARD_HEIGHT : toTask.h || 280
          const toX = toExpanded
            ? toTask.x - (EXPANDED_CARD_WIDTH - toTask.w) / 2
            : toTask.x
          const toY = toExpanded
            ? toTask.y - (EXPANDED_CARD_HEIGHT - (toTask.h || 280)) / 2
            : toTask.y

          const isVertical = layoutDirection === "vertical"
          const x1 = isVertical ? fromX + fromW / 2 : fromX + fromW
          const y1 = isVertical ? fromY + fromH : fromY + fromH / 2
          const x2 = isVertical ? toX + toW / 2 : toX
          const y2 = isVertical ? toY : toY + toH / 2

          const mx = (x1 + x2) / 2
          const my = (y1 + y2) / 2
          const isEdgeSelected = selectedEdgeKey === `${edge.from}>${edge.to}`

          return (
            <React.Fragment key={`lbl-${edge.from}-${edge.to}-${idx}`}>
              <div
                className={`dc-edge-badge ${isEdgeSelected ? "selected" : ""}`}
                style={{ left: mx, top: my }}
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedEdgeKey(
                    isEdgeSelected ? null : `${edge.from}>${edge.to}`,
                  )
                }}
                title={`单击管理依赖：从 #T-${fromTask.taskNo} 注入 #T-${toTask.taskNo}`}
              >
                {edge.payloadLabel}
              </div>

              {/* 连线选中弹出浮层：断开连线 */}
              {isEdgeSelected && (
                <div className="dc-edge-popover" style={{ left: mx, top: my }}>
                  <span>
                    #T-{fromTask.taskNo} ➔ #T-{toTask.taskNo}
                  </span>
                  <button
                    className="dc-edge-del-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDisconnect?.(edge.from, edge.to)
                      setSelectedEdgeKey(null)
                    }}
                    title="断开这两个任务间的依赖连线"
                  >
                    断开连线 ✕
                  </button>
                  <button
                    className="dc-icon-btn"
                    style={{ width: 18, height: 18 }}
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedEdgeKey(null)
                    }}
                  >
                    <X size={11} />
                  </button>
                </div>
              )}
            </React.Fragment>
          )
        })}

        {/* 通用任务卡片集群：单击/画框选中，双击展开，主体拖动 */}
        {tasks.map((task) => (
          <DutyNodeCard
            key={task.id}
            task={task}
            allTasks={tasks}
            zoom={view.k}
            layoutDirection={layoutDirection}
            isFocused={task.id === activeTaskId}
            isSelected={isTaskSelected(task.id)}
            isDimmed={
              (!!activeTaskId && task.id !== activeTaskId) ||
              Boolean(
                !activeTaskId &&
                  highlightStatuses &&
                  highlightStatuses.length > 0 &&
                  !highlightStatuses.includes(task.status),
              )
            }
            stepIndex={stepIndexMap[task.id] ?? 0}
            isDragging={draggingTaskId === task.id}
            isFullscreen={isNodeFullscreen && task.id === activeTaskId}
            onToggleFullscreen={() => setIsNodeFullscreen((prev) => !prev)}
            onSelect={() => {
              onSelectTasks?.(new Set([task.id]))
              onSelectTask?.(task.id)
            }}
            onFocus={() => {
              flyToCard(task, undefined, 480, true)
              onTaskClick(task.id)
            }}
            onUnfocus={() => {
              // 原地收起卡片，绝不调用 flyToOverview！
              setIsNodeFullscreen(false)
              onCloseTask()
            }}
            onPortPointerDown={handlePortPointerDown}
            onTaskFission={onTaskFission}
            onPickOption={onPickOption}
            onApprove={onApprove}
            onReject={onReject}
            onArbitrate={onArbitrate}
            onConfirmHitl={onConfirmHitl}
            onCancelHitl={onCancelHitl}
            onSubmitTextHitl={onSubmitTextHitl}
            onSubmitChoiceHitl={onSubmitChoiceHitl}
            onSubmitMultiChoiceHitl={onSubmitMultiChoiceHitl}
          />
        ))}
      </div>

      {/* ── 全屏节点工作页面（扩展到整个右侧面板） ── */}
      {isNodeFullscreen &&
        activeTaskId &&
        (() => {
          const currentActiveTask = tasks.find((t) => t.id === activeTaskId)
          if (!currentActiveTask) return null
          return (
            <div
              className="dc-node-fullscreen-overlay"
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <DutyNodePageContent
                task={currentActiveTask}
                allTasks={tasks}
                stepIndex={stepIndexMap[currentActiveTask.id] ?? 0}
                isFullscreen={true}
                onToggleFullscreen={() => setIsNodeFullscreen(false)}
                onClose={() => {
                  setIsNodeFullscreen(false)
                  onCloseTask()
                }}
                onPickOption={onPickOption}
                onApprove={onApprove}
                onConfirmProposal={onConfirmProposalTask}
                onReject={onReject}
                onArbitrate={onArbitrate}
                onConfirmHitl={onConfirmHitl}
                onCancelHitl={onCancelHitl}
                onSubmitTextHitl={onSubmitTextHitl}
                onSubmitChoiceHitl={onSubmitChoiceHitl}
                onSubmitMultiChoiceHitl={onSubmitMultiChoiceHitl}
              />
            </div>
          )
        })()}

      {/* ── 当画布无任何任务时的居中空状态引导（置于视口层，不随画布缩放漂移或被零宽压缩） ── */}
      {tasks.length === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none select-none z-10 -translate-y-12">
          <div className="flex flex-col items-center gap-2.5 max-w-sm px-6 py-5 rounded-2xl bg-background/60 border border-border/50 backdrop-blur-xs text-center shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
              <Workflow size={20} />
            </div>
            <div className="text-sm font-medium text-foreground/85">
              当前工作空间暂无自主值守任务
            </div>
            <div className="text-xs text-muted-foreground leading-relaxed">
              可在下方输入框输入任务指令，由 Agent 自动规划排入脑图
            </div>
          </div>
        </div>
      )}

      {/* ── 画布中央底部悬浮区域：宽尺寸输入卡片 + 贴底漏出的 100% 实色精致操作栏 ── */}
      <div
        className={`dc-bottom-dock-wrap ${isNodeFullscreen ? "hidden" : ""}`}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {/* 输入卡片主体 (置于上层 z-10，完全 100% 实底不透明) */}
        <div className="dc-bottom-dock-input">
          {renderInputBar?.({
            selectedTask,
            selectedTaskIds: selectedTaskIds ?? new Set(),
            isMultiSelected,
            onFocusTask: (task) => {
              flyToCard(task, undefined, 480, true)
              onTaskClick(task.id)
            },
            onClearSelection: () => {
              onSelectTasks?.(new Set())
              onSelectTask?.(null)
            },
          })}
        </div>

        {/* ── 贴底漏出的操作工具栏（比输入框窄，100% 实色无透明度，负 margin 向上塞入输入框底边） ── */}
        <div className="dc-bottom-dock-toolbar">
          {/* 左组：节点聚焦放大 / 整理 / 排列方向 */}
          <div className="flex items-center gap-1.5 min-w-0">
            {selectedTask && (
              <button
                type="button"
                onClick={() => {
                  flyToCard(selectedTask, undefined, 480, true)
                  onTaskClick(selectedTask.id)
                }}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-primary bg-primary/10 hover:bg-primary/20 transition-colors cursor-pointer"
                title="聚焦并在画布中央原地放大为现场工作页面"
              >
                <span>🎯 聚焦放大</span>
              </button>
            )}

            {onResetAutoLayout && (
              <button
                type="button"
                onClick={() => {
                  hasUserInteractedRef.current = false
                  onResetAutoLayout()
                  setTimeout(() => centerInitialView(), 30)
                }}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer"
                title="一键整理：自动消除错位并恢复优雅排版"
              >
                <span>⚡ 整理</span>
              </button>
            )}

            {onToggleDirection && (
              <button
                type="button"
                onClick={onToggleDirection}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer"
                title={
                  layoutDirection === "vertical"
                    ? "切换为横向展开排列 (从左向右)"
                    : "切换为纵向展开排列 (从上向下，契合鼠标滚轮上下滚动)"
                }
              >
                <span>
                  {layoutDirection === "vertical" ? "⇄ 横向" : "⇅ 纵向"}
                </span>
              </button>
            )}
          </div>

          {/* 右组：抓手 / 框选 / 缩放控制 */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              className={cn(
                "p-1 rounded-md transition-colors cursor-pointer",
                toolMode === "hand"
                  ? "text-primary bg-primary/15 font-medium"
                  : "hover:text-foreground hover:bg-muted/70",
              )}
              onClick={() => setToolMode("hand")}
              title="抓手模式 (Hand)：在画布空白处拖拽平移视口"
            >
              <Hand size={14} />
            </button>
            <button
              type="button"
              className={cn(
                "p-1 rounded-md transition-colors cursor-pointer",
                toolMode === "select"
                  ? "text-primary bg-primary/15 font-medium"
                  : "hover:text-foreground hover:bg-muted/70",
              )}
              onClick={() => setToolMode("select")}
              title="框选模式 (Marquee Select)：在画布空白处拉框多选节点"
            >
              <BoxSelect size={14} />
            </button>

            <span className="h-3 w-[1px] bg-border/80 mx-1" />

            <button
              type="button"
              className="px-1.5 py-0.5 rounded-md hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer font-bold"
              onClick={() =>
                updateView((v) => ({ ...v, k: clamp(v.k * 0.82, 0.18, 3.0) }))
              }
              title="缩小画布 (Zoom Out)"
            >
              −
            </button>
            <button
              type="button"
              className="px-1 py-0.5 rounded-md hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer min-w-[42px] text-center font-mono text-[11px]"
              onClick={() => updateView((v) => ({ ...v, k: 1.0 }))}
              title="点击重置为 100% 缩放"
            >
              {Math.round(view.k * 100)}%
            </button>
            <button
              type="button"
              className="px-1.5 py-0.5 rounded-md hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer font-bold"
              onClick={() =>
                updateView((v) => ({ ...v, k: clamp(v.k * 1.22, 0.18, 3.0) }))
              }
              title="放大画布 (Zoom In)"
            >
              ＋
            </button>
            <button
              type="button"
              className="px-1.5 py-0.5 rounded-md hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer"
              onClick={() => flyToOverview()}
              title="一键自适应全览 (Fit All)"
            >
              ⌂
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
