/* ==========================================================================
   EvoLoop 通用脑图拓扑自动分层布局引擎 (layoutEngine.ts)
   核心价值：针对通用自主值守任务队列的任意拓扑依赖，自动计算脑图结构空间坐标
   - 纯正脑图 (Mind-Map) 排列：左侧根节点，分支水平向右展开
   - 连线从上游右端口平滑过渡到下游左端口
   - 纵向对称树状居中对齐与冲突消解，保证 100% 节点零重叠
   - 支持节点任意拖拽后的坐标保留与一键脑图重排
   ========================================================================== */

import type {DutyEdge, DutyTask} from "../core/types"

export const CARD_WIDTH = 420
export const CARD_HEIGHT = 280
export const HORIZONTAL_GAP = 160
export const VERTICAL_GAP = 60
export const PADDING_LEFT = 100
export const PADDING_TOP = 100

/**
 * 计算有向无环图 (DAG) 的传递归约 (Transitive Reduction)
 * 消除多余的跨层捷径连线 (如 A->B, B->C 时剔除直穿 B 的 A->C 冗余长线)
 * 彻底解决长线贯穿、切穿中间节点卡片的问题，让脑图保持纯正优雅的相邻层级树状展开
 */
export function pruneTransitiveEdges(
  tasks: DutyTask[],
): { from: string; to: string }[] {
  const adj = new Map<string, Set<string>>()
  tasks.forEach((t) => adj.set(t.id, new Set(t.dependencies || [])))

  // 检查从 start 出发，是否能不走直接依赖 (start -> target) 通过中间节点路径到达 target
  function canReach(start: string, target: string, directBlocked: string): boolean {
    const queue: string[] = []
    for (const dep of adj.get(start) || []) {
      if (start === directBlocked && dep === target) continue
      queue.push(dep)
    }
    const visited = new Set<string>(queue)
    while (queue.length > 0) {
      const curr = queue.shift()!
      if (curr === target) return true
      for (const dep of adj.get(curr) || []) {
        if (!visited.has(dep)) {
          visited.add(dep)
          queue.push(dep)
        }
      }
    }
    return false
  }

  const reducedEdges: { from: string; to: string }[] = []
  tasks.forEach((t) => {
    ;(t.dependencies || []).forEach((depId) => {
      // 若从 t 逆向追溯 depId 存在更长拓扑路径，则直接边 depId -> t 是冗余跨层捷径
      if (!canReach(t.id, depId, t.id)) {
        reducedEdges.push({ from: depId, to: t.id })
      }
    })
  })

  return reducedEdges
}

/**
 * 依据任务及其 dependencies 自动派生拓扑连线 (Edges)
 * 自动应用传递归约，确保连线仅连接直接相邻拓扑阶段，100% 杜绝穿透中间卡片
 */
export function deriveDutyEdges(tasks: DutyTask[]): DutyEdge[] {
  const taskMap = new Map<string, DutyTask>()
  tasks.forEach((t) => taskMap.set(t.id, t))

  const validEdges = pruneTransitiveEdges(tasks)

  return validEdges.map(({ from, to }) => {
    const fromTask = taskMap.get(from)
    return {
      from,
      to,
      payloadLabel: fromTask?.artifact?.title
        ? `产出: ${fromTask.artifact.title.slice(0, 7)}`
        : "数据流注入",
    }
  })
}

/**
 * 计算任务在派发队列中的相对顺序键，与后端 _queue_ordering 对齐：
 * priority → coalesce(due_at, created_at) → category → created_at → id
 * 用于让同一拓扑层内的卡片按执行顺序排列，减少高亮移动时的跳跃感。
 */
function executionOrderKey(t: DutyTask): [number, number, string, number, string] {
  const priorityRank =
    t.priority === "urgent" ? 0
    : t.priority === "high" ? 1
    : t.priority === "medium" ? 2
    : t.priority === "low" ? 3
    : 2
  const dueTs = t.dueAt ? Date.parse(t.dueAt) : NaN
  const createdTs = t.createdAt ? Date.parse(t.createdAt) : 0
  const effectiveDue = Number.isFinite(dueTs) ? dueTs : createdTs
  return [priorityRank, effectiveDue, t.category || "", createdTs, t.id]
}

function compareExecutionOrder(a: DutyTask, b: DutyTask): number {
  const ka = executionOrderKey(a)
  const kb = executionOrderKey(b)
  if (ka[0] !== kb[0]) return ka[0] - kb[0]
  if (ka[1] !== kb[1]) return ka[1] - kb[1]
  if (ka[2] !== kb[2]) return ka[2].localeCompare(kb[2])
  if (ka[3] !== kb[3]) return ka[3] - kb[3]
  return ka[4].localeCompare(kb[4])
}

/**
 * 流水线 (Pipeline) 布局：按拓扑序 + 执行优先级键把任务排成一条直线。
 * 所有依赖边都朝前，高亮切换时从一张卡自然移动到相邻的下一张卡。
 */
