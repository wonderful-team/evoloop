import * as React from "react"
import { Loader2, Wrench } from "lucide-react"
import { Badge } from "../ui/badge"
import type { ToolCallTraceData } from "./types"

const TOOL_DETAIL_KEYS = [
  "command",
  "pattern",
  "sql",
  "query",
  "prompt",
  "question",
  "content",
]

const TOOL_INLINE_PARAM_KEYS = [
  "prompt",
  "url",
  "path",
  "source",
  "pattern",
  "query",
  "name",
  "identifier",
  "content",
]

export interface ToolCallItemProps {
  data: ToolCallTraceData
  variant?: "compact" | "timeline"
  defaultExpanded?: boolean
  className?: string
  renderDetail?: (content: string) => React.ReactNode
}

export function ToolCallItem({
  data,
  variant = "compact",
  defaultExpanded = false,
  className = "",
  renderDetail,
}: ToolCallItemProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded)

  const toolInput = data.input || {}
  const rawDisplayName = data.displayName || data.toolName

  let header = rawDisplayName
  let detail: string | null = null

  // 1. 尝试从入参中提取长文本 detail
  for (const key of TOOL_DETAIL_KEYS) {
    const value = toolInput[key]
    if (typeof value === "string") {
      const trimmed = value.trim()
      if (trimmed && (trimmed.length > 48 || trimmed.includes("\n"))) {
        detail = value
        break
      }
    }
  }

  // 2. 如果没有长文本，尝试提取简短的内联参数以美化单行 header
  if (!detail && !data.displayName) {
    for (const key of TOOL_INLINE_PARAM_KEYS) {
      const value = toolInput[key]
      if (typeof value === "string") {
        const trimmed = value.trim()
        if (trimmed) {
          header = `${data.toolName} '${trimmed}'`
          break
        }
      }
    }
  }

  const isRunning = data.status === "running" || data.status === "streaming"
  const isFailed = data.status === "failed"

  if (variant === "timeline") {
    return (
      <div className={`space-y-1 ${className}`}>
        <div
          className="flex items-center gap-1.5 cursor-pointer select-none text-[11px] font-mono hover:text-foreground text-muted-foreground transition-colors"
          onClick={() => setExpanded(!expanded)}
        >
          <Wrench className="h-3 w-3 text-sky-500 shrink-0" />
          <span className="font-semibold text-sky-600 dark:text-sky-400">
            {data.toolName}()
          </span>
          <span className="truncate flex-1 text-muted-foreground/80">
            {header !== data.toolName ? header : ""}
          </span>
          {isRunning && (
            <Loader2 className="h-3 w-3 animate-spin text-primary ml-auto shrink-0" />
          )}
          {isFailed && (
            <span className="text-[10px] text-destructive shrink-0 ml-auto">
              failed
            </span>
          )}
          {data.changesetCount !== undefined && data.changesetCount > 0 && (
            <Badge
              variant="secondary"
              className="h-4 px-1 text-[9px] bg-primary/10 text-primary border-none shrink-0 ml-auto"
            >
              {data.changesetCount} 文件
            </Badge>
          )}
        </div>

        {expanded && (
          <div className="pl-4 pt-1 space-y-1.5 text-xs text-muted-foreground font-mono">
            {detail && (
              <pre className="p-2 rounded bg-muted/40 max-h-48 overflow-y-auto whitespace-pre-wrap break-all text-[11px]">
                {renderDetail ? renderDetail(detail) : detail}
              </pre>
            )}
            {data.output !== undefined && data.output !== null && (
              <pre className="p-2 rounded bg-muted/30 max-h-60 overflow-y-auto whitespace-pre-wrap break-all text-[11px]">
                {typeof data.output === "string"
                  ? data.output
                  : JSON.stringify(data.output, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    )
  }

  // compact variant (chat stream)
  return (
    <div
      className={`group relative flex w-full py-1 px-3 my-0.5 rounded transition-colors font-mono text-[12px] text-muted-foreground/70 hover:text-muted-foreground bg-muted/10 hover:bg-muted/25 ${
        detail ? "flex-col items-stretch gap-1" : "items-center gap-2.5"
      } ${className}`}
    >
      <div
        className="flex items-center gap-2.5 min-w-0 w-full cursor-pointer"
        onClick={() => detail && setExpanded(!expanded)}
      >
        <div
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            isRunning
              ? "bg-primary shadow-[0_0_6px_var(--primary)]"
              : isFailed
                ? "bg-destructive"
                : data.status === "waiting_human"
                  ? "bg-warning"
                  : "bg-foreground/25"
          }`}
        />
        <span className="truncate flex-1" title={detail || header}>
          {header}
        </span>
        {isRunning && (
          <Loader2 className="h-3 w-3 animate-spin text-primary ml-2 shrink-0" />
        )}
        {isFailed && (
          <span className="ml-2 shrink-0 text-[10px] text-destructive">
            failed
          </span>
        )}
        {data.changesetCount !== undefined && data.changesetCount > 0 && (
          <Badge
            variant="secondary"
            className="h-4 px-1.5 text-[9px] bg-primary/10 text-primary border-none shrink-0 ml-auto"
          >
            {data.changesetCount} 文件
          </Badge>
        )}
      </div>
      {detail && (
        <pre className="pl-4 max-h-40 overflow-y-auto font-mono text-[11px] leading-[1.6] whitespace-pre-wrap break-all text-muted-foreground/55">
          {renderDetail ? renderDetail(detail) : detail}
        </pre>
      )}
    </div>
  )
}
