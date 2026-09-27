import {describe, expect, it} from "vitest"

import {stripMarkdownTokens} from "./mdText"

describe("stripMarkdownTokens · 摘要脱壳", () => {
  it("剥掉加粗/行内代码/删除线，保留内容", () => {
    expect(stripMarkdownTokens("**重点**：核对 `refund_status` 值~~待定~~")).toBe(
      "重点：核对 refund_status 值待定",
    )
  })

  it("标题井号与引用符移除", () => {
    expect(stripMarkdownTokens("## 目标\n> 背景说明")).toBe("目标\n背景说明")
  })

  it("无序列表符 → 间隔点；有序编号保留", () => {
    const out = stripMarkdownTokens("- 查订单\n- 查库存\n\n1. 先查主表\n2. 再查明细")
    expect(out).toContain("· 查订单")
    expect(out).toContain("· 查库存")
    expect(out).toContain("1. 先查主表")
    expect(out).toContain("2. 再查明细")
  })

  it("链接留文字，图片整体移除", () => {
    expect(stripMarkdownTokens("详见 [运营文档](https://x.y) ![截图](a.png)")).toBe(
      "详见 运营文档",
    )
  })

  it("代码围栏保留内容，去掉围栏与语言标注", () => {
    const out = stripMarkdownTokens("```sql\nSELECT 1\n```")
    expect(out).toContain("SELECT 1")
    expect(out).not.toContain("```")
    expect(out).not.toContain("sql")
  })

  it("表格：分隔行移除，竖线退化", () => {
    const out = stripMarkdownTokens("| a | b |\n|---|---|\n| 1 | 2 |")
    expect(out).not.toContain("---")
    expect(out).toContain("a")
    expect(out).toContain("1")
  })

  it("snake_case 不被斜体规则误伤", () => {
    expect(stripMarkdownTokens("字段 task_no_field 保持原样")).toBe(
      "字段 task_no_field 保持原样",
    )
  })

  it("空值安全", () => {
    expect(stripMarkdownTokens(null)).toBe("")
    expect(stripMarkdownTokens("")).toBe("")
  })
})
