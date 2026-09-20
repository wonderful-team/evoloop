/* ==========================================================================
   EvoLoop 自主值守工作台 · 节点卡片即页面内页组件 (DutyNodePageContent.tsx)
   嵌入在画布任务卡片节点内部，实现「节点原地放大为页面」的现场级工作体验：
   - 顶部导航：收起为卡片 (Esc)、#T-n 编号、标题、血统徽标、状态胶囊
   - 四问关系区：一屏回答因谁而生 / 输入是谁 / 产出喂谁 / 结果谁背书
   - 左栏：Agent 时序思考、进度点亮与 MCP 工具链调用
   - 右栏：异构产物查看器 (单选、矩阵、素材、漏斗、文案)
   - 内嵌治理控制台：商业拍板 (D2/D4)、资金安全 HITL (D5)、仲裁三键 (D3/F4)
   ========================================================================== */

import { useState, useEffect } from "react"
import {
  X,
  Wrench,
  CheckCircle2,
  ShieldAlert,
  Layers,
  RefreshCw,
  XCircle,
  PlayCircle,
  Copy,
  Check,
} from "lucide-react"
import type { DutyTask } from "../types"
import { DutyHumanRequestCard } from "./DutyHumanRequestCard"

interface DutyNodePageContentProps {
  task: DutyTask
  stepIndex: number
  onClose: () => void
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

function hueCss(hue: number) {
  return `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 45) % 360} 75% 35%))`
}

export const DutyNodePageContent = ({
  task,
  stepIndex,
  onClose,
  onPickOption,
  onApprove,
  onReject,
  onArbitrate,
  onConfirmHitl,
  onCancelHitl,
  onSubmitTextHitl,
  onSubmitChoiceHitl,
  onSubmitMultiChoiceHitl,
}: DutyNodePageContentProps) => {
  const [rejectFeedback, setRejectFeedback] = useState("")
  const [showRejectInput, setShowRejectInput] = useState(false)
  const [copied, setCopied] = useState(false)

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

  function handleCopy(text: string) {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const steps = task.steps || []
  const currentStepCount = Math.min(stepIndex, steps.length)

  return (
    <div
      className="dc-page-inner"
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* ── 页面顶部条：元数据、状态、关闭按钮 ── */}
      <header className="dc-page-header">
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

          {task.signoff && task.signoff.rejectCount > 0 && (
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
        {/* ====================================================================
           ★ 四问全景关系区 (Four Questions Architecture - 严格一屏回答)
           ==================================================================== */}
        <div className="dc-four-q-panel">
          <div className="dc-four-q-head">
            <Layers size={13} />
            <span>自主值守关系全景 · 一屏解答四问</span>
          </div>
          <div className="dc-four-q-grid">
            {/* 1. 血统 */}
            <div className="dc-four-q-col">
              <div className="dc-four-q-label">💬 血统（因谁而生）</div>
              <div className="dc-four-q-desc">{task.provenance.sourceRef}</div>
            </div>

            {/* 2. 输入 */}
            <div className="dc-four-q-col">
              <div className="dc-four-q-label">⛓ 上游（输入是谁）</div>
              <div className="dc-four-q-desc">{task.provenance.upstreamSummary}</div>
            </div>

            {/* 3. 下游 */}
            <div className="dc-four-q-col">
              <div className="dc-four-q-label">🚀 下游（产出喂谁）</div>
              <div className="dc-four-q-desc">
                {task.provenance.downstreamTargets.join(" · ") || "终局闭环 · 反哺全局资产"}
              </div>
            </div>

            {/* 4. 核验 */}
            <div className="dc-four-q-col">
              <div className="dc-four-q-label">🛡 核验（结果谁背书）</div>
              <div className="dc-four-q-desc">{task.provenance.endorsement}</div>
            </div>
          </div>
        </div>

        {/* ── 左右双栏：左侧 Agent 执行时序与思考，右侧异构产物与治理控制台 ── */}
        <div className="dc-page-columns">
          {/* 左栏：执行时间线与 Agent 思考 */}
          <div className="dc-timeline-panel">
            <div className="dc-panel-head">
              <Wrench size={13} />
              <span>
                执行步骤与工具调用 ({currentStepCount}/{steps.length})
              </span>
            </div>

            <div className="dc-timeline-list">
              {steps.map((st, i) => {
                const isDone = i < stepIndex
                const isCurrent = i === stepIndex
                return (
                  <div
                    key={i}
                    className={`dc-timeline-item ${
                      isDone ? "done" : isCurrent ? "running" : "pending"
                    }`}
                  >
                    <div className="dc-step-dot">
                      {isDone ? "✓" : isCurrent ? "⟳" : i + 1}
                    </div>
                    <div className="dc-step-content">
                      <div className="dc-step-title">{st.label}</div>
                      {st.thought && (
                        <div className="dc-step-thought">
                          <span className="dc-thought-label">💭 思考：</span>
                          {st.thought}
                        </div>
                      )}
                      {st.detail && <div className="dc-step-detail">{st.detail}</div>}
                      {st.tool && (
                        <div className="dc-step-tool">
                          <Wrench size={10} />
                          <span>MCP: {st.tool}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 右栏：交付产物查看器与内嵌决策控制台 */}
          <div className="dc-artifact-panel">
            <div className="dc-panel-head">
              <CheckCircle2 size={13} />
              <span>
                {task.artifact?.title || "交付产物全景详情 (Artifact Inspector)"}
              </span>

              {task.artifact?.body && (
                <button
                  className="dc-copy-btn"
                  onClick={() => handleCopy(task.artifact?.body || "")}
                  title="复制产物文本"
                >
                  {copied ? <Check size={11} color="var(--green)" /> : <Copy size={11} />}
                  <span>{copied ? "已复制" : "复制正文"}</span>
                </button>
              )}
            </div>

            <div className="dc-artifact-view">
              {/* 1. 方案选择单选卡 (闭环 D2: 选品/策略) */}
              {task.signoff && (
                <div style={{ marginBottom: 16 }}>
                  <div className="dc-signoff-title">{task.signoff.prompt}</div>
                  <div className="dc-choice-list">
                    {task.signoff.options.map((opt, idx) => (
                      <div
                        key={idx}
                        className={`dc-choice-card ${opt.picked ? "picked" : ""}`}
                        onClick={() => onPickOption?.(task.id, idx)}
                      >
                        <span className="dc-radio-circle">{opt.picked && <i />}</span>
                        <div style={{ flex: 1 }}>
                          <div className="dc-choice-label">{opt.label}</div>
                          {opt.note && <div className="dc-choice-note">{opt.note}</div>}
                          {opt.risk && (
                            <div className="dc-choice-risk">⚠️ 风险点：{opt.risk}</div>
                          )}
                        </div>
                        {opt.margin && (
                          <div className="dc-choice-margin">毛利 {opt.margin}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 2. 定价与参数矩阵表 */}
              {task.artifact?.matrixData && (
                <div style={{ marginBottom: 16 }}>
                  <table className="dc-matrix-table">
                    <thead>
                      <tr>
                        <th>梯度项 / SKU</th>
                        <th>物料/采购成本</th>
                        <th>建议销售定价</th>
                        <th>预估毛利率</th>
                        <th>策略定位说明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {task.artifact.matrixData.map((row, idx) => (
                        <tr key={idx}>
                          <td style={{ fontWeight: 600 }}>{row.tier}</td>
                          <td style={{ color: "var(--text-sub)" }}>{row.cost}</td>
                          <td style={{ color: "var(--pri)", fontWeight: 700 }}>
                            {row.price}
                          </td>
                          <td style={{ color: "var(--green)", fontWeight: 700 }}>
                            {row.margin}
                          </td>
                          <td style={{ color: "var(--text-sub)" }}>{row.note}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* 3. 多场景素材图库画廊 */}
              {task.artifact?.images && (
                <div style={{ marginBottom: 16 }}>
                  <div className="dc-gallery-grid">
                    {task.artifact.images.map((img) => (
                      <div
                        key={img.id}
                        className="dc-gallery-card"
                        style={{ background: hueCss(img.hue) }}
                      >
                        <span className="dc-gallery-label">{img.label}</span>
                        <span className="dc-gallery-sub">
                          分辨率 1080×1080 · 质检核验通过
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 4. 转化漏斗分析图 */}
              {task.artifact?.funnel && (
                <div style={{ marginBottom: 16 }}>
                  <div className="dc-funnel-list">
                    {task.artifact.funnel.map((item, idx) => (
                      <div key={idx} className="dc-funnel-item">
                        <span className="dc-funnel-name">{item.label}</span>
                        <span className="dc-funnel-track">
                          <i style={{ width: `${item.pct}%` }} />
                        </span>
                        <span className="dc-funnel-val">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 5. 核心报告与文案 Markdown 呈现 */}
              {task.artifact?.body && (
                <div className="dc-markdown-body">{task.artifact.body}</div>
              )}
            </div>

            {/* ================================================================
               ★ 人在回路 (HITL) 治理控制台 (全面对齐 evoloop/frontend 聊天界面 7 种交互形态)
               ================================================================ */}
            {task.humanRequest ? (
              <DutyHumanRequestCard
                request={task.humanRequest}
                onApprove={(grantMode) => {
                  if (onConfirmHitl) {
                    onConfirmHitl(task.id, grantMode)
                  } else {
                    onApprove?.(task.id, grantMode)
                  }
                }}
                onReject={(feedback) => onReject?.(task.id, feedback)}
                onCancel={() => onCancelHitl?.(task.id)}
                onSubmitText={(val) => onSubmitTextHitl?.(task.id, val)}
                onSubmitChoice={(ch) => onSubmitChoiceHitl?.(task.id, ch)}
                onSubmitMultiChoice={(chs) => onSubmitMultiChoiceHitl?.(task.id, chs)}
              />
            ) : task.status === "confirm" && task.hitl ? (
              <DutyHumanRequestCard
                request={{
                  id: task.hitl.requestId || `hitl-${task.id}`,
                  type: "approval",
                  prompt: `资金安全审批：${task.hitl.description}`,
                  context: `风险等级：高风险资金出账 (T1)\n操作行为：${task.hitl.action}\n预算支出：${task.hitl.budget || "¥200.00"}\n目标接口：ads.launch_campaign`,
                  status: "waiting_human",
                }}
                onApprove={(grantMode) => onConfirmHitl?.(task.id, grantMode)}
                onReject={(feedback) => onReject?.(task.id, feedback)}
                onCancel={() => onCancelHitl?.(task.id)}
              />
            ) : null}

            {/* ================================================================
               ★ 内嵌商业拍板控制台 (闭环 D2, D4, F5) - 仅在无 humanRequest 时作为向下兼容降级
               ================================================================ */}
            {task.status === "waiting_acceptance" && task.signoff && !task.humanRequest && (
              <div className="dc-governance-box signoff">
                <div className="dc-gov-prompt">
                  ⏸ 商业决策拍板：请核验上方方案。批准后链路继续解锁下游任务；打回则带反馈重做。
                </div>

                {showRejectInput ? (
                  <div style={{ marginTop: 8 }}>
                    <textarea
                      rows={3}
                      className="dc-reject-textarea"
                      placeholder="请输入具体的打回修改意见（如：毛利测算偏激进，需压低拿货成本）..."
                      value={rejectFeedback}
                      onChange={(e) => setRejectFeedback(e.target.value)}
                    />
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        className="dc-btn dc-btn-danger"
                        onClick={() => {
                          onReject?.(task.id, rejectFeedback)
                          setShowRejectInput(false)
                        }}
                      >
                        确认打回修改
                      </button>
                      <button
                        className="dc-btn dc-btn-ghost"
                        onClick={() => setShowRejectInput(false)}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="dc-gov-actions">
                    <button
                      className="dc-btn dc-btn-primary"
                      onClick={() => onApprove?.(task.id)}
                    >
                      ✓ 批准所选方案并推进下游
                    </button>
                    <button
                      className="dc-btn dc-btn-outline-danger"
                      onClick={() => setShowRejectInput(true)}
                    >
                      打回重做
                    </button>
                    <span className="dc-reject-hint">
                      已累计打回 {task.signoff.rejectCount} 次
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* ================================================================
               ★ 人工仲裁三键控制台 (闭环 D3, F4)
               ================================================================ */}
            {(task.status === "blocked" || task.status === "failed") && (
              <div className="dc-governance-box arbitration">
                <div className="dc-gov-prompt" style={{ color: "var(--red)" }}>
                  <ShieldAlert size={15} />
                  <span>链路异常断开 · 触发人工仲裁裁决</span>
                </div>
                <div className="dc-gov-desc">
                  由于前置依赖产生异常或监察评审未通过，下游任务自动转为锁定阻塞状态。请选择恢复策略：
                </div>
                <div className="dc-gov-actions" style={{ marginTop: 10 }}>
                  <button
                    className="dc-btn dc-btn-ghost"
                    onClick={() => onArbitrate?.("retry_upstream")}
                    title="重新调度上游前置任务执行"
                  >
                    <RefreshCw size={13} /> 重跑上游任务
                  </button>
                  <button
                    className="dc-btn dc-btn-ghost"
                    onClick={() => onArbitrate?.("cancel_downstream")}
                    title="放弃并截断受影响的下游分支"
                  >
                    <XCircle size={13} /> 取消下游任务
                  </button>
                  <button
                    className="dc-btn dc-btn-primary"
                    onClick={() => onArbitrate?.("reopen_modified")}
                    title="人工微调输入参数后恢复执行"
                  >
                    <PlayCircle size={13} /> 修改参数后重开
                  </button>
                </div>
              </div>
            )}

            {/* 已完成盖戳 */}
            {task.status === "completed" && (
              <div className="dc-completed-banner">
                <CheckCircle2 size={15} color="var(--green)" />
                <span>
                  Supervisor Agent 意图一致性对账核验通过 · 产物已安全入库并向拓扑下游注入
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
