import {describe, expect, it} from "vitest"
import {render, screen} from "@testing-library/react"

import {MarkdownText} from "./MarkdownText"

/**
 * 轻量 markdown 渲染契约：GFM autolink / 强调 / 表格 / URL 白名单。
 * 提案正文与任务描述的统一渲染位（2026-09-23 收敛）。
 */

describe("MarkdownText · autolink", () => {
  it("裸 URL 渲染为可点锚点（remark-gfm autolink literal）", () => {
    render(
      <MarkdownText
        content="原帖：https://www.reddit.com/r/shopify/comments/1wndf41/do_you_think/ 请评估"
      />,
    )
    const a = screen.getByRole("link", { name: /reddit\.com/ })
    expect(a).toHaveAttribute("href", expect.stringContaining("reddit.com"))
    expect(a).toHaveAttribute("target", "_blank")
    expect(a).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("javascript: 伪协议被 URL 白名单拦截（降级为不可点文本）", () => {
    render(<MarkdownText content="[点我](javascript:alert(1))" />)
    // href 被剥掉 → 不再是可点链接角色，文本保留
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.getByText(/点我/)).toBeInTheDocument()
  })
})

describe("MarkdownText · 块级结构", () => {
  it("加粗 / 列表 / 表格渲染", () => {
    render(
      <MarkdownText
        content={
          "**重点**：核对\n\n- 第一项\n- 第二项\n\n| a | b |\n|---|---|\n| 1 | 2 |"
        }
      />,
    )
    expect(screen.getByText("重点").closest("strong")).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByRole("table")).toBeInTheDocument()
  })

  it("段落紧凑（首段无上边距类）", () => {
    const { container } = render(<MarkdownText content={"第一段\n\n第二段"} />)
    const first = container.querySelector("p")
    expect(first?.className).toContain("first:mt-0")
  })
})
