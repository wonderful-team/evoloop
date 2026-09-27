import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { AgentExecutionTimeline } from "./AgentExecutionTimeline"
import type { TraceNodeItem } from "./types"

describe("AgentExecutionTimeline component", () => {
  it("renders empty text when items is empty", () => {
    render(<AgentExecutionTimeline items={[]} emptyText="空时间线" />)
    expect(screen.getByText("空时间线")).toBeInTheDocument()
  })

  it("renders multiple nodes with correct icons and labels", () => {
    const items: TraceNodeItem[] = [
      {
        id: "node-1",
        kind: "instruction",
        title: "启动任务",
        content: "第一步执行分析",
      },
      {
        id: "node-2",
        kind: "think",
        content: "思考中...",
      },
      {
        id: "node-3",
        kind: "artifact",
        title: "报告生成",
        content: "output.md",
      },
      {
        id: "node-4",
        kind: "error",
        content: "连接超时",
      },
      {
        id: "node-5",
        kind: "hitl",
        content: "等待审批确认",
      },
    ]

    render(<AgentExecutionTimeline items={items} />)

    expect(screen.getByText("启动任务")).toBeInTheDocument()
    expect(screen.getByText("思考")).toBeInTheDocument()
    expect(screen.getByText("报告生成")).toBeInTheDocument()
    expect(screen.getByText("异常")).toBeInTheDocument()
    expect(screen.getByText("等待人工")).toBeInTheDocument()
  })

  it("renders tool call node when kind is tool and toolData is present", () => {
    const items: TraceNodeItem[] = [
      {
        id: "tool-1",
        kind: "tool",
        toolData: {
          toolName: "web_search",
          status: "success",
          input: { query: "vitest testing" },
          output: "results found",
        },
      },
    ]

    render(<AgentExecutionTimeline items={items} />)
    expect(screen.getByText(/web_search\(\)/)).toBeInTheDocument()
  })

  it("toggles node expansion when clicked", () => {
    const longContent = "A".repeat(200)
    const items: TraceNodeItem[] = [
      {
        id: "long-node",
        kind: "think",
        content: longContent,
      },
    ]

    render(<AgentExecutionTimeline items={items} />)

    expect(screen.getByText(/展开全部/)).toBeInTheDocument()
    const clickable = screen.getByText("思考").closest("div.cursor-pointer")
    expect(clickable).toBeTruthy()

    fireEvent.click(clickable!)
    expect(screen.queryByText(/展开全部/)).not.toBeInTheDocument()
  })

  it("supports renderNodeExtra", () => {
    const items: TraceNodeItem[] = [
      {
        id: "extra-node",
        kind: "system",
        content: "系统初始化",
      },
    ]

    render(
      <AgentExecutionTimeline
        items={items}
        renderNodeExtra={(node) => <span data-testid="extra-tag">{node.id}</span>}
      />,
    )

    expect(screen.getByTestId("extra-tag")).toHaveTextContent("extra-node")
  })
})
