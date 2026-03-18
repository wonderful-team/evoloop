import { Check, Loader2, ChevronDown, ChevronRight, ExternalLink, FileText, Search, Terminal, Code, Globe } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"

export interface AgentProcessStep {
    id: string | number
    tool: string
    tool_name?: string  // Friendly name from backend mapping
    input: any
    output: string
    status: "success" | "failure" | "running" | "done" | "failed" | "cancelled"
    duration?: number
    type?: "node" | "tool" | "ai" | "skill"
    parent_id?: string | number
}

// A Group is a collection of steps under a header (Phase)
interface StepGroup {
    id: string
    title: string
    status: string // derived from children
    steps: AgentProcessStep[] // The actual steps in this phase
    isImplicit?: boolean // If true, didn't have a header step
}

interface AgentProcessProps {
    steps: AgentProcessStep[]
    isStreaming?: boolean
}

// Tool name mapping for friendly display
const TOOL_ICONS: Record<string, React.ReactNode> = {
    search_web: <Search className="h-3.5 w-3.5" />,
    read_url_content: <Globe className="h-3.5 w-3.5" />,
    scrape_dynamic: <Globe className="h-3.5 w-3.5" />,
    read_file: <FileText className="h-3.5 w-3.5" />,
    grep_files: <Search className="h-3.5 w-3.5" />,
    list_files: <FileText className="h-3.5 w-3.5" />,
    bash_command: <Terminal className="h-3.5 w-3.5" />,
    python_code: <Code className="h-3.5 w-3.5" />,
    route_to: <ExternalLink className="h-3.5 w-3.5" />,
}

// Extract summary from tool output
function summarizeOutput(output: string, tool: string): { summary: string; hasMore: boolean } {
    if (!output) return { summary: "", hasMore: false }

    // Limit output preview length
    const MAX_PREVIEW = 150

    // For search results, extract titles/URLs
    if (tool === "search_web" || tool === "read_url_content") {
        // Try to extract title from "Title: ..." pattern
        const titleMatch = output.match(/Title:\s*(.+?)(?:\n|$)/)
        if (titleMatch) {
            return { summary: titleMatch[1].trim(), hasMore: output.length > MAX_PREVIEW }
        }
        // Try to extract URL
        const urlMatch = output.match(/URL:\s*(.+?)(?:\n|$)/)
        if (urlMatch) {
            return { summary: urlMatch[1].trim(), hasMore: output.length > MAX_PREVIEW }
        }
    }

    // For file operations, show first line or truncated
    const firstLine = output.split('\n')[0].trim()
    if (firstLine.length > MAX_PREVIEW) {
        return { summary: firstLine.slice(0, MAX_PREVIEW) + "...", hasMore: true }
    }
    return { summary: firstLine, hasMore: output.length > firstLine.length }
}

// Grouping logic (borrowed and adapted from ExecutionSteps.tsx)
function groupSteps(steps: AgentProcessStep[], t: any): StepGroup[] {
    const groups: StepGroup[] = []

    const headerMap = new Map<string | number, AgentProcessStep>()
    const childrenMap = new Map<string | number, AgentProcessStep[]>()
    const orphans: AgentProcessStep[] = []

    steps.forEach(step => {
        const parentId = step.parent_id
        const stepId = step.id

        if (parentId != null) {
            if (!childrenMap.has(parentId)) {
                childrenMap.set(parentId, [])
            }
            childrenMap.get(parentId)?.push(step)
        } else {
            // Header or Orphan
            const toolName = step.tool_name || step.tool || ""
            if (toolName.startsWith("►") || step.type === "node") {
                headerMap.set(stepId, step)
            } else {
                orphans.push(step)
            }
        }
    })

    headerMap.forEach((header, id) => {
        const children = childrenMap.get(id) || []
        const toolName = header.tool_name || header.tool || ""

        groups.push({
            id: `g-${header.id}`,
            title: toolName.replace("► ", "").replace("Phase: ", ""),
            status: header.status,
            steps: children,
            isImplicit: false
        })
    })

    if (orphans.length > 0) {
        groups.push({
            id: "g-implicit",
            title: t("chat.steps.execution", "Execution"),
            status: orphans.some(s => s.status === "running") ? "running" : "success",
            steps: orphans,
            isImplicit: true
        })
    }

    // Basic sorting by ID
    groups.sort((a, b) => {
        const getOrder = (g: StepGroup) => {
            if (g.isImplicit && g.steps.length > 0) return Number(g.steps[0].id)
            return Number(g.id.replace("g-", "")) || 999999
        }
        return getOrder(a) - getOrder(b)
    })

    return groups
}

