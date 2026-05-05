import { Message } from "./ChatMessageItem"
import { CheckCircle2, ChevronRight, Loader2, XCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { Button } from "@evoloop/shared/components/ui/button"

interface ToolExecutionGroupProps {
  steps: Message[]
}

export function ToolExecutionGroup({ steps }: ToolExecutionGroupProps) {
  const { t } = useTranslation()

  if (steps.length === 0) return null
  
  // Logic: Hide in main chat if any tool is still running
  // It will be visible in the Activity Sidebar instead during execution
  const isAnyRunning = steps.some(s => s.status === "running")
  if (isAnyRunning) return null

  return (
    <div className="ml-12 mb-6">
      <Collapsible defaultOpen={false} className="w-full">
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-0 text-[10px] text-muted-foreground/50 hover:bg-transparent flex items-center gap-2 w-full justify-start font-mono group/trigger"
          >
            <ChevronRight className="h-3 w-3 group-data-[state=open]/trigger:rotate-90 transition-transform opacity-40" />
            <span className="uppercase tracking-wider opacity-60 font-bold">
              {t("chat.interface.toolExecutionSteps", { count: steps.length })}
            </span>
          </Button>
        </CollapsibleTrigger>
        
        <CollapsibleContent className="pt-2">
          <div className="flex flex-col gap-0 relative">
            {/* Vertical Timeline Rail */}
            <div className="absolute left-[7px] top-1 bottom-1 w-[1px] bg-border/40" />

            {steps.map((step, idx) => {
              const toolMeta = step.tool_meta || step.meta_data?.tool_meta
              const displayName = toolMeta?.display_name || step.tool_name || step.meta_data?.tool_name || t("chat.messageList.toolExecution")
              
              const input = step.input || step.meta_data?.input
              let inputSnippet = ""
              if (input && typeof input === "object") {
                  const priorityKeys = ["path", "file", "command", "query", "url"]
                  const key = priorityKeys.find(k => input[k])
                  if (key) {
                      inputSnippet = String(input[key])
                  } else {
                      const firstVal = Object.values(input).find(v => typeof v === "string")
                      if (firstVal) inputSnippet = String(firstVal)
                  }
              }

              const isFailed = step.status === "failed"

              return (
                <div key={step.id || idx} className="flex items-center gap-3 py-1 group relative pl-5">
                  {/* Horizontal connection dot */}
                  <div className="absolute left-[4px] w-1.5 h-1.5 rounded-full border border-background bg-border/60 group-hover:bg-primary/40 transition-colors" />

                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-[10px] font-bold text-muted-foreground/70 font-mono tracking-tight uppercase truncate flex-1 min-w-0" title={displayName}>
                      {displayName}
                    </span>
                    {inputSnippet && (
                      <>
                        <span className="text-[10px] text-muted-foreground/20">•</span>
                        <span className="text-[10px] text-muted-foreground/40 truncate font-mono italic">
                          {inputSnippet}
                        </span>
                      </>
                    )}
                  </div>

                  <div className="flex items-center">
                    {isFailed ? (
                      <XCircle className="h-3 w-3 text-red-500/50" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3 text-primary/30" />
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
