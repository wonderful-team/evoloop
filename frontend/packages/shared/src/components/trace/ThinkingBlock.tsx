import * as React from "react"
import { Brain, ChevronRight, Loader2 } from "lucide-react"
import { Button } from "../ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible"
import type { ThinkingTraceData } from "./types"

export interface ThinkingBlockProps {
  data: ThinkingTraceData
  defaultOpen?: boolean
  className?: string
  renderContent?: (content: string) => React.ReactNode
}

export function ThinkingBlock({
  data,
  defaultOpen = false,
  className = "",
  renderContent,
}: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  const isStreaming = data.isStreaming === true

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className={`mb-2 overflow-hidden ${className}`}
    >
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="group/trigger h-6 px-2 rounded text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors hover:bg-muted/40 flex items-center gap-1.5"
        >
          <Brain className="h-3 w-3 text-primary/70" />
          <span>{isStreaming ? "正在思考..." : "思考过程"}</span>
          {data.duration && (
            <span className="text-[10px] text-muted-foreground/60">
              ({data.duration})
            </span>
          )}
          {isStreaming ? (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/50 ml-1" />
          ) : (
            <ChevronRight
              className={`h-3 w-3 transition-transform text-muted-foreground/50 ml-0.5 ${
                isOpen ? "rotate-90" : ""
              }`}
            />
          )}
        </Button>
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-1 pl-3 py-1 border-l-2 border-border/60 text-[12px] text-muted-foreground/80 leading-relaxed font-mono whitespace-pre-wrap">
        {renderContent ? renderContent(data.thinking) : data.thinking}
      </CollapsibleContent>
    </Collapsible>
  )
}
