/* ==========================================================================
   EvoLoop 自主值守工作台 · 顶栏主控制台 (DutyTopBar.tsx)
   精简版：
   - 去除重复品牌标识与中间指令输入框
   - 左侧：Agent 核心长程值守 Pulse 呼吸信标与实时 Token / 调用量 / 进度 KPI
   - 右侧：重置与【启动自主值守 / 暂停值守】总控按钮
   ========================================================================== */

import {
  Play,
  Square,
  RotateCcw,
} from "lucide-react"
import type { DashboardKPIs } from "../core/types"

interface DutyTopBarProps {
  isRunning: boolean
  kpis: DashboardKPIs
  statusText: string
  promptText?: string
  onChangePrompt?: (text: string) => void
  onSendPrompt?: () => void
  onToggleRun: () => void
  onReset: () => void
}

export const DutyTopBar = ({
  isRunning,
  kpis,
  statusText,
  onToggleRun,
  onReset,
}: DutyTopBarProps) => {
  return (
    <header className="dc-topbar">
      {/* ── 左侧：值守状态信标与实时指标监控 ── */}
      <div className="dc-topbar-center" style={{ marginLeft: 0 }}>
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

      {/* ── 右侧：控制按钮集 ── */}
      <div className="dc-topbar-actions">
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