// Compact Step component
function StepRow({ step }: { step: AgentProcessStep }) {
    const { t } = useTranslation()
    const [showDetails, setShowDetails] = useState(false)

    const icon = TOOL_ICONS[step.tool] || <Terminal className="h-3.5 w-3.5" />
    const toolName = step.tool_name || step.tool
    const inputStr = formatInput(step.input, t)
    const { summary, hasMore } = summarizeOutput(step.output, step.tool)

    const isRunning = step.status === "running"
    const isFailed = step.status === "failure" || step.status === "failed"

    return (
        <div className="group relative flex gap-3 py-1.5 px-2 rounded-md hover:bg-muted/30 transition-colors animate-in fade-in slide-in-from-left-1">
            {/* Minimal Icon */}
            <div className="shrink-0 mt-0.5">
                {isRunning ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                ) : isFailed ? (
                    <div className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500/10 text-red-500 text-[10px] font-bold border border-red-500/20">!</div>
                ) : (
                    <div className="text-muted-foreground opacity-70 group-hover:opacity-100 transition-opacity">
                        {icon}
                    </div>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-medium leading-tight ${isRunning ? "text-foreground" : "text-foreground/80"}`}>
                        {toolName}
                    </span>
                    {step.duration && <span className="text-[9px] text-muted-foreground/60">{step.duration}ms</span>}
                </div>

                {/* Input summary */}
                {inputStr && !showDetails && (
                    <div className="text-[10px] text-muted-foreground truncate w-full mt-0.5 opacity-80" title={inputStr}>
                        {inputStr}
                    </div>
                )}

                {/* Output summary */}
                {summary && (
                    <div className="mt-1">
                        {!showDetails ? (
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] text-muted-foreground/70 truncate flex-1 font-mono italic" title={summary}>
                                    {summary}
                                </span>
                                {(hasMore || step.output.length > summary.length) && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-4 px-1 text-[9px] text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                                        onClick={() => setShowDetails(true)}
                                    >
                                        <ChevronRight className="h-2.5 w-2.5 mr-0.5" />
                                        {t("chat.process.show", "详情")}
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <div className="rounded border bg-muted/20 p-2 font-mono text-[10px] text-muted-foreground max-h-[180px] overflow-auto whitespace-pre-wrap w-full min-w-0 break-all shadow-inner">
                                <div className="flex justify-end mb-1">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-4 px-1 text-[9px] text-muted-foreground hover:text-foreground"
                                        onClick={() => setShowDetails(false)}
                                    >
                                        <ChevronDown className="h-2.5 w-2.5 mr-0.5" />
                                        {t("chat.process.hide", "收起")}
                                    </Button>
                                </div>
                                {step.output}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

function ProcessGroup({ group }: { group: StepGroup }) {
    const isRunning = group.status === "running"
    const isFailed = group.status === "failed" || group.status === "failure"

    return (
        <div className="w-full border rounded-lg bg-background/40 overflow-hidden mb-3 shadow-sm border-border/60">
            <div className={`p-2 px-3 flex items-center justify-between border-b border-border/30 ${isRunning ? "bg-primary/5" : ""}`}>
                <div className="flex items-center gap-2 flex-1 w-full">
                    {/* Header Icon */}
                    {isRunning ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                    ) : isFailed ? (
                        <div className="h-3.5 w-3.5 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold shrink-0">!</div>
                    ) : (
                        <div className="h-3.5 w-3.5 flex items-center justify-center rounded-full bg-green-500 text-white shrink-0">
                            <Check className="w-2.5 h-2.5" />
                        </div>
                    )}

                    <span className={`text-[12px] font-bold flex-1 tracking-tight ${isRunning ? "text-primary" : "text-foreground/90"}`}>
                        {group.title}
                    </span>
                </div>
            </div>

            <div className="p-1 px-2 flex flex-col gap-0.5">
                {group.steps.length === 0 && isRunning && (
                    <div className="text-[10px] text-muted-foreground/50 italic px-3 py-2">
                        Initializing Phase...
                    </div>
                )}
                {group.steps.map((step, idx) => (
                    <StepRow key={step.id || idx} step={step} />
                ))}
            </div>
        </div>
    )
}

export function AgentProcess({ steps }: AgentProcessProps) {
    const { t } = useTranslation()
    const groups = groupSteps(steps || [], t)

    if (!steps || steps.length === 0) return null

    return (
        <div className="mt-3 space-y-2 pt-1 animate-in fade-in slide-in-from-bottom-2 duration-300">
            {groups.map(group => (
                <ProcessGroup key={group.id} group={group} />
            ))}
        </div>
    )
}

function formatInput(input: any, t: any): string {
    if (typeof input === 'string') return input
    if (!input) return ""

    // Specific Formatters
    if (input.query) return `${t("chat.process.query", "搜索")}: ${input.query}`
    if (input.path) return `${t("chat.process.path", "路径")}: ${input.path}`
    if (input.start_path) return `${t("chat.process.path", "路径")}: ${input.start_path}`
    if (input.command) return `$ ${input.command}`
    if (input.target) return `${t("chat.process.target", "目标")}: ${input.target}`

    try {
        const str = JSON.stringify(input)
        return str.length > 60 ? str.slice(0, 60) + "..." : str
    } catch {
        return String(input)
    }
}
