import type {ReactNode} from "react"

/**
 * 纯文本 → 可点链接：识别 http(s) URL 渲染为锚点（其余文本原样）。
 *
 * 用途：任务描述/提案正文里的来源链接（Agent 上报的引用、原帖地址等）
 * 要能点开核对。轻量实现——shared 包不依赖 react-markdown 全家桶；
 * 聊天管线（MessageContent）已有 remark-gfm autolink，此处只覆盖
 * 不走 markdown 渲染的描述位。
 */
const URL_RE = /(https?:\/\/[^\s<>()"'\u3001\u3002，。；]+)/g

export function linkifyText(text: string): ReactNode[] {
  if (!text) return []
  const nodes: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(URL_RE)) {
    const idx = match.index ?? 0
    if (idx > last) nodes.push(text.slice(last, idx))
    const url = match[0]
    // 去尾部标点（句号/逗号/右括号常见贴在 URL 后）
    const trimmed = url.replace(/[.,;:!?)）\]】」」]+$/, "")
    nodes.push(
      <a
        key={`${idx}-${url}`}
        href={trimmed}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2 break-all hover:opacity-80"
        onClick={(e) => e.stopPropagation()}
      >
        {trimmed}
      </a>,
    )
    last = idx + trimmed.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
