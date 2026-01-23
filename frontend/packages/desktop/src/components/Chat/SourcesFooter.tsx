import {
    ChevronDown,
    Brain,
    FileText,
    Search,
    Terminal,
    BookOpen
} from "lucide-react"
import { memo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"

interface Reference {
    type: "memory" | "file" | "search" | "tool" | string
    name: string
    path?: string
    content?: string
}

interface SourcesFooterProps {
    references: Reference[]
    maxVisible?: number
}

/**
 * SourcesFooter - Displays message sources with collapse/expand for >3 items
 */
export const SourcesFooter = memo(({ references, maxVisible = 3 }: SourcesFooterProps) => {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(false)

    if (!references || references.length === 0) return null

    const visibleRefs = isExpanded ? references : references.slice(0, maxVisible)
    const hiddenCount = references.length - maxVisible

    const getIcon = (type: string) => {
        switch (type) {
            case "memory":
                return <Brain size={14} className="text-amber-500" />
            case "file":
                return <FileText size={14} className="text-blue-500" />
            case "search":
                return <Search size={14} className="text-purple-500" />
            case "tool":
                return <Terminal size={14} className="text-slate-500" />
            default:
                return <BookOpen size={14} className="text-muted-foreground" />
        }
    }

    return (
        <div className="mt-2 pt-2 border-t border-border/50">
            <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-muted-foreground shrink-0">
                    {t("chat.sources.title", "Sources:")}
                </span>
                {visibleRefs.map((ref, idx) => (
                    <span
                        key={`${ref.type}-${ref.name}-${idx}`}
                        className={cn(
                            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md",
                            "bg-muted/50 text-xs text-muted-foreground",
                            "hover:bg-muted transition-colors cursor-default"
                        )}
                        title={ref.path || ref.content || ref.name}
                    >
                        <span>{getIcon(ref.type)}</span>
                        <span className="max-w-[100px] truncate">{ref.name}</span>
                    </span>
                ))}
                {hiddenCount > 0 && !isExpanded && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-5 px-1.5 text-xs text-muted-foreground hover:text-foreground"
                        onClick={() => setIsExpanded(true)}
                    >
                        +{hiddenCount} {t("chat.sources.more", "more")}
                        <ChevronDown size={12} className="ml-0.5" />
                    </Button>
                )}
                {isExpanded && hiddenCount > 0 && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-5 px-1.5 text-xs text-muted-foreground hover:text-foreground"
                        onClick={() => setIsExpanded(false)}
                    >
                        {t("chat.sources.showLess", "Show less")}
                    </Button>
                )}
            </div>
        </div>
    )
})

SourcesFooter.displayName = "SourcesFooter"
