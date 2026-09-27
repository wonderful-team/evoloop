/* ==========================================================================
 * EvoLoop 自主值守工作台 · 状态元数据单一来源 (core/statusMeta.ts)
 * ==========================================================================
 * 后端队列状态 → 展示元数据（中文标签/圆点/徽章底色/终态标记）的唯一映射。
 * 组件不再各自维护 status→label/颜色 三元组（2026-09-25 收敛前在 7 个
 * 组件里散落 60+ 处字面量，后端状态词汇一变就要全仓对齐）。
 *
 * 用法：渲染状态标签/颜色一律 `statusMeta(task.status)`；业务逻辑判断
 * （tab 过滤、门控）保留 `task.status === "…"` 的类型化比较。
 */

import type { DutyTaskStatus } from "./types"

export interface StatusMeta {
  /** 中文短标签（看板/卡片通用；节点页等需要长文案处可再包一层） */
  label: string
  /** 状态圆点色（tailwind bg-*) */
  dotCls: string
  /** 徽标/胶囊底色与前景（tailwind) */
  pillCls: string
  /** 画布节点卡 CSS 状态词（dc-card/dot 类名，styles/duty-canvas.css 消费） */
  cardCls: "run" | "done" | "proposed" | "wait" | "fail" | "lock"
  /** 状态图形符号（节点卡/状态条共用） */
  glyph: string
  /** 终态（completed/failed/cancelled）：行内折叠、依赖门控判定共用 */
  terminal: boolean
}

const PENDING: StatusMeta = {
  label: "待执行",
  dotCls: "bg-slate-400 dark:bg-slate-500",
  pillCls: "bg-muted text-muted-foreground",
  cardCls: "lock",
  glyph: "○",
  terminal: false,
}

const RUNNING: StatusMeta = {
  label: "执行中",
  dotCls: "bg-primary",
  pillCls: "bg-primary/10 text-primary",
  cardCls: "run",
  glyph: "⟳",
  terminal: false,
}

export const STATUS_META: Record<DutyTaskStatus, StatusMeta> = {
  pending: PENDING,
  in_progress: RUNNING,
  proposed: {
    label: "提案",
    dotCls: "bg-violet-500",
    pillCls: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    cardCls: "proposed",
    glyph: "💡",
    terminal: false,
  },
  waiting_acceptance: {
    label: "待验收",
    dotCls: "bg-sky-500",
    pillCls: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
    cardCls: "wait",
    glyph: "⏸",
    terminal: false,
  },
  /* 派生态（taskAdapter 由 waiting_acceptance+signoff 派生）：资金/安全门禁 */
  confirm: {
    label: "待安全授权",
    dotCls: "bg-amber-500",
    pillCls: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    cardCls: "wait",
    glyph: "⏸",
    terminal: false,
  },
  completed: {
    label: "已完成",
    dotCls: "bg-emerald-500",
    pillCls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    cardCls: "done",
    glyph: "✓",
    terminal: true,
  },
  failed: {
    label: "失败",
    dotCls: "bg-destructive",
    pillCls: "bg-destructive/10 text-destructive",
    cardCls: "fail",
    glyph: "⛔",
    terminal: true,
  },
  /* 派生态（上游断链阻塞，等人工裁决） */
  blocked: {
    label: "断链阻塞",
    dotCls: "bg-amber-500",
    pillCls: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    cardCls: "fail",
    glyph: "🔒",
    terminal: false,
  },
  cancelled: {
    label: "已取消",
    dotCls: "bg-muted-foreground/50",
    pillCls: "bg-muted text-muted-foreground",
    cardCls: "fail",
    glyph: "⊘",
    terminal: true,
  },
}

/** 状态元数据（未知状态 fail-open 到 pending 展示，不炸 UI） */
export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as DutyTaskStatus] ?? PENDING
}

/** 终态判定（completed/failed/cancelled）——与后端 QUEUE_TRANSITIONS 终态对齐 */
export function isTerminalStatus(status: string): boolean {
  return statusMeta(status).terminal
}
