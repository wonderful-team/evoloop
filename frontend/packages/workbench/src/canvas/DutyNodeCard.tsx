/* ==========================================================================
   EvoLoop 自主值守工作台 · 画布任务节点空间容器 (DutyNodeCard.tsx)
   设计理念：静若脑图，动若页面 (Node Card IS the Page)
   - 单击选中：高亮聚焦外框，联动底部居中悬浮对话框，可直接按住拖拽卡片
   - 双击或点击按钮：原地中心对称膨胀为 1040px × 660px 现场全景工作页面
   - 流入数据直观展现：清晰呈现上游输入数据 Payload
   - 左右磁吸端口交互手柄：支持从右端口按住拖拽连线到下游节点
   ========================================================================== */

import { AlertTriangle, ArrowDownLeft, Ban, RotateCcw } from "lucide-react"
import type React from "react"
import { stripMarkdownTokens } from "../core/mdText"
import { statusMeta } from "../core/statusMeta"
import type { DutyTask } from "../core/types"
import { PlanProgressInline } from "../detail/PlanPanel"
import { DutyNodePageContent } from "./DutyNodePageContent"

export const EXPANDED_CARD_WIDTH = 1040
export const EXPANDED_CARD_HEIGHT = 660

interface DutyNodeCardProps {
  task: DutyTask
  allTasks?: DutyTask[]
  zoom?: number
  isFocused: boolean
  isSelected?: boolean
  stepIndex?: number
  isDragging?: boolean
  isDimmed?: boolean
  isFullscreen?: boolean
  onToggleFullscreen?: () => void
  layoutDirection?: "horizontal" | "vertical"
  onPointerDown?: (e: React.PointerEvent) => void
  onSelect?: () => void
  onFocus: () => void
  onUnfocus: () => void
  onPortPointerDown?: (
    e: React.PointerEvent,
    taskId: string,
    side: "left" | "right" | "top" | "bottom",
  ) => void
  onTaskFission?: (taskId: string) => void
  onApprove?: (taskId: string, grantMode?: "once" | "always") => void
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

function hueCss(hue: number) {
  return `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 45) % 360} 75% 35%))`
}

export const DutyNodeCard = ({
  task,
  allTasks = [],
  zoom: _zoom,
  isFocused,
  isSelected = false,
  stepIndex = 0,
  isDragging = false,
  isDimmed = false,
  isFullscreen = false,
  onToggleFullscreen,
  layoutDirection = "horizontal",
  onPointerDown,
  onSelect,
  onFocus,
  onUnfocus,
  onPortPointerDown,
  onTaskFission: _onTaskFission,
  onApprove,
  onReject,
  onArbitrate,
  onConfirmHitl,
  onCancelHitl,
  onSubmitTextHitl,
  onSubmitChoiceHitl,
  onSubmitMultiChoiceHitl,
}: DutyNodeCardProps) => {
  const isExpanded = isFocused

  const meta = statusMeta(task.status)
  const statusDotClass = meta.cardCls
  const statusGlyph = meta.glyph

  /* 在画布坐标系中，计算原地中心对称展开后的坐标与宽高 */
  const cardWidth = isExpanded ? EXPANDED_CARD_WIDTH : task.w
  const cardHeight = isExpanded ? EXPANDED_CARD_HEIGHT : task.h || 280
  const cardLeft = isExpanded
    ? task.x - (EXPANDED_CARD_WIDTH - task.w) / 2
    : task.x
  const cardTop = isExpanded
    ? task.y - (EXPANDED_CARD_HEIGHT - (task.h || 280)) / 2
    : task.y

  // 查找并汇聚所有直接上游依赖任务的数据产物 Payload
  const upstreamPayloads = (task.dependencies || [])
    .map((depId) => allTasks.find((t) => t.id === depId))
    .filter((u): u is DutyTask => Boolean(u))
    .map((u) => ({
      taskNo: u.taskNo,
      title: u.artifact?.title || u.title,
    }))

  return (
    <div
      className={`dc-card ${task.status} ${isExpanded ? "expanded focused" : ""} ${
        isSelected ? "selected" : ""
      } ${isDragging ? "dragging" : ""} ${isDimmed ? "dimmed" : ""}`}
      data-task-id={task.id}
      style={{
        left: cardLeft,
        top: cardTop,
        width: cardWidth,
        height: cardHeight,
      }}
      onPointerDown={(e) => {
        if (isExpanded) {
          e.stopPropagation()
        } else {
          onPointerDown?.(e)
        }
      }}
      onClick={(e) => {
        if (isExpanded) {
          e.stopPropagation()
        } else {
          e.stopPropagation()
          onSelect?.()
        }
      }}
      onDoubleClick={(e) => {
        if (isExpanded) {
          e.stopPropagation()
        } else {
          e.stopPropagation()
          onFocus()
        }
      }}
    >
      {/* ── 脑图磁吸连接端口 (Connection Ports)：支持横向 (左右) 与纵向 (上下) 自适应 ── */}
      {layoutDirection === "vertical" ? (
        <>
          <div
            className="dc-port dc-port-top"
            data-port-task-id={task.id}
            data-port-side="top"
            title="依赖输入端口 (接收上游数据)"
          />
          <div
            className="dc-port dc-port-bottom"
            data-port-task-id={task.id}
            data-port-side="bottom"
            title="产出输出端口 (按住拖拽连线至下游节点)"
            onPointerDown={(e) => {
              e.stopPropagation()
              onPortPointerDown?.(e, task.id, "bottom")
            }}
          />
        </>
      ) : (
        <>
          <div
            className="dc-port dc-port-left"
            data-port-task-id={task.id}
            data-port-side="left"
            title="依赖输入端口 (接收上游数据)"
          />
          <div
            className="dc-port dc-port-right"
            data-port-task-id={task.id}
            data-port-side="right"
            title="产出输出端口 (按住拖拽连线至下游节点)"
            onPointerDown={(e) => {
              e.stopPropagation()
              onPortPointerDown?.(e, task.id, "right")
            }}
          />
        </>
      )}

      {isExpanded ? (
        /* ──────────────────────────────────────────────────────────
           分支 A：展开态 (Card IS Page) · 现场双栏全景工作页面
           若当前为全屏状态，画布底层仅保留占位符，由全屏浮层专属挂载
           ────────────────────────────────────────────────────────── */
        isFullscreen ? (
          <div className="flex items-center justify-center h-full text-xs text-muted-foreground/60 select-none bg-background/50 backdrop-blur-xs rounded-xl border border-dashed border-border/40">
            <span>已在全屏工作台视图呈现</span>
          </div>
        ) : (
          <DutyNodePageContent
            task={task}
            allTasks={allTasks}
            stepIndex={stepIndex}
            onClose={onUnfocus}
            isFullscreen={false}
            onToggleFullscreen={onToggleFullscreen}
            onApprove={onApprove}
            onReject={onReject}
            onArbitrate={onArbitrate}
            onConfirmHitl={onConfirmHitl}
            onCancelHitl={onCancelHitl}
            onSubmitTextHitl={onSubmitTextHitl}
            onSubmitChoiceHitl={onSubmitChoiceHitl}
            onSubmitMultiChoiceHitl={onSubmitMultiChoiceHitl}
          />
        )
      ) : (
        /* ──────────────────────────────────────────────────────────
           分支 B：常态卡片 (Unfocused) · 脑图标准紧凑卡片 (420px × 280px)
           ────────────────────────────────────────────────────────── */
        <>
          {/* ── 卡片顶栏元数据 ── */}
          <div className="dc-card-top">
            <span
              className="dc-badge-no dc-node-drag-handle"
              title="卡片编号 · 单击选中可拖拽或对话，双击放大进入页面"
            >
              #T-{task.taskNo}
            </span>

            <span className={`dc-badge dc-badge-${task.source}`}>
              {task.source === "chat"
                ? "💬 对话"
                : task.source === "agent_proposal"
                  ? "🤖 提案"
                  : task.source === "cron"
                    ? "⏰ 巡检"
                    : task.source === "event"
                      ? "🔗 事件"
                      : task.source === "chain"
                        ? "⛓ 派生"
                        : "👤 手动"}
            </span>

            <span
              className={`dc-badge-risk risk-${(task.riskLevel || "T3").toLowerCase()}`}
            >
              {task.riskLevel}
            </span>

            {task.status === "proposed" && (
              <span className="dc-badge-proposal">待确认提案</span>
            )}
            {task.workflowId && (
              <span
                className="dc-badge-proposal"
                title={`周期流水线归属：${task.workflowName || task.workflowId}`}
              >
                周期流水线{task.workflowName ? `·${task.workflowName}` : ""}
                {task.workflowRound ? `·第${task.workflowRound}轮` : ""}
              </span>
            )}
            {task.signoff && <span className="dc-badge-signoff">需拍板</span>}
            {task.hitl && (
              <span className="dc-badge-hitl">
                {task.humanRequest?.type === "choice"
                  ? "待决策选择"
                  : "安全授权"}
              </span>
            )}
            {task.humanRequest && task.humanRequest.type === "acceptance" && (
              <span className="dc-badge-acceptance">待验收</span>
            )}

            <span className={`dc-card-status-glyph ${statusDotClass}`}>
              {task.status === "in_progress" && <i className="dc-pulse-dot" />}
              {statusGlyph}
            </span>
          </div>

          {/* ── 任务标题 ── */}
          <div className="dc-card-title">{task.title}</div>

          {/* ── 计划推进进度条 (核心要素：计划；仅活任务拉取，防 N+1) ── */}
          {task.rawQueueTask && (
            <div className="px-3 py-0.5">
              <PlanProgressInline
                task={task.rawQueueTask as any}
                enabled={["in_progress", "confirm", "suspended"].includes(
                  task.status,
                )}
              />
            </div>
          )}

          {/* ── 流入数据（Inputs Payload）：仅在有真实上游依赖时精美展示，杜绝冗余空占位 ── */}
          {upstreamPayloads.length > 0 && (
            <div
              className="dc-card-inflow"
              title={`上游流入数据：${upstreamPayloads
                .map((p) => `#T-${p.taskNo}「${p.title}」`)
                .join("，")}`}
            >
              <span className="dc-inflow-label">
                <ArrowDownLeft size={11} /> 流入数据:
              </span>
              <span className="dc-inflow-val">
                {upstreamPayloads
                  .map((p) => `#T-${p.taskNo} ${p.title}`)
                  .join(" · ")}
              </span>
            </div>
          )}

          {/* ── 常态卡片预览摘要 ── */}
          <div className="dc-card-unfocused-content">
            <div className="dc-card-preview">
              {task.artifact?.matrixData && (
                <table className="dc-preview-matrix">
                  <tbody>
                    {task.artifact.matrixData.slice(0, 2).map((row, idx) => (
                      <tr key={idx}>
                        <td>{row.tier}</td>
                        <td style={{ color: "var(--pri)", fontWeight: 700 }}>
                          {row.price}
                        </td>
                        <td style={{ color: "var(--green)" }}>{row.margin}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {task.artifact?.images && (
                <div className="dc-preview-gallery">
                  {task.artifact.images.map((img) => (
                    <div
                      key={img.id}
                      className="dc-preview-gallery-item"
                      style={{ background: hueCss(img.hue) }}
                    >
                      {img.label.slice(0, 4)}
                    </div>
                  ))}
                </div>
              )}

              {task.humanRequest && (
                <div className="dc-preview-choice">
                  <div className="text-[11px] font-semibold text-amber-500 mb-1 flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
                    <span className="truncate">{task.humanRequest.prompt}</span>
                  </div>
                  {task.humanRequest.options?.slice(0, 3).map((opt, idx) => (
                    <div key={idx} className="dc-preview-choice-row">
                      <span className="dc-preview-radio" />
                      <span className="dc-preview-choice-text">{opt}</span>
                    </div>
                  ))}
                </div>
              )}

              {(task.status === "failed" ||
                task.status === "blocked" ||
                Boolean(task.arbitration)) && (
                <div
                  className="dc-card-arbitrate-box"
                  onClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <div className="text-[11px] font-semibold text-rose-500 mb-1 flex items-center justify-between">
                    <span className="flex items-center gap-1">
                      <AlertTriangle size={12} className="text-rose-500 shrink-0" />
                      <span>
                        {task.status === "blocked"
                          ? "断链阻断 · 待仲裁"
                          : "执行阻断 · 人工仲裁"}
                      </span>
                    </span>
                    <span className="text-[10px] text-muted-foreground/80 font-normal">
                      双击进内页
                    </span>
                  </div>
                  <div className="dc-arbitrate-btns">
                    <button
                      type="button"
                      className="dc-btn dc-btn-xs dc-btn-primary flex items-center gap-1"
                      onClick={() => onArbitrate?.("retry_upstream", task.id)}
                      title="重跑前序依赖节点"
                    >
                      <RotateCcw size={10} />
                      <span>重跑上游</span>
                    </button>
                    <button
                      type="button"
                      className="dc-btn dc-btn-xs dc-btn-outline-danger flex items-center gap-1"
                      onClick={() => onArbitrate?.("cancel_downstream", task.id)}
                      title="截断后续依赖任务"
                    >
                      <Ban size={10} />
                      <span>截断下游</span>
                    </button>
                  </div>
                </div>
              )}

              {!task.humanRequest &&
                !task.artifact?.matrixData &&
                !task.artifact?.images &&
                task.status !== "failed" &&
                task.status !== "blocked" &&
                !task.arbitration && (
                  <div className="dc-preview-text">
                    {stripMarkdownTokens(
                      task.artifact?.summary || task.description,
                    ) || "任务已由调度引擎接入脑图拓扑"}
                  </div>
                )}
            </div>
          </div>

          {/* ── 卡片底栏 ── */}
          <div className="dc-card-footer">
            <span className="dc-footer-stage">{task.stage}</span>
            <span className="dc-footer-status">
              {statusMeta(task.status).glyph} {statusMeta(task.status).label}
            </span>
          </div>
        </>
      )}
    </div>
  )
}
