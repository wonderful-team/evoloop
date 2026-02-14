import { ChevronDown, ChevronUp, BrainCircuit } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared/lib/utils"

export interface ThinkingBlockProps {
    content: string
    timestamp: number
    isComplete?: boolean
}

export function ThinkingBlock({ content, timestamp, isComplete = true }: ThinkingBlockProps) {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(!isComplete) // Auto-expand if still streaming/thinking

    return (
        <div className="my-2 border rounded-lg overflow-hidden bg-muted/30 border-muted">
            <div
                className="flex items-center justify-between p-2 px-3 bg-muted/50 cursor-pointer hover:bg-muted/70 transition-colors"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <BrainCircuit className="w-3.5 h-3.5" />
                    <span>{t("chat.thinking", "Thought Process")}</span>
                    {!isComplete && <span className="animate-pulse">...</span>}
                </div>

                {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                )}
            </div>

            {isExpanded && (
                <div className="p-3 text-xs font-mono text-muted-foreground bg-black/5 dark:bg-white/5 whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-y-auto">
                    {content || <span className="italic opacity-50">{t("chat.thinkingEmpty", "Processing...")}</span>}
                </div>
            )}
        </div>
    )
}
