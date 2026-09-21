/* ==========================================================================
   EvoLoop 自主值守工作台 · 左侧索引与「需要你处理」侧栏 (DutyLeftSidebar.tsx)
   对齐 EvoLoop Duty 界面中「需要你处理」与任务索引入口：
   - 快速提炼：商业拍板待办、资金安全门禁、断链仲裁
   - 过滤与状态筛选：快速在画布上聚焦对应任务卡片
   ========================================================================== */

import { useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Filter,
  AlertCircle,
  Clock,
  CheckCircle2,
  ListTodo,
} from "lucide-react"
import type { DutyTask, DutyTaskStatus } from "../core/types"

interface DutyLeftSidebarProps {
  tasks: DutyTask[]
  activeTaskId: string | null
  onSelectTask: (taskId: string) => void
}

export const DutyLeftSidebar = ({
  tasks,
  activeTaskId,
  onSelectTask,
}: DutyLeftSidebarProps) => {
  const [collapsed, setCollapsed] = useState(false)
  const [statusFilter, setStatusFilter] = useState<DutyTaskStatus | "all" | "needs_you">("all")

  // 需要用户处理的待办项
  const needsYouTasks = tasks.filter(
    (t) =>
      t.status === "waiting_acceptance" ||
      t.status === "confirm" ||
      t.status === "proposed" ||
      t.status === "failed" ||
      t.status === "blocked",
  )

  const filteredTasks = tasks.filter((t) => {
    if (statusFilter === "all") return true
    if (statusFilter === "needs_you") {
      return (
        t.status === "waiting_acceptance" ||
        t.status === "confirm" ||
        t.status === "proposed" ||
        t.status === "failed" ||
        t.status === "blocked"
      )
    }
    return t.status === statusFilter
  })

  if (collapsed) {
    return (
      <div className="dc-sidebar-collapsed">
        <button
          className="dc-collapse-toggle-btn"
          onClick={() => setCollapsed(false)}
          title="展开任务索引侧栏"
        >
          <ChevronRight size={15} />
        </button>
        <span className="dc-vertical-title">
          任务索引 ({tasks.filter((t) => t.status === "completed").length}/{tasks.length})
        </span>
      </div>
    )
  }

  return (
    <aside className="dc-sidebar">
      {/* 侧栏顶头 */}
      <div className="dc-sidebar-header">
        <div className="dc-sidebar-title">
          <ListTodo size={14} color="var(--pri)" />
          <span>值守任务索引</span>
        </div>
        <button
          className="dc-collapse-toggle-btn"
          onClick={() => setCollapsed(true)}
          title="收起侧栏"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      {/* ── 需要你处理 (Needs You) 强调区 ── */}
      {needsYouTasks.length > 0 && (
        <div className="dc-needs-you-box">
          <div className="dc-needs-you-title">
            <span className="dc-pulse-beacon-amber" />
            <span>需要你处理 ({needsYouTasks.length})</span>
          </div>

          <div className="dc-needs-you-list">
            {needsYouTasks.map((t) => (
              <div
                key={t.id}
                className={`dc-needs-you-item ${t.id === activeTaskId ? "active" : ""}`}
                onClick={() => onSelectTask(t.id)}
              >
                <div className="dc-needs-you-item-title">
                  <span className="dc-badge-no-sm">#T-{t.taskNo}</span>
                  <span className="dc-needs-you-text">{t.title}</span>
                </div>
                <div className="dc-needs-you-action">
                  {t.status === "proposed"
                    ? "去确认提案 →"
                    : t.status === "waiting_acceptance"
                    ? t.humanRequest?.type === "acceptance"
                      ? "去验收 →"
                      : "去拍板 →"
                    : t.status === "confirm"
                    ? "去授权 →"
                    : "去仲裁 →"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 状态过滤器胶囊 ── */}
      <div className="dc-filter-bar">
        <div className="dc-filter-label">
          <Filter size={11} />
          <span>状态筛选</span>
        </div>
        <div className="dc-filter-chips">
          <button
            className={`dc-chip ${statusFilter === "all" ? "active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            全部 ({tasks.length})
          </button>
          <button
            className={`dc-chip ${statusFilter === "needs_you" ? "active" : ""}`}
            onClick={() => setStatusFilter("needs_you")}
          >
            需处理 ({needsYouTasks.length})
          </button>
          <button
            className={`dc-chip ${statusFilter === "in_progress" ? "active" : ""}`}
            onClick={() => setStatusFilter("in_progress")}
          >
            进行中
          </button>
          <button
            className={`dc-chip ${statusFilter === "completed" ? "active" : ""}`}
            onClick={() => setStatusFilter("completed")}
          >
            已完成
          </button>
        </div>
      </div>

      {/* ── 任务列表滚动区 ── */}
      <div className="dc-task-scroll-list">
        {filteredTasks.map((task) => {
          const isActive = task.id === activeTaskId
          return (
            <div
              key={task.id}
              className={`dc-task-row ${isActive ? "active" : ""}`}
              onClick={() => onSelectTask(task.id)}
              title="点击在画布上聚焦展开此任务"
            >
              <div className="dc-task-row-top">
                <span className="dc-badge-no-sm">#T-{task.taskNo}</span>
                <span className="dc-task-row-stage">{task.stage}</span>
                <span className={`dc-task-row-status ${task.status}`}>
                  {task.status === "completed" ? (
                    <CheckCircle2 size={12} color="var(--green)" />
                  ) : task.status === "in_progress" ? (
                    <Clock size={12} color="var(--pri)" />
                  ) : task.status === "proposed" ? (
                    <AlertCircle size={12} color="var(--purple)" />
                  ) : task.status === "waiting_acceptance" || task.status === "confirm" ? (
                    <AlertCircle size={12} color="var(--amber)" />
                  ) : task.status === "failed" || task.status === "blocked" ? (
                    <AlertCircle size={12} color="var(--red)" />
                  ) : (
                    <AlertCircle size={12} color="var(--text-muted)" />
                  )}
                </span>
              </div>
              <div className="dc-task-row-title">{task.title}</div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
