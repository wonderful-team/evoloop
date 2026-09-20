/* ==========================================================================
   EvoLoop 自主值守工作台 · 标准人在回路治理卡片 (DutyHumanRequestCard.tsx)
   全面对齐 evoloop/frontend/packages/desktop/src/components/Chat/HumanRequestCard.tsx：
   - 7 种标准交互形态：approval (高危4键) / choice / multi_choice / proposal / acceptance / confirmation / text
   - 结构化风险上下文渲染 (Context Callout: 风险等级/操作/目标资源/预算)
   - 4 级治理标准动作：取消 / 拒绝 / 仅本次 / 总是允许 (grant_mode: once | always)
   - 事后审计留痕封存：操作后原地转为已完成/已拒绝不可篡改存根
   ========================================================================== */

import { useState } from "react"
import {
  Ban,
  CheckCircle2,
  XCircle,
  Play,
  BadgeCheck,
  MessageSquareX,
  CheckSquare,
} from "lucide-react"
import type { HumanRequestSpec } from "../types"

interface DutyHumanRequestCardProps {
  request: HumanRequestSpec
  onApprove?: (grantMode?: "once" | "always") => void
  onReject?: (feedback?: string) => void
  onCancel?: () => void
  onSubmitText?: (value: string) => void
  onSubmitChoice?: (choice: string) => void
  onSubmitMultiChoice?: (choices: string[]) => void
}

