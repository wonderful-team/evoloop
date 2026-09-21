import * as React from "react"
import {
  AlertTriangle,
  BadgeCheck,
  Brain,
  ListTodo,
  Package,
} from "lucide-react"
import type { TraceNodeItem, TraceNodeKind } from "./types"
import { ToolCallItem } from "./ToolCallItem"

const NODE_STYLE: Record<
  TraceNodeKind,
  { dot: string; label: string; labelCls: string }
> = {
  tool: {
    dot: "bg-sky-500",
    label: "工具",
    labelCls: "text-sky-600 dark:text-sky-400 font-mono",
  },
  think: {
    dot: "bg-muted-foreground/40",
    label: "思考",
    labelCls: "text-muted-foreground",
  },
  artifact: {
    dot: "bg-emerald-500",
    label: "产出",
    labelCls: "text-emerald-600 dark:text-emerald-400",
  },
  error: {
    dot: "bg-destructive",
    label: "异常",
    labelCls: "text-destructive",
  },
  hitl: {
    dot: "bg-amber-500",
    label: "等待人工",
    labelCls: "text-amber-600 dark:text-amber-400",
  },
  instruction: {
    dot: "bg-primary/70",
    label: "任务指令",
    labelCls: "text-primary",
  },
  system: {
    dot: "bg-muted-foreground/30",
    label: "系统事件",
    labelCls: "text-muted-foreground",
  },
}

export interface AgentExecutionTimelineProps {
  items: TraceNodeItem[]
  className?: string
  emptyText?: string
  renderNodeExtra?: (node: TraceNodeItem) => React.ReactNode
  renderContent?: (content: string) => React.ReactNode
}

export function AgentExecutionTimeline({
  items,
  className = "",
  emptyText = "暂无执行记录",
  renderNodeExtra,
  renderContent,
}: AgentExecutionTimelineProps) {
  const [expandedIndices, setExpandedIndices] = React.useState<Set<number>>(
    new Set(),
  )

  const toggleExpand = (idx: number) => {
    setExpandedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (items.length === 0) {
    return <div className="text-xs text-muted-foreground p-2">{emptyText}</div>
  }

  return (
    <div className={`relative pl-4 space-y-1 ${className}`}>
      {/* 垂直时间线 */}
      <span className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-border" />

      {items.map((node, i) => {
        const style = NODE_STYLE[node.kind] || NODE_STYLE.system
        const isOpen = expandedIndices.has(i)
        const text = node.content || ""
        const preview = text.slice(0, 160)

        // 如果是纯工具调用，并且有结构化数据，直接渲染 ToolCallItem
        if (node.kind === "tool" && node.toolData) {
          return (
            <div key={node.id || i} className="relative">
              <span
                className={`absolute -left-4 top-1.5 h-2 w-2 rounded-full ${style.dot}`}
              />
              <div className="rounded-md px-2 py-1.5 hover:bg-muted/30 transition-colors">
                <ToolCallItem
                  data={node.toolData}
                  variant="timeline"
                  defaultExpanded={isOpen}
                  renderDetail={renderContent}
                />
                {renderNodeExtra && renderNodeExtra(node)}
              </div>
            </div>
          )
        }

        return (
          <div key={node.id || i} className="relative">
            <span
              className={`absolute -left-4 top-1.5 h-2 w-2 rounded-full ${style.dot}`}
            />
            <div
              className="rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/40 transition-colors"
              onClick={() => toggleExpand(i)}
            >
              <div className="flex items-center gap-1.5 text-[10px] mb-0.5 select-none">
                {node.kind === "instruction" && (
                  <ListTodo className="h-2.5 w-2.5 text-primary" />
                )}
                {node.kind === "think" && (
                  <Brain className="h-2.5 w-2.5 text-muted-foreground" />
                )}
                {node.kind === "error" && (
                  <AlertTriangle className="h-2.5 w-2.5 text-destructive" />
                )}
                {node.kind === "artifact" && (
                  <Package className="h-2.5 w-2.5 text-emerald-500" />
                )}
                {node.kind === "hitl" && (
                  <BadgeCheck className="h-2.5 w-2.5 text-amber-500" />
                )}

                <span className={`font-medium ${style.labelCls}`}>
                  {node.title || style.label}
                </span>

                {!isOpen && text.length > 160 && (
                  <span className="text-muted-foreground/50 ml-auto">
                    展开全部 ({text.length} 字)
                  </span>
                )}
              </div>

              {isOpen ? (
                <div className="text-xs text-muted-foreground [&_pre]:bg-muted/60 [&_pre]:rounded-md [&_pre]:p-2 [&_pre]:text-[11px] font-mono leading-relaxed">
                  {renderContent ? renderContent(text) : text}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                  {preview}
                </div>
              )}

              {renderNodeExtra && renderNodeExtra(node)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
