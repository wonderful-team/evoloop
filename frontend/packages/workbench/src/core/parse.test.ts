import { describe, expect, it } from "vitest"

import {
  classify,
  stripMcpRepr,
  textOf,
  toolNameOf,
} from "./parse"

describe("stripMcpRepr", () => {
  it("extracts inner text from MCP TextContent repr with trailing kwargs", () => {
    const raw =
      "meta=None content=[TextContent(type='text', text='{\\n    \"page_count\": 0,\n    \"count\": 0,\n    \"list\": []\n}', annotations=None, meta=None)] structured_content=None"
    const out = stripMcpRepr(raw)
    expect(out).toContain('"page_count": 0')
    expect(out).not.toContain("meta=None")
  })

  it("extracts short single-line repr", () => {
    expect(
      stripMcpRepr("content=[TextContent(type='text', text='✅ done')] x"),
    ).toBe("✅ done")
  })

  it("leaves plain text untouched", () => {
    expect(stripMcpRepr("普通回复")).toBe("普通回复")
  })
})

describe("textOf", () => {
  it("joins content block arrays", () => {
    expect(
      textOf({ content: [{ type: "text", text: "你好" }, { text: "世界" }] }),
    ).toBe("你好\n世界")
  })

  it("pretty-prints JSON strings", () => {
    const out = textOf({ content: '{"count":0,"list":[]}' })
    expect(out).toContain('"count": 0')
    expect(out).toContain("\n")
  })

  it("stringifies non-string objects", () => {
    expect(textOf({ content: { a: 1 } })).toContain('"a": 1')
  })

  it("unwraps MCP repr before JSON pretty-printing", () => {
    const raw =
      "content=[TextContent(type='text', text='{\"ok\": true}', annotations=None)]"
    expect(textOf({ content: raw })).toContain('"ok": true')
  })
})

describe("toolNameOf", () => {
  it("prefers backend tool_name column", () => {
    expect(
      toolNameOf({ tool_name: "mcp__mall__list_goods", name: "ignored" }),
    ).toBe("mcp__mall__list_goods")
  })

  it("parses tool_calls JSON string with openai shape", () => {
    expect(
      toolNameOf({
        tool_calls:
          '[{"id":"c1","function":{"name":"web_search","arguments":"{}"}}]',
      }),
    ).toBe("web_search")
  })

  it("reads native name field", () => {
    expect(toolNameOf({ name: "write_report" })).toBe("write_report")
  })

  it("returns empty string when nothing matches", () => {
    expect(toolNameOf({})).toBe("")
  })
})

describe("classify", () => {
  it("tool_output category → tool node", () => {
    expect(classify({ role: "ai", category: "tool_output" })).toBe("tool")
  })

  it("assistant_tool_call category → tool node", () => {
    expect(classify({ role: "ai", category: "assistant_tool_call" })).toBe(
      "tool",
    )
  })

  it("❌-prefixed model failure → error node", () => {
    expect(
      classify({
        role: "ai",
        content: "❌ **模型调用异常**: Error code: 400",
      }),
    ).toBe("error")
  })

  it("❌-prefixed tool failure → error node", () => {
    expect(
      classify({ role: "tool", content: "❌ Command Failed: exit 1" }),
    ).toBe("error")
  })

  it("prose containing 超时/失败 does NOT become error (human prompts, copy)", () => {
    expect(
      classify({
        role: "human",
        content: "你是文案 Agent。生成标题详情卖点，并检查夸张宣传风险。营销文案若超时应重试",
      }),
    ).toBe("instruction")
    expect(
      classify({
        role: "ai",
        content: "广告文案草稿已写入 data/copy_draft_output.json",
      }),
    ).toBe("artifact")
  })

  it("artifact verbs → artifact node", () => {
    expect(classify({ role: "ai", content: "报告已写入 reports/x.md" })).toBe(
      "artifact",
    )
  })

  it("plain reasoning → think node", () => {
    expect(classify({ role: "ai", content: "先拉取商品列表再核对库存" })).toBe(
      "think",
    )
  })

  it("hitl_request category / system role → hitl node", () => {
    expect(classify({ role: "system", category: "hitl_request" })).toBe("hitl")
    expect(classify({ role: "system", content: '{"id":"x"}' })).toBe("hitl")
  })
})

describe("real-world message shapes (LangGraph agents)", () => {
  it("empty content with thinking column → shows thinking text", () => {
    expect(
      textOf({ role: "ai", content: "", thinking: "The JSON has been saved." }),
    ).toBe("The JSON has been saved.")
  })

  it("workflow JSON with top-level summary → summary only (not raw JSON)", () => {
    const out = textOf({
      role: "ai",
      content:
        '{"summary":"完成两套完整商品文案","data":{"OPP-01":{},"OPP-02":{}},"risks":[],"recommendation":"continue"}',
    })
    expect(out).toBe("完成两套完整商品文案")
  })

  it("non-summary JSON still pretty-prints", () => {
    expect(textOf({ content: '{"count":0}' })).toContain('"count": 0')
  })
})
