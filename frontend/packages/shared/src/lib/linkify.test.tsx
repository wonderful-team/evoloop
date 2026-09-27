import {describe, expect, it} from "vitest"
import {render, screen} from "@testing-library/react"

import {linkifyText} from "./linkify"

describe("linkifyText · URL 自动识别", () => {
  it("裸 URL 渲染为可点锚点（Agent 上报的来源链接）", () => {
    render(
      <div>
        {linkifyText(
          "原帖：https://www.reddit.com/r/shopify/comments/1wndf41/do_you_think_shopify_search_losing_sales_because/ 请评估",
        )}
      </div>,
    )
    const a = screen.getByRole("link", {
      name: /reddit\.com\/r\/shopify\/comments/,
    })
    expect(a).toHaveAttribute("href", expect.stringContaining("reddit.com"))
    expect(a).toHaveAttribute("target", "_blank")
    expect(a).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("URL 尾部中文标点不进入链接", () => {
    render(<div>{linkifyText("见 https://example.com/a_1。后续说明")}</div>)
    const a = screen.getByRole("link")
    expect(a.getAttribute("href")).toBe("https://example.com/a_1")
    expect(a.textContent).toBe("https://example.com/a_1")
  })

  it("多 URL 全部识别，纯文本段原样保留", () => {
    render(
      <div>{linkifyText("对比 https://a.com 与 https://b.com 的报价")}</div>,
    )
    expect(screen.getAllByRole("link")).toHaveLength(2)
    expect(screen.getByText(/对比/)).toBeInTheDocument()
    expect(screen.getByText(/的报价/)).toBeInTheDocument()
  })

  it("无 URL → 原样返回文本", () => {
    const nodes = linkifyText("没有任何链接的普通描述")
    expect(nodes).toHaveLength(1)
  })

  it("空值安全", () => {
    expect(linkifyText("")).toEqual([])
  })
})
