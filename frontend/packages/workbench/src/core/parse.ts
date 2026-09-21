/* Pure parsing layer for the duty execution panel.
 * Everything here is side-effect-free and unit-testable against
 * real message shapes found in the wild (SQLite messages table). */


export interface Msg {
  id?: string
  role?: string
  content?: unknown
  thinking?: string | null
  name?: string
  tool_calls?: unknown
  tool_name?: string | null
  category?: string | null
  content_type?: string | null
  created_at?: string | null
  attachments?: unknown
}

const ARTIFACT_RE = /(已写入|已创建|已下架|已更新|已发布|已上架|已生成|已完成)/
const ERROR_RE = /(error|failed|失败|异常|超时|timeout)/i

/** single-line summary for tool outputs: JSON gives key facts, text gives first line */
export function summarizeOutput(raw: string): string {
  const one = raw.replace(/\s+/g, " ").trim()
  const trimmed = one
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>
      if (parsed && typeof parsed === "object") {
        if (typeof parsed.summary === "string") return parsed.summary
        const keys = Object.keys(parsed)
        if (keys.length <= 4) {
          const kv = keys
            .map((k) => {
              const v = parsed[k]
              const sv =
                typeof v === "string"
                  ? v.slice(0, 40)
                  : Array.isArray(v)
                    ? `[${v.length} items]`
                    : typeof v === "object" && v
                      ? `{${Object.keys(v).length} keys}`
                      : String(v)
              return `${k}: ${sv}`
            })
            .join(" | ")
          return kv || trimmed.slice(0, 120)
        }
        return `${keys.length} fields`
      }
    } catch {
      /* fall through */
    }
  }
  return one.slice(0, 160)
}

/** strip MCP python-repr shells:
 *  ...content=[TextContent(type='text', text='...')] / variants with trailing kwargs */
export function stripMcpRepr(raw: string): string {
  const m =
    /content=\[(?:TextContent\()?type='text', text='([\s\S]*?)'(?:, |\)\])/.exec(
      raw,
    )
  if (m) return m[1]
  return raw
}

/** humanize message content: blocks / objects / repr shells / pretty JSON.
 *  Fallbacks: content "" → thinking column (LangGraph agent replies).
 *  Workflow JSON with a top-level string `summary` → show summary only
 *  (the machine-readable `data` stays available via the raw message). */
export function textOf(m: Msg): string {
  const c = m.content
  let raw = ""
  if (typeof c === "string") raw = c
  else if (Array.isArray(c)) {
    raw = c
      .map((b) =>
        b && typeof b === "object" && "text" in (b as Record<string, unknown>)
          ? String((b as { text?: unknown }).text ?? "")
          : "",
      )
      .filter(Boolean)
      .join("\n")
  } else if (c != null) {
    raw = JSON.stringify(c)
  }
  raw = stripMcpRepr(raw)
  const trimmed = raw.trim()
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown> | unknown[]
      if (parsed && typeof parsed === "object") {
        if (
          !Array.isArray(parsed) &&
          typeof (parsed as Record<string, unknown>).summary === "string"
        ) {
          return (parsed as { summary: string }).summary
        }
        return JSON.stringify(parsed, null, 1)
      }
    } catch {
      /* not JSON — return as-is */
    }
  }
  if (!raw.trim() && m.thinking) return m.thinking
  return raw
}

export function toolNameOf(m: Msg): string {
  if (m.tool_name) return m.tool_name
  if (m.name) return m.name
  let tc = m.tool_calls
  if (typeof tc === "string") {
    try {
      tc = JSON.parse(tc)
    } catch {
      tc = null
    }
  }
  const arr = Array.isArray(tc) ? tc : [tc]
  for (const c of arr) {
    const obj = c as
      | { name?: string; function?: { name?: string } }
      | null
      | undefined
    if (!obj || typeof obj !== "object") continue
    if (obj.name) return obj.name
    if (obj.function?.name) return obj.function.name
  }
  return ""
}

/** classify a message into a timeline node kind.
 *  backend `category` (structured) wins over text heuristics. */
export type NodeKind =
  | "tool"
  | "think"
  | "artifact"
  | "error"
  | "hitl"
  | "instruction"

export function classify(m: Msg): NodeKind {
  if (m.category === "hitl_request" || m.role === "system") return "hitl"
  if (m.role === "human" || m.role === "user") return "instruction"
  if (m.category === "tool_output" || m.role === "tool") {
    // tool outputs use ✅/❌ prefixes from the executor — trust those
    const raw = typeof m.content === "string" ? m.content : textOf(m)
    if (raw.startsWith("❌") || /\b(Command Failed|error:)/i.test(raw.slice(0, 80))) {
      return "error"
    }
    return "tool"
  }
  if (m.category === "assistant_tool_call") return "tool"
  const text = textOf(m)
  // model/provider failures are uniformly prefixed with ❌ by the engine —
  // never guess "error" from free prose (long prompts/copy contain 超时/失败 words)
  if (text.startsWith("❌") || text.includes("模型调用异常")) return "error"
  if (ARTIFACT_RE.test(text)) return "artifact"
  return "think"
}

export { ARTIFACT_RE, ERROR_RE }

import type { HumanRequestItem } from "@evoloop/shared"

export function hitlRequestFromMsg(
  m: Msg,
  threadId: string,
): HumanRequestItem | null {
  try {
    const payload = JSON.parse(textOf(m)) as {
      id?: string
      type?: string
      prompt?: string
      options?: string[]
      context?: string
    }
    if (!payload.id) return null
    return {
      id: payload.id,
      type: payload.type ?? "approval",
      prompt: payload.prompt ?? "",
      options: payload.options ?? [],
      context: payload.context ?? null,
      thread_id: threadId,
    }
  } catch {
    return null
  }
}
