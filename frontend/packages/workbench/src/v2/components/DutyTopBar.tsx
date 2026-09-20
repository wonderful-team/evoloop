/* ==========================================================================
   EvoLoop 自主值守工作台 · 顶栏主控制台 (DutyTopBar.tsx)
   对齐 EvoLoop Duty 控制台：
   - 品牌标识与 Canvas Mode 徽标
   - Agent 核心长程值守启动/暂停控制与 Pulse 呼吸信标
   - 实时 Token 与调用量 KPI 监控
   - 全局 Agent 动态任务派发指令栏 (Prompt Command Bar)
   - 模拟断链测试、重置与手机端协同模式切换
   ========================================================================== */

import {
  Play,
  Square,
  RotateCcw,
  Zap,
  Send,
  Sparkles,
  Layers,
} from "lucide-react"
import type { DashboardKPIs } from "../types"

interface DutyTopBarProps {
  isRunning: boolean
  kpis: DashboardKPIs
  statusText: string
  promptText: string
  onChangePrompt: (text: string) => void
  onSendPrompt: () => void
  onToggleRun: () => void
  onMockBreak: () => void
  onReset: () => void
}

export const DutyTopBar = ({
  isRunning,
  kpis,
  statusText,
  promptText,
  onChangePrompt,
  onSendPrompt,
  onToggleRun,
  onMockBreak,
  onReset,
}: DutyTopBarProps) => {
  return (
    <header className="dc-topbar">
      {/* ── 品牌与模式标识 ── */}
      <div className="dc-brand-group">
        <div className="dc-brand-icon">
          <Layers size={18} color="#ffffff" />
        </div>
        <div className="dc-brand-info">
          <div className="dc-brand-title">
            <span>EvoLoop 自主值守工作台</span>
            <span className="dc-canvas-mode-tag">Canvas Mode</span>
          </div>
          <div className="dc-brand-sub">通用 Agent 长程任务空间调度系统</div>
        </div>
      </div>

      {/* ── 中央：值守状态信标与实时 Token 监控 ── */}
      <div className="dc-topbar-center">
        <div
          className={`dc-pulse-beacon ${
            isRunning ? "running" : kpis.taskCounts.needsYou > 0 ? "waiting" : ""
          }`}
        >
          <i />
          <span>{statusText}</span>
        </div>

        <div className="dc-kpi-strip">
          <span className="dc-kpi-item">
            Token: <b style={{ color: "var(--text-main)" }}>{(kpis.tokenToday.input + kpis.tokenToday.output) / 1000}k</b>
          </span>
          <span className="dc-kpi-divider">/</span>
          <span className="dc-kpi-item">
            调用: <b style={{ color: "var(--text-main)" }}>{kpis.tokenToday.calls}</b>
          </span>
          <span className="dc-kpi-divider">/</span>
          <span className="dc-kpi-item">
            进度:{" "}
            <b style={{ color: "var(--pri)" }}>
              {kpis.taskCounts.completed}/{kpis.taskCounts.total}
            </b>
          </span>
        </div>
      </div>

      {/* ── 中右：全局 Prompt 指令栏 ── */}
      <div className="dc-prompt-bar">
        <Sparkles size={14} color="var(--pri)" />
        <input
          type="text"
          value={promptText}
          onChange={(e) => onChangePrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSendPrompt()
          }}
          placeholder="向 Agent 下达新任务或干预指令（如：为选品增加轻量化方案）…"
          className="dc-prompt-input"
        />
        <button className="dc-prompt-send-btn" onClick={onSendPrompt} title="向调度拓扑发送新指令">
          <Send size={11} />
          <span>发送</span>
        </button>
      </div>

      {/* ── 右侧：控制按钮集 ── */}
      <div className="dc-topbar-actions">
        {/* 模拟断链 */}
        <button
          className="dc-btn dc-btn-ghost"
          onClick={onMockBreak}
          title="模拟上游异常导致下游锁定，测试人工仲裁三键恢复"
        >
          <Zap size={13} color="var(--amber)" />
          <span>模拟断链</span>
        </button>


        {/* 重置 */}
        <button className="dc-btn dc-btn-ghost" onClick={onReset} title="重置当前值守任务队列">
          <RotateCcw size={13} />
          <span>重置</span>
        </button>

        {/* 核心值守启停按钮 */}
        <button
          className={`dc-btn ${isRunning ? "dc-btn-danger" : "dc-btn-primary"}`}
          onClick={onToggleRun}
          title={isRunning ? "暂停当前 Agent 自主巡航" : "启动 Agent 自主巡航推进链路"}
        >
          {isRunning ? (
            <>
              <Square size={13} />
              <span>暂停值守</span>
            </>
          ) : (
            <>
              <Play size={13} />
              <span>启动自主值守</span>
            </>
          )}
        </button>
      </div>
    </header>
  )
}
