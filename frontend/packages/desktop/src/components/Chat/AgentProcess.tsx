import { Loader2, ExternalLink, FileText, Search, Terminal, Code, Globe, Database, Wrench } from "lucide-react"
import { useTranslation } from "react-i18next"

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

// A Group is a collection of steps under a header
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
    header?: React.ReactNode
}

// Tool name to icon mapping
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
    memory: <Database className="h-3.5 w-3.5" />,
    task_boundary: <Wrench className="h-3.5 w-3.5" />,
}

// Tool name to friendly display name mapping
const TOOL_NAMES: Record<string, string> = {
    search_web: "搜索网页",
    read_url_content: "读取网页",
    scrape_dynamic: "动态抓取",
    read_file: "读取文件",
    grep_files: "搜索文件内容",
    list_files: "列出文件",
    bash_command: "执行命令",
    python_code: "执行代码",
    route_to: "路由请求",
    memory: "记忆操作",
    task_boundary: "任务边界",
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

// Format tool input in a user-friendly way
function formatToolInput(tool: string, input: any, t: any): { label: string; value: string } | null {
    if (!input) return null

    // Handle string input (try to parse as JSON)
    let data = input
    if (typeof input === 'string') {
        data = safeJsonParse(input) || input
    }

    if (typeof data === 'string') {
        return { label: t("chat.process.param", "参数"), value: data }
    }

    // Tool-specific formatting
    switch (tool) {
        case 'search_web':
            if (data.query) return { label: t("chat.process.query", "搜索"), value: data.query }
            break
        case 'read_url_content':
        case 'scrape_dynamic':
            if (data.url) return { label: "URL", value: data.url }
            break
        case 'read_file':
        case 'grep_files':
        case 'list_files':
            if (data.path) return { label: t("chat.process.path", "路径"), value: data.path }
            if (data.file_path) return { label: t("chat.process.path", "路径"), value: data.file_path }
            if (data.start_path) return { label: t("chat.process.path", "路径"), value: data.start_path }
            break
        case 'bash_command':
            if (data.command) return { label: "$", value: data.command }
            break
        case 'python_code':
            if (data.code) {
                const firstLine = data.code.split('\n')[0].trim()
                return { label: "python", value: firstLine + (data.code.includes('\n') ? '...' : '') }
            }
            break
        case 'route_to':
            if (data.target) return { label: t("chat.process.target", "目标"), value: data.target }
            break
        case 'memory':
            const action = data.action || 'get'
            const key = data.key || data.query || data.name || ''
            return { label: action, value: key }
    }

    // Generic fallback - show first meaningful field
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
function parseToolOutput(tool: string, output: string): { type: 'text' | 'json' | 'list' | 'error'; data: any } {
    if (!output) return { type: 'text', data: '' }

    // Try to parse as JSON
    const jsonData = safeJsonParse(output)
    if (jsonData) {
        if (Array.isArray(jsonData)) {
            return { type: 'list', data: jsonData }
        }
        if (typeof jsonData === 'object') {
            // Check for error
            if (jsonData.error || jsonData.status === 'error') {
                return { type: 'error', data: jsonData.error || jsonData.message || output }
            }
            return { type: 'json', data: jsonData }
        }
    }

    return { type: 'text', data: output }
}

// Extract human-readable summary from tool output
function summarizeOutput(tool: string, output: string): { title: string; subtitle?: string; hasMore: boolean } {
    if (!output) return { title: "", hasMore: false }

    const MAX_LENGTH = 120
    const parsed = parseToolOutput(tool, output)

    // Handle error
    if (parsed.type === 'error') {
        const errorMsg = typeof parsed.data === 'string' ? parsed.data : JSON.stringify(parsed.data)
        return { 
            title: errorMsg.length > MAX_LENGTH ? errorMsg.slice(0, MAX_LENGTH) + "..." : errorMsg,
            hasMore: errorMsg.length > MAX_LENGTH
        }
    }

    // Handle list data
    if (parsed.type === 'list' && Array.isArray(parsed.data)) {
        const count = parsed.data.length
        if (count === 0) return { title: "无结果", hasMore: false }
        
        // Try to get first item description
        const firstItem = parsed.data[0]
        if (typeof firstItem === 'string') {
            return { title: `${count} 项结果`, subtitle: firstItem.slice(0, 50), hasMore: true }
        }
        if (typeof firstItem === 'object' && firstItem !== null) {
            const title = firstItem.title || firstItem.name || firstItem.path || firstItem.url || ''
            return { title: `${count} 项结果`, subtitle: title.slice(0, 50), hasMore: true }
        }
        return { title: `${count} 项结果`, hasMore: true }
    }

    // Handle JSON object
    if (parsed.type === 'json' && typeof parsed.data === 'object') {
        const data = parsed.data
        
        // Search results
        if (tool === 'search_web' || tool === 'read_url_content') {
            if (data.title) return { title: data.title, subtitle: data.url || data.description, hasMore: true }
            if (data.url) return { title: data.url, hasMore: true }
        }

        // File operations
        if (tool === 'read_file' || tool === 'grep_files') {
            if (data.content) {
                const firstLine = String(data.content).split('\n')[0].trim()
                return { title: firstLine.slice(0, MAX_LENGTH), hasMore: String(data.content).length > firstLine.length }
            }
            if (data.matches && Array.isArray(data.matches)) {
                return { title: `${data.matches.length} 个匹配`, hasMore: true }
            }
        }

        // Generic - try to find a meaningful field
        const priorityFields = ['message', 'result', 'content', 'summary', 'status', 'name', 'title']
        for (const field of priorityFields) {
            if (data[field]) {
                const val = String(data[field])
                return { title: val.slice(0, MAX_LENGTH), hasMore: val.length > MAX_LENGTH }
            }
        }

        // Fallback to stringified JSON (first line)
        const str = JSON.stringify(data)
        return { title: str.slice(0, MAX_LENGTH), hasMore: str.length > MAX_LENGTH }
    }

    // Plain text
    const firstLine = output.split('\n')[0].trim()
    return { 
        title: firstLine.slice(0, MAX_LENGTH), 
        hasMore: output.length > firstLine.length || output.split('\n').length > 1
    }
}

// Grouping logic
function groupSteps(steps: any[], t: any): StepGroup[] {
    const groups: StepGroup[] = []

    const headerMap = new Map<string | number, any>()
    const childrenMap = new Map<string | number, any[]>()
    const orphans: any[] = []

    steps.forEach(step => {
        const parentId = step.parent_id
        const stepId = step.id
        
        // Handle both formats: AgentProcessStep (tool/tool_name) and StepItem (name)
        const displayName = step.tool_name || step.tool || step.name || ""

        if (parentId != null) {
            if (!childrenMap.has(parentId)) {
                childrenMap.set(parentId, [])
            }
            childrenMap.get(parentId)?.push(step)
        } else {
            if (displayName.startsWith("►") || step.type === "node") {
                headerMap.set(stepId, step)
            } else {
                orphans.push(step)
            }
        }
    })

    headerMap.forEach((header, id) => {
        const children = childrenMap.get(id) || []
        const displayName = header.tool_name || header.tool || header.name || ""

        groups.push({
            id: `g-${header.id}`,
            title: displayName.replace("► ", "").replace("Phase: ", ""),
            status: header.status,
            steps: children,
            isImplicit: false
        })
    })

    if (orphans.length > 0) {
        groups.push({
            id: "g-implicit",
            title: t("chat.steps.execution", "执行"),
            status: orphans.some(s => s.status === "running") ? "running" : "success",
            steps: orphans,
            isImplicit: true
        })
    }

    groups.sort((a, b) => {
        const getOrder = (g: StepGroup) => {
            if (g.isImplicit && g.steps.length > 0) return Number(g.steps[0].id)
            return Number(g.id.replace("g-", "")) || 999999
        }
        return getOrder(a) - getOrder(b)
    })

    return groups
}

// Normalize step data to handle both AgentProcessStep and StepItem formats
function normalizeStep(step: any): AgentProcessStep {
    // If step has 'name' but not 'tool', it's StepItem format
    const tool = step.tool || step.name?.replace(/^Using\s+/, '') || 'unknown'
    // If step has 'details' but not 'output', it's StepItem format  
    const output = step.output !== undefined ? step.output : (step.details || '')
    // If step has 'time' (string) but not 'duration' (number), convert it
    let duration = step.duration
    if (duration === undefined && step.time) {
        const parsed = parseFloat(step.time)
        if (!isNaN(parsed)) {
            duration = parsed < 1000 ? parsed * 1000 : parsed // Convert seconds to ms if small
        }
    }
    
    return {
        id: step.id,
        tool,
        tool_name: step.tool_name || step.name,
        input: step.input,
        output,
        status: step.status || 'running',
        duration,
        type: step.type,
        parent_id: step.parent_id,
    }
}

// Compact Step component
function StepRow({ step: rawStep }: { step: AgentProcessStep }) {
    const { t } = useTranslation()
    
    // Normalize step to handle both formats
    const step = normalizeStep(rawStep)

    const icon = TOOL_ICONS[step.tool] || <Terminal className="h-3.5 w-3.5" />
    const toolName = TOOL_NAMES[step.tool] || step.tool_name || step.tool
    const inputInfo = formatToolInput(step.tool, step.input, t)
    const outputSummary = summarizeOutput(step.tool, step.output)

    const isRunning = step.status === "running"
    const isFailed = step.status === "failure" || step.status === "failed"
    const hasError = step.output?.toLowerCase().includes('error') || step.output?.includes('"status":"error"')

    return (
        <div className="group relative flex gap-2 py-2 px-2 rounded-md hover:bg-muted/30 transition-colors animate-in fade-in slide-in-from-left-1">
            {/* Icon */}
            <div className="shrink-0 mt-0.5 text-muted-foreground">
                {isRunning ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                ) : isFailed || hasError ? (
                    <div className="h-3.5 w-3.5 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold">!</div>
                ) : (
                    <div className="opacity-70 group-hover:opacity-100 transition-opacity">{icon}</div>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
                {/* Tool name */}
                <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-medium leading-tight ${isRunning ? "text-foreground" : "text-foreground/80"}`}>
                        {toolName}
                    </span>
                    {step.duration && (
                        <span className="text-[9px] text-muted-foreground/60">{step.duration}ms</span>
                    )}
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
                            {hasError && <span className="text-red-500 mr-1">{t("chat.steps.failed", "失败")}:</span>}
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
                        {t("chat.process.initializing", "初始化中...")}
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

    if (!steps || steps.length === 0) return null

    return (
        <div className="w-full min-w-0 border rounded bg-muted/20 overflow-hidden border-border/40">
            {header && (
                <div className="border-b border-border/30">
                    {header}
                </div>
            )}
            <div className="p-1 px-2 flex flex-col gap-0.5 animate-in fade-in slide-in-from-bottom-2 duration-300">
                {groups.map(group => (
                    <ProcessGroup key={group.id} group={group} />
                ))}
            </div>
        </div>
    )
}
