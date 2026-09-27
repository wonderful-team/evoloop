import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ToolCallItem } from "./ToolCallItem"
import type { ToolCallTraceData } from "./types"

/**
 * 工具调用头部展示契约（2026-09-25 参数可见性收敛）：
 * - 内联键与折叠键分工：同时命中两名单的键（command/pattern）短值内联、
 *   长值折叠；此前 command 只在折叠名单 → 短命令参数彻底不可见；
 * - tasks 的 action 入内联名单（值守审计最常看的"动了哪个动作"）；
 * - 后端 tool_meta.display_name（聊天/值守同一 i18n 体系）优先于白名单拼装。
 */

function timeline(data: ToolCallTraceData) {
  return render(<ToolCallItem data={data} variant="timeline" />)
}

describe("ToolCallItem · 参数可见性", () => {
  it("tasks 的 action 内联显示（此前永不可见）", () => {
    timeline({
      toolName: "tasks",
      input: { action: "take", task_id: "t-9", status: "pending" },
    })
    expect(screen.getByText(/tasks 'take'/)).toBeInTheDocument()
  })

  it("bash 短命令内联显示（command 补入内联名单）", () => {
    timeline({
      toolName: "bash",
      input: { command: "ls -la" },
    })
    expect(screen.getByText(/bash 'ls -la'/)).toBeInTheDocument()
  })

  it("bash 长命令（>48 字符）折叠进 detail，header 不带内联", () => {
    const long =
      "python scripts/export_intent_classifier_onnx.py --input models/intent_classifier --out models/intent_classifier.onnx"
    timeline({ toolName: "bash", input: { command: long } })
    expect(screen.queryByText(/bash 'ls/)).not.toBeInTheDocument()
    // 折叠区含完整命令（点击展开后可见）
    fireEvent.click(screen.getByText(/bash\(\)/))
    expect(screen.getByText(/intent_classifier\.onnx/)).toBeInTheDocument()
  })

  it("read 的 path 任何长度都内联（path 只在内联名单）", () => {
    const p = "/Users/huangjinhuan/Projects/data/hn_v2ex/merged_summary.json"
    timeline({ toolName: "read", input: { path: p } })
    expect(
      screen.getByText(new RegExp(p.replace(/[/.]/g, "\\$&"))),
    ).toBeInTheDocument()
  })

  it("displayName（后端 i18n）优先于白名单拼装", () => {
    timeline({
      toolName: "tasks",
      displayName: "任务: take 每日巡检",
      input: { action: "take", task_id: "t-1" },
    })
    expect(screen.getByText("任务: take 每日巡检")).toBeInTheDocument()
    expect(screen.queryByText(/tasks 'take'/)).not.toBeInTheDocument()
  })
})