export const DutyHumanRequestCard = ({
  request,
  onApprove,
  onReject,
  onCancel,
  onSubmitText,
  onSubmitChoice,
  onSubmitMultiChoice,
}: DutyHumanRequestCardProps) => {
  const [inputVal, setInputVal] = useState("")
  const [customValue, setCustomValue] = useState("")
  const [selectedChoices, setSelectedChoices] = useState<string[]>([])
  const [rejectOpen, setRejectOpen] = useState(false)
  const [feedback, setFeedback] = useState("")
  const [busy, setBusy] = useState(false)

  const isResolved =
    request.status === "completed" ||
    request.status === "cancelled" ||
    request.status === "rejected"

  // 格式化解析上下文详情行 (风险等级/操作/资源/预算…)
  const contextLines = (request.context || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)

  const handleApproveAction = async (grantMode: "once" | "always") => {
    setBusy(true)
    try {
      await onApprove?.(grantMode)
    } finally {
      setBusy(false)
    }
  }

  const handleRejectAction = async () => {
    setBusy(true)
    try {
      await onReject?.(feedback)
      setRejectOpen(false)
      setFeedback("")
    } finally {
      setBusy(false)
    }
  }

  const handleCancelAction = async () => {
    setBusy(true)
    try {
      await onCancel?.()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dc-hitl-card-wrapper">
      {/* ── 顶部 Prompt 引导区 ── */}
      <div className="dc-hitl-prompt-row">
        <span className="dc-hitl-indicator-pulse" />
        <span className="dc-hitl-prompt-text">{request.prompt}</span>
      </div>

      {/* ── 结构化安全上下文 Callout ── */}
      {contextLines.length > 0 && (
        <div className="dc-hitl-context-box">
          {contextLines.map((line, idx) => (
            <div key={idx} className="dc-hitl-context-line">
              {line}
            </div>
          ))}
        </div>
      )}

      {/* ── 核心交互操作区 ── */}
      {!isResolved ? (
        <div className="dc-hitl-action-area">
          {/* ────────────────────────────────────────────────────────
             形态 1：高危操作审批 (Approval) · 标准 4 级治理体系
             ──────────────────────────────────────────────────────── */}
          {request.type === "approval" && (
            <div className="dc-hitl-approval-row">
              <div className="dc-hitl-cancel-box">
                <button
                  type="button"
                  className="dc-btn dc-btn-ghost dc-hitl-btn-cancel"
                  disabled={busy}
                  onClick={handleCancelAction}
                  title="叫停并终止该任务的会话"
                >
                  <Ban size={13} />
                  <span>取消任务</span>
                </button>
              </div>

              <div className="dc-hitl-actions-right">
                <button
                  type="button"
                  className="dc-btn dc-btn-ghost dc-hitl-btn-reject"
                  disabled={busy}
                  onClick={() => onReject?.("操作员拒绝")}
                  title="明确拒绝本次操作，触发降级保护"
                >
                  <XCircle size={13} />
                  <span>拒绝</span>
                </button>

                <button
                  type="button"
                  className="dc-btn dc-btn-outline dc-hitl-btn-once"
                  disabled={busy}
                  onClick={() => handleApproveAction("once")}
                  title="仅批准本次调用放行"
                >
                  <CheckCircle2 size={13} />
                  <span>仅本次</span>
                </button>

                <button
                  type="button"
                  className="dc-btn dc-btn-primary dc-hitl-btn-always"
                  disabled={busy}
                  onClick={() => handleApproveAction("always")}
                  title="总是允许（加入白名单免审）"
                >
                  <CheckCircle2 size={13} />
                  <span>总是允许</span>
                </button>
              </div>
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 2：商业策略拍板单选 (Choice) · 带必选自定义输入
             ──────────────────────────────────────────────────────── */}
          {request.type === "choice" && request.options && (
            <div className="dc-hitl-choice-section">
              <div className="dc-hitl-radio-list">
                {request.options.map((opt, idx) => (
                  <label
                    key={idx}
                    className={`dc-hitl-radio-item ${inputVal === opt ? "selected" : ""}`}
                    onClick={() => setInputVal(opt)}
                  >
                    <input
                      type="radio"
                      name="hitl-choice"
                      checked={inputVal === opt}
                      onChange={() => setInputVal(opt)}
                    />
                    <span className="dc-hitl-radio-label">{opt}</span>
                  </label>
                ))}

                {/* 每次必带的自定义输入选项 */}
                <label
                  className={`dc-hitl-radio-item ${inputVal === "__custom__" ? "selected" : ""}`}
                  onClick={() => setInputVal("__custom__")}
                >
                  <input
                    type="radio"
                    name="hitl-choice"
                    checked={inputVal === "__custom__"}
                    onChange={() => setInputVal("__custom__")}
                  />
                  <span className="dc-hitl-radio-label">自定义输入补充指令…</span>
                </label>
              </div>

              {inputVal === "__custom__" && (
                <textarea
                  className="dc-hitl-custom-textarea"
                  placeholder="请输入您的自定义商业决策或策略微调要求…"
                  value={customValue}
                  onChange={(e) => setCustomValue(e.target.value)}
                  rows={3}
                />
              )}

              <div className="dc-hitl-submit-row">
                <button
                  type="button"
                  className="dc-btn dc-btn-primary"
                  disabled={
                    busy ||
                    !inputVal ||
                    (inputVal === "__custom__" && !customValue.trim())
                  }
                  onClick={() =>
                    onSubmitChoice?.(
                      inputVal === "__custom__" ? customValue.trim() : inputVal,
                    )
                  }
                >
                  <Play size={12} />
                  <span>提交决策方案</span>
                </button>
              </div>
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 3：多选组合策略 (Multi Choice)
             ──────────────────────────────────────────────────────── */}
          {request.type === "multi_choice" && request.options && (
            <div className="dc-hitl-choice-section">
              <div className="dc-hitl-radio-list">
                {request.options.map((opt, idx) => {
                  const checked = selectedChoices.includes(opt)
                  return (
                    <label
                      key={idx}
                      className={`dc-hitl-radio-item ${checked ? "selected" : ""}`}
                      onClick={() => {
                        setSelectedChoices((prev) =>
                          checked ? prev.filter((x) => x !== opt) : [...prev, opt],
                        )
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {}}
                      />
                      <span className="dc-hitl-radio-label">{opt}</span>
                    </label>
                  )
                })}
              </div>

              <div className="dc-hitl-submit-row">
                <button
                  type="button"
                  className="dc-btn dc-btn-primary"
                  disabled={busy || selectedChoices.length === 0}
                  onClick={() => onSubmitMultiChoice?.(selectedChoices)}
                >
                  <CheckSquare size={12} />
                  <span>确认组合配置 ({selectedChoices.length})</span>
                </button>
              </div>
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 4：Agent 主动提案确认 (Proposal)
             ──────────────────────────────────────────────────────── */}
          {request.type === "proposal" && (
            <div className="dc-hitl-proposal-section">
              {!rejectOpen ? (
                <div className="dc-hitl-actions-right" style={{ justifyContent: "flex-start" }}>
                  <button
                    type="button"
                    className="dc-btn dc-btn-primary"
                    disabled={busy}
                    onClick={() => onApprove?.("once")}
                    title="确认该提案并排入正式执行队列"
                  >
                    <BadgeCheck size={14} />
                    <span>确认，加入队列</span>
                  </button>

                  <button
                    type="button"
                    className="dc-btn dc-btn-ghost dc-hitl-btn-reject"
                    disabled={busy}
                    onClick={() => setRejectOpen(true)}
                    title="驳回提案并附带修改意见"
                  >
                    <MessageSquareX size={14} />
                    <span>驳回提案</span>
                  </button>
                </div>
              ) : (
                <div className="dc-hitl-reject-form">
                  <textarea
                    className="dc-hitl-custom-textarea"
                    placeholder="请输入驳回原因（必填，将反馈给 Agent 修正提案）…"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    rows={3}
                  />
                  <div className="dc-hitl-submit-row">
                    <button
                      type="button"
                      className="dc-btn dc-btn-danger"
                      disabled={busy || !feedback.trim()}
                      onClick={handleRejectAction}
                    >
                      确认驳回
                    </button>
                    <button
                      type="button"
                      className="dc-btn dc-btn-ghost"
                      onClick={() => {
                        setRejectOpen(false)
                        setFeedback("")
                      }}
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 5：交付成果验收与打回 (Acceptance)
             ──────────────────────────────────────────────────────── */}
          {request.type === "acceptance" && (
            <div className="dc-hitl-acceptance-section">
              {!rejectOpen ? (
                <div className="dc-hitl-actions-right" style={{ justifyContent: "flex-start" }}>
                  <button
                    type="button"
                    className="dc-btn dc-btn-primary"
                    disabled={busy}
                    onClick={() => onApprove?.("once")}
                    title="验收通过，成果安全归档入库"
                  >
                    <BadgeCheck size={14} />
                    <span>验收通过，成果归档</span>
                  </button>

                  <button
                    type="button"
                    className="dc-btn dc-btn-ghost dc-hitl-btn-reject"
                    disabled={busy}
                    onClick={() => setRejectOpen(true)}
                    title="打回修改重做并附带具体指导意见"
                  >
                    <MessageSquareX size={14} />
                    <span>打回重做</span>
                  </button>
                </div>
              ) : (
                <div className="dc-hitl-reject-form">
                  <textarea
                    className="dc-hitl-custom-textarea"
                    placeholder="请输入打回原因与修正指导（将注入 Agent 上下文重新推演）…"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    rows={3}
                  />
                  <div className="dc-hitl-submit-row">
                    <button
                      type="button"
                      className="dc-btn dc-btn-danger"
                      disabled={busy || !feedback.trim()}
                      onClick={handleRejectAction}
                    >
                      确认打回重做
                    </button>
                    <button
                      type="button"
                      className="dc-btn dc-btn-ghost"
                      onClick={() => {
                        setRejectOpen(false)
                        setFeedback("")
                      }}
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 6：补充文本输入 (Text)
             ──────────────────────────────────────────────────────── */}
          {request.type === "text" && (
            <div className="dc-hitl-text-section">
              <textarea
                className="dc-hitl-custom-textarea"
                placeholder="请输入补充信息或参数说明…"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                rows={3}
              />
              <div className="dc-hitl-submit-row">
                <button
                  type="button"
                  className="dc-btn dc-btn-primary"
                  disabled={busy || !inputVal.trim()}
                  onClick={() => onSubmitText?.(inputVal.trim())}
                >
                  <Play size={12} />
                  <span>提交输入</span>
                </button>
              </div>
            </div>
          )}

          {/* ────────────────────────────────────────────────────────
             形态 7：二值确认 (Confirmation)
             ──────────────────────────────────────────────────────── */}
          {request.type === "confirmation" && (
            <div className="dc-hitl-actions-right" style={{ justifyContent: "flex-start" }}>
              <button
                type="button"
                className="dc-btn dc-btn-primary"
                disabled={busy}
                onClick={() => onApprove?.("once")}
              >
                <CheckCircle2 size={13} />
                <span>确认 (Yes)</span>
              </button>
              <button
                type="button"
                className="dc-btn dc-btn-ghost"
                disabled={busy}
                onClick={() => onReject?.("用户选择否")}
              >
                <XCircle size={13} />
                <span>否 (No)</span>
              </button>
            </div>
          )}
        </div>
      ) : (
        /* ── 事后审计存根 (Post-Action Audit Stamp) ── */
        <div className="dc-hitl-audit-bar">
          {request.status === "completed" && (
            <div className="dc-hitl-audit-pill completed">
              <CheckCircle2 size={13} />
              <span>
                ✓ 人在回路：已批准放行
                {request.decision?.grantMode === "always"
                  ? " · 授权模式：总是允许（白名单）"
                  : " · 授权模式：仅本次"}
                {request.decision?.timestamp ? ` (${request.decision.timestamp})` : ""}
              </span>
            </div>
          )}

          {request.status === "rejected" && (
            <div className="dc-hitl-audit-pill rejected">
              <XCircle size={13} />
              <span>
                ✕ 人在回路：已明确拒绝
                {request.decision?.feedback ? `（原因：${request.decision.feedback}）` : ""}
              </span>
            </div>
          )}

          {request.status === "cancelled" && (
            <div className="dc-hitl-audit-pill cancelled">
              <Ban size={13} />
              <span>✕ 人在回路：操作员已叫停并终止任务会话</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