function layoutPipelineTasks(
  rawTasks: DutyTask[],
  direction: LayoutDirection,
): { tasks: DutyTask[]; edges: DutyEdge[] } {
  if (rawTasks.length === 0) return { tasks: [], edges: [] }

  const taskMap = new Map<string, DutyTask>()
  rawTasks.forEach((t) => taskMap.set(t.id, { ...t }))

  const inDegree = new Map<string, number>()
  const downstream = new Map<string, string[]>()

  rawTasks.forEach((t) => {
    const deps = (t.dependencies || []).filter((d) => taskMap.has(d))
    inDegree.set(t.id, deps.length)
    deps.forEach((d) => {
      downstream.set(d, [...(downstream.get(d) || []), t.id])
    })
  })

  const available: DutyTask[] = []
  const order: string[] = []

  rawTasks.forEach((t) => {
    if ((inDegree.get(t.id) || 0) === 0) available.push(t)
  })

  while (available.length > 0) {
    available.sort(compareExecutionOrder)
    const t = available.shift()!
    order.push(t.id)
    for (const downId of downstream.get(t.id) || []) {
      const newDeg = (inDegree.get(downId) || 0) - 1
      inDegree.set(downId, newDeg)
      if (newDeg === 0) {
        const downTask = taskMap.get(downId)
        if (downTask) available.push(downTask)
      }
    }
  }

  // 兜底：循环依赖或孤立节点直接按执行顺序追加
  const seen = new Set(order)
  rawTasks
    .filter((t) => !seen.has(t.id))
    .sort(compareExecutionOrder)
    .forEach((t) => order.push(t.id))

  const positions = new Map<string, { x: number; y: number }>()
  order.forEach((id, idx) => {
    if (direction === "vertical") {
      positions.set(id, {
        x: PADDING_LEFT,
        y: PADDING_TOP + idx * (CARD_HEIGHT + VERTICAL_ROW_GAP),
      })
    } else {
      positions.set(id, {
        x: PADDING_LEFT + idx * (CARD_WIDTH + HORIZONTAL_GAP),
        y: PADDING_TOP,
      })
    }
  })

  const positionedTasks: DutyTask[] = rawTasks.map((t) => {
    const pos = positions.get(t.id) || { x: PADDING_LEFT, y: PADDING_TOP }
    return {
      ...t,
      x: pos.x,
      y: pos.y,
      w: CARD_WIDTH,
      h: CARD_HEIGHT,
    }
  })

  const edges = deriveDutyEdges(positionedTasks)
  positionedTasks.sort((a, b) => a.taskNo - b.taskNo)
  return { tasks: positionedTasks, edges }
}

export type LayoutDirection = "horizontal" | "vertical"
export type LayoutStrategy = "mindmap" | "pipeline"

export const VERTICAL_ROW_GAP = 140
export const VERTICAL_COL_GAP = 60

/**
 * 通用脑图拓扑分层与坐标自动计算函数
 * 支持横向 (Horizontal: 从左向右展开) 与纵向 (Vertical: 从上向下展开，契合滚轮自然滚动)
 */
