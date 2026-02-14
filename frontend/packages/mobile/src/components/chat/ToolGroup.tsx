import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronDown, ChevronRight, Wrench, Brain } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@evoloop/shared/components/ui/collapsible"
import { Button } from "@evoloop/shared/components/ui/button"
import { ToolBlock, ToolBlockProps } from "./ToolBlock"
import { cn } from "@evoloop/shared"

interface ToolGroupProps {
    tools: ToolBlockProps[]
    timestamp: number
    thought?: string
}

export function ToolGroup({ tools, thought }: ToolGroupProps) {
    const { t } = useTranslation()
    const [isOpen, setIsOpen] = useState(false)

    // Calculate stats
    const count = tools.length
    const hasError = tools.some(t => t.status === "error")
    const isRunning = tools.some(t => t.status === "running")

    return (
        <div className="my-1 border rounded-xl overflow-hidden bg-card shadow-sm border-border/30 transition-all duration-300">
            {thought && (
                <div className="p-3 border-b border-border/40 bg-muted/10 text-sm">
                    <div className="flex gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-primary/5 flex items-center justify-center shrink-0 border border-primary/5">
                            <Brain className="w-4 h-4 text-primary/70" />
                        </div>
                        <div className="flex-1 py-1 text-foreground/90 leading-relaxed text-left">
                            {thought}
                        </div>
                    </div>
                </div>
            )}

            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
                <div
                    className="flex items-center justify-between p-3 bg-muted/20 hover:bg-muted/30 transition-colors cursor-pointer active:scale-[0.99] origin-center"
                    onClick={() => setIsOpen(!isOpen)}
                >
                    <div className="flex items-center gap-3">
                        <div className={cn(
                            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 shadow-sm border",
                            hasError ? "bg-destructive/10 text-destructive border-destructive/20" :
                                isRunning ? "bg-blue-500/10 text-blue-500 border-blue-500/20" :
                                    "bg-primary/10 text-primary border-primary/20"
                        )}>
                            <Wrench className="w-4 h-4" />
                        </div>

                        <div className="flex flex-col text-left">
                            <span className="text-sm font-bold text-foreground tracking-tight">
                                {t("chat.toolGroup.title", { count })}
                            </span>
                            <span className="text-[10px] text-muted-foreground font-mono opacity-80 leading-none mt-0.5">
                                {tools.map(t => t.toolName).slice(0, 3).join(", ")}
                                {tools.length > 3 && "..."}
                            </span>
                        </div>
                    </div>

                    <CollapsibleTrigger asChild>
                        <Button variant="ghost" size="sm" className="w-8 h-8 p-0 text-muted-foreground hover:bg-muted/50 rounded-full">
                            {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            <span className="sr-only">Toggle</span>
                        </Button>
                    </CollapsibleTrigger>
                </div>

                <CollapsibleContent className="bg-muted/5 border-t border-border/10 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 duration-200">
                    <div className="flex flex-col p-2 pt-1 gap-1 max-h-[60vh] overflow-y-auto custom-scrollbar">
                        {(() => {
                            const grouped: any[] = [];
                            tools.forEach((tool) => {
                                const last = grouped[grouped.length - 1];
                                if (last && last.toolName === tool.toolName && last.status === tool.status) {
                                    if (!last.results) {
                                        last.results = [last.result || ""];
                                        last.result = undefined;
                                    }
                                    last.results.push(tool.result || "");
                                    // Use the latest timestamp for the block? Or keep the first. 
                                    // Historically keeps the first for positioning.
                                } else {
                                    grouped.push({ ...tool });
                                }
                            });

                            return grouped.map((group, index) => (
                                <ToolBlock key={`${group.timestamp}-${index}`} {...group} />
                            ));
                        })()}
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </div>
    )
}
