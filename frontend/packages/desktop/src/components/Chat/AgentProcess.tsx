import {
    Loader2, PlusCircle
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { useState } from "react"
import { Button } from "@evoloop/shared/components/ui/button"
import type { ToolStep } from "@/types/toolstep"

// A Group is a collection of steps under a header
interface StepGroup {
    id: string
    title: string
    status: string
    steps: ToolStep[]
    isImplicit?: boolean
}

interface AgentProcessProps {
    steps: ToolStep[]
    header?: React.ReactNode
}



// Safe JSON parse helper
function safeJsonParse(str: string): any {
    if (!str || typeof str !== 'string') return null
    try {
        return JSON.parse(str)
    } catch {
        return null
    }
}

// Format tool input for display. Driven entirely by backend tool_meta.
// No hard-coded tool-specific logic.
function formatToolInput(
    input: any,
    toolMeta: any,
    t: any
): { label: string; value: string } | null {
    if (!input) return null

    let data = input
    if (typeof input === 'string') {
        data = safeJsonParse(input) || input
    }

    if (typeof data === 'string') {
        return { label: t("chat.process.param", "参数"), value: data }
    }

    // 1. Use backend-provided affected_path_keys
    if (toolMeta?.affected_path_keys?.length > 0) {
        for (const key of toolMeta.affected_path_keys) {
            if (data[key] != null && data[key] !== '') {
                return { label: t("chat.process.path", "路径"), value: String(data[key]) }
            }
        }
    }

    // 2. Generic fallback - show first meaningful field
    const skipFields = ['Mode', 'TaskName', 'TaskStatus']
    for (const [key, val] of Object.entries(data)) {
        if (skipFields.includes(key)) continue
        if (typeof val === 'string' && val) {
            return { label: key, value: val }
        }
        if (typeof val === 'number') {
            return { label: key, value: String(val) }
        }
    }

    return null
}

// Parse tool output into structured format
function parseToolOutput(output: string): { type: 'text' | 'json' | 'list' | 'error'; data: any } {
    if (!output) return { type: 'text', data: '' }

    const jsonData = safeJsonParse(output)
    if (jsonData) {
        if (Array.isArray(jsonData)) {
            return { type: 'list', data: jsonData }
        }
        if (typeof jsonData === 'object') {
            if (jsonData.error || jsonData.status === 'error') {
                return { type: 'error', data: jsonData.error || jsonData.message || output }
            }
            return { type: 'json', data: jsonData }
        }
    }

    return { type: 'text', data: output }
}

// Extract human-readable summary from tool output.
// Fully generic — no tool-specific logic.
function summarizeOutput(output: string, t: (key: string, options?: any) => string): { title: string; subtitle?: string; hasMore: boolean } {
    if (!output) return { title: "", hasMore: false }

    const MAX_LENGTH = 120
    const parsed = parseToolOutput(output)

    if (parsed.type === 'error') {
        const errorMsg = typeof parsed.data === 'string' ? parsed.data : JSON.stringify(parsed.data)
        return {
            title: errorMsg.length > MAX_LENGTH ? errorMsg.slice(0, MAX_LENGTH) + "..." : errorMsg,
            hasMore: errorMsg.length > MAX_LENGTH
        }
    }

    if (parsed.type === 'list' && Array.isArray(parsed.data)) {
        const count = parsed.data.length
        if (count === 0) return { title: t("chat.process.noResults"), hasMore: false }

        const firstItem = parsed.data[0]
        if (typeof firstItem === 'string') {
            return { title: t("chat.process.resultCount", { count }), subtitle: firstItem.slice(0, 50), hasMore: true }
        }
        if (typeof firstItem === 'object' && firstItem !== null) {
            const title = firstItem.title || firstItem.name || firstItem.path || firstItem.url || ''
            return { title: t("chat.process.resultCount", { count }), subtitle: title.slice(0, 50), hasMore: true }
        }
        return { title: t("chat.process.resultCount", { count }), hasMore: true }
    }

    if (parsed.type === 'json' && typeof parsed.data === 'object') {
        const data = parsed.data
        const priorityFields = ['message', 'result', 'content', 'summary', 'status', 'name', 'title']
        for (const field of priorityFields) {
            if (data[field]) {
                const val = String(data[field])
                return { title: val.slice(0, MAX_LENGTH), hasMore: val.length > MAX_LENGTH }
            }
        }

        const str = JSON.stringify(data)
        return { title: str.slice(0, MAX_LENGTH), hasMore: str.length > MAX_LENGTH }
    }

    const firstLine = output.split('\n')[0].trim()
    return {
        title: firstLine.slice(0, MAX_LENGTH),
        hasMore: output.length > firstLine.length || output.split('\n').length > 1
    }
}

// Grouping logic — simplified for ToolStep (flat list, no parent_id hierarchy)
function groupSteps(steps: ToolStep[], t: any): StepGroup[] {
    if (steps.length === 0) return []

    return [{
        id: "g-steps",
        title: t("chat.steps.execution"),
        status: steps.some(s => s.status === "running") ? "running" : "done",
        steps,
        isImplicit: true,
    }]
}

// Compact Step component
function StepRow({ step }: { step: ToolStep }) {
    const { t } = useTranslation()

    // Resolve display name from backend metadata (canonical source)
    const toolName = step.tool_meta?.display_name
        || step.name
        || step.tool_name
        || step.tool
        || t("chat.steps.unknown")

    const output = step.output || ''

    // Only show input params when display_name doesn't already contain them
    const inputInfo = step.tool_meta?.display_name
        ? null
        : formatToolInput(step.input, step.tool_meta, t)
    const outputSummary = summarizeOutput(output, t)

    const isRunning = step.status === "running"
    const isFailed = step.status === "failed"

    return (
        <div className="group relative flex gap-2 py-2 px-2 rounded-md hover:bg-muted/30 transition-colors animate-in fade-in slide-in-from-left-1">
            {/* Icon */}
            <div className="shrink-0 mt-0.5 text-muted-foreground">
                {isRunning ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                ) : isFailed ? (
                    <div className="h-3.5 w-3.5 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold">!</div>
                ) : (
                    <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 group-hover:bg-muted-foreground/60 transition-colors" />
                )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
                {/* Tool name */}
                <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-medium leading-tight ${isRunning ? "text-foreground" : "text-foreground/80"}`}>
                        {toolName}
                    </span>
                </div>

                {/* Input info */}
                {inputInfo && (
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground/80 mt-0.5">
                        <span className="text-muted-foreground/50">{inputInfo.label}:</span>
                        <span className="truncate" title={inputInfo.value}>{inputInfo.value}</span>
                    </div>
                )}

                {/* Output summary */}
                {outputSummary.title && (
                    <div className="mt-1 flex min-w-0">
                        <span className="text-[10px] text-muted-foreground/70 truncate flex-1 break-all" title={outputSummary.title}>
                            {isFailed && <span className="text-red-500 mr-1">{t("chat.steps.failed")}:</span>}
                            {outputSummary.title}
                            {outputSummary.subtitle && (
                                <span className="text-muted-foreground/50 ml-1">· {outputSummary.subtitle}</span>
                            )}
                        </span>
                    </div>
                )}
            </div>
        </div>
    )
}

function ProcessGroup({ group }: { group: StepGroup }) {
    const { t } = useTranslation()
    const isRunning = group.status === "running"

    return (
        <div className="w-full min-w-0 border-b border-border/30 last:border-b-0">
            <div className="p-1 px-2 flex flex-col gap-0.5">
                {group.steps.length === 0 && isRunning && (
                    <div className="text-[10px] text-muted-foreground/50 italic px-3 py-2">
                        {t("chat.process.initializing")}
                    </div>
                )}
                {group.steps.map((step, idx) => (
                    <StepRow key={step.id || idx} step={step} />
                ))}
            </div>
        </div>
    )
}

export function AgentProcess({ steps, header }: AgentProcessProps) {
    const { t } = useTranslation()
    const groups = groupSteps(steps || [], t)
    const [isFullyExpanded, setIsFullyExpanded] = useState(false)

    if (!steps || steps.length === 0) return null

    const MAX_VISIBLE_STEPS = 5
    const isHistorical = !header
    const shouldCollapse = isHistorical && steps.length > MAX_VISIBLE_STEPS && !isFullyExpanded

    const visibleGroups = shouldCollapse
        ? groups.slice(0, 1).map(g => ({ ...g, steps: g.steps.slice(0, MAX_VISIBLE_STEPS) }))
        : groups

    return (
        <div className="w-full min-w-0 flex flex-col gap-0.5">
            {header && (
                <div className="mb-1">
                    {header}
                </div>
            )}
            <div className="flex flex-col gap-0.5 animate-in fade-in slide-in-from-bottom-2 duration-300">
                {visibleGroups.map(group => (
                    <ProcessGroup key={group.id} group={group} />
                ))}
            </div>
            {shouldCollapse && (
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] text-muted-foreground/60 hover:text-primary w-fit mt-1 self-center"
                    onClick={() => setIsFullyExpanded(true)}
                >
                    <PlusCircle className="h-3 w-3 mr-1" />
                    {t("chat.steps.showMore")} ({steps.length - MAX_VISIBLE_STEPS}+)
                </Button>
            )}
        </div>
    )
}