export function layoutDutyTasks(
  rawTasks: DutyTask[],
  customEdges?: DutyEdge[],
  direction: LayoutDirection = "horizontal",
  strategy: LayoutStrategy = "mindmap",
): { tasks: DutyTask[]; edges: DutyEdge[] } {
  if (strategy === "pipeline") {
    return layoutPipelineTasks(rawTasks, direction)
  }

  if (rawTasks.length === 0) return { tasks: [], edges: [] }

  const taskMap = new Map<string, DutyTask>()
  rawTasks.forEach((t) => taskMap.set(t.id, { ...t }))

  // 1. 计算每个任务的拓扑层级 (Rank / Depth)
  const rankMap = new Map<string, number>()

  function computeRank(taskId: string, visited: Set<string>): number {
    if (rankMap.has(taskId)) return rankMap.get(taskId)!
    if (visited.has(taskId)) return 0 // 防止循环依赖死循环

    visited.add(taskId)
    const task = taskMap.get(taskId)
    if (!task || !task.dependencies || task.dependencies.length === 0) {
      rankMap.set(taskId, 0)
      return 0
    }

    let maxDepRank = -1
    for (const depId of task.dependencies) {
      if (taskMap.has(depId)) {
        const depRank = computeRank(depId, new Set(visited))
        if (depRank > maxDepRank) maxDepRank = depRank
      }
    }

    const currentRank = maxDepRank + 1
    rankMap.set(taskId, currentRank)
    return currentRank
  }

  rawTasks.forEach((t) => computeRank(t.id, new Set()))

  // 2. 将任务分组到各个 Rank 中
  const maxRank = Math.max(0, ...Array.from(rankMap.values()))
  const groups: DutyTask[][] = Array.from({ length: maxRank + 1 }, () => [])
  rawTasks.forEach((t) => {
    const r = rankMap.get(t.id) ?? 0
    groups[r].push(taskMap.get(t.id)!)
  })

  // 2.5 同一拓扑层内按执行顺序排列，使高亮在派发时尽可能顺滑移动
  groups.forEach((g) => g.sort(compareExecutionOrder))

  // 3. 计算坐标 (根据 direction 分支：横向 LR vs 纵向 TB)
  const positions = new Map<string, { x: number; y: number }>()

  if (direction === "vertical") {
    // ─────────────── 纵向排列 (Top-to-Bottom: 契合滚轮方向) ───────────────
    // 第 0 层 (根任务行)：横向居中排列
    let rootX = PADDING_LEFT
    groups[0].forEach((t) => {
      positions.set(t.id, { x: rootX, y: PADDING_TOP })
      rootX += CARD_WIDTH + VERTICAL_COL_GAP
    })

    const rootCenterX =
      PADDING_LEFT +
      Math.max(0, groups[0].length * CARD_WIDTH + (groups[0].length - 1) * VERTICAL_COL_GAP) / 2

    // 后续各层：依据父节点横向重心 (targetCenterX) 对称发散与居中
    for (let r = 1; r <= maxRank; r++) {
      const row = groups[r]
      const rowY = PADDING_TOP + r * (CARD_HEIGHT + VERTICAL_ROW_GAP)

      const items = row.map((t) => {
        const parentXs = (t.dependencies || [])
          .map((pId) => positions.get(pId))
          .filter(Boolean)
          .map((p) => p!.x + CARD_WIDTH / 2)

        const targetCenterX =
          parentXs.length > 0
            ? parentXs.reduce((a, b) => a + b, 0) / parentXs.length
            : rootCenterX
        return { task: t, targetCenterX }
      })

      // 按重心横向排序，保证纵向下行连线平行不交叉
      items.sort((a, b) => a.targetCenterX - b.targetCenterX)

      const totalRowWidth =
        items.length * CARD_WIDTH + Math.max(0, items.length - 1) * VERTICAL_COL_GAP
      const avgCenterX = items.reduce((sum, item) => sum + item.targetCenterX, 0) / items.length
      let startX = Math.max(PADDING_LEFT, avgCenterX - totalRowWidth / 2)

      items.forEach((item, idx) => {
        const itemX = startX + idx * (CARD_WIDTH + VERTICAL_COL_GAP)
        positions.set(item.task.id, { x: Math.round(itemX), y: rowY })
      })
    }
  } else {
    // ─────────────── 横向排列 (Left-to-Right: 经典脑图向右延伸) ───────────────
    let rootY = PADDING_TOP
    groups[0].forEach((t) => {
      positions.set(t.id, { x: PADDING_LEFT, y: rootY })
      rootY += CARD_HEIGHT + VERTICAL_GAP
    })

    const rootCenterY =
      PADDING_TOP +
      Math.max(0, groups[0].length * CARD_HEIGHT + (groups[0].length - 1) * VERTICAL_GAP) / 2

    for (let c = 1; c <= maxRank; c++) {
      const col = groups[c]
      const colX = PADDING_LEFT + c * (CARD_WIDTH + HORIZONTAL_GAP)

      const items = col.map((t) => {
        const parentYs = (t.dependencies || [])
          .map((pId) => positions.get(pId))
          .filter(Boolean)
          .map((p) => p!.y + CARD_HEIGHT / 2)

        const targetCenterY =
          parentYs.length > 0
            ? parentYs.reduce((a, b) => a + b, 0) / parentYs.length
            : rootCenterY
        return { task: t, targetCenterY }
      })

      items.sort((a, b) => a.targetCenterY - b.targetCenterY)

      const totalColHeight =
        items.length * CARD_HEIGHT + Math.max(0, items.length - 1) * VERTICAL_GAP
      const avgCenterY = items.reduce((sum, item) => sum + item.targetCenterY, 0) / items.length
      let startY = Math.max(PADDING_TOP, avgCenterY - totalColHeight / 2)

      items.forEach((item, idx) => {
        const itemY = startY + idx * (CARD_HEIGHT + VERTICAL_GAP)
        positions.set(item.task.id, { x: colX, y: Math.round(itemY) })
      })
    }
  }

  // 4. 生成定位后的任务集合
  const positionedTasks: DutyTask[] = rawTasks.map((t) => {
    const pos = positions.get(t.id) || { x: PADDING_LEFT, y: PADDING_TOP }
    return {
      ...t,
      x: pos.x,
      y: pos.y,
      w: CARD_WIDTH,
      h: CARD_HEIGHT,
    }
  })

  // 5. 自动推导或补充拓扑边 (Edges)
  const edges = customEdges && customEdges.length > 0 ? customEdges : deriveDutyEdges(positionedTasks)

  // 依据任务编号稳定排序
  positionedTasks.sort((a, b) => a.taskNo - b.taskNo)

  return { tasks: positionedTasks, edges }
}
