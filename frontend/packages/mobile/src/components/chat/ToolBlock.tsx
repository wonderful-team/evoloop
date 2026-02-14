import { CheckCircle2, Loader2, XCircle } from "lucide-react"
import { cn } from "@evoloop/shared"

export interface ToolBlockProps {
    toolName: string
    result?: string
    results?: string[] // Added for merged view
    isFile?: boolean
    status: "running" | "success" | "error"
    timestamp: number
}

export function ToolBlock({ toolName, result, results, status, isFile }: ToolBlockProps) {
    return (
        <div className="flex-shrink-0 rounded-xl border border-border/40 bg-background/40 overflow-hidden shadow-none my-1 transition-all hover:border-border/60">
            <div className="flex items-center justify-between p-2 px-3 bg-muted/30 border-b border-border/10">
                <div className="flex items-center gap-2.5 min-w-0">
                    <div className="shrink-0">
                        {status === "running" ? (
                            <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
                        ) : status === "error" ? (
                            <XCircle className="w-3 h-3 text-red-500" />
                        ) : (
                            <CheckCircle2 className="w-3 h-3 text-green-500" />
                        )}
                    </div>
                    <span className="text-[12px] font-bold text-foreground/90 truncate tracking-tight uppercase">
                        {toolName}
                    </span>
                </div>
            </div>

            <div className="p-2.5 px-3 bg-card/5">
                {/* Result only, merged view */}
                {(result || results) ? (
                    <div className={cn(
                        "p-2.5 rounded-xl border border-border/10 font-mono text-foreground/80 break-all max-h-[300px] overflow-y-auto leading-relaxed custom-scrollbar whitespace-pre-wrap text-[11px]",
                        isFile ? "bg-primary/5 border-primary/10 text-foreground/90" : "bg-muted/30"
                    )}>
                        {results ? (
                            <div className="space-y-1">
                                {results.map((r, idx) => (
                                    <div key={idx} className={cn(idx > 0 && "pt-1 border-t border-border/5")}>
                                        {r}
                                    </div>
                                ))}
                            </div>
                        ) : result}
                    </div>
                ) : status === "running" ? (
                    <div className="py-2 text-muted-foreground/60 italic text-[10px] animate-pulse">
                        {/* Empty spacer or subtle hint */}
                        ...
                    </div>
                ) : null}
            </div>
        </div>
    )
}
