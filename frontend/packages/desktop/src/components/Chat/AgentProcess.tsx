import {
    Loader2, ExternalLink, FileText, Search, Terminal, Code, Globe, Database, Wrench,
    FolderOpen, FolderCog, FileEdit, Files, Activity, XCircle, Play, PlayCircle,
    Chrome, Monitor, Smartphone, Locate, CheckCircle, Eye, Brain, History,
    Lightbulb, Sprout, ListTodo, GitBranch, TrendingUp, List, PlusCircle,
    Bookmark, RotateCcw, Trash, BookOpen, PenTool, Wand2, GraduationCap, RefreshCw,
    Image, Server, UserCircle, HelpCircle, Clock, Calendar, Map as MapIcon, BarChart,
    Building, Table, FileType, Clipboard, ClipboardList
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { useState } from "react"

export interface AgentProcessStep {
    id: string | number
    tool: string
    tool_name?: string  // Friendly name from backend mapping (legacy)
    tool_name_display?: string  // Friendly name from backend (new)
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
    steps: any[]
    isStreaming?: boolean
    header?: React.ReactNode
}

// Tool name to icon mapping
const TOOL_ICONS: Record<string, React.ReactNode> = {
    // 文件操作
    read_file: <FileText className="h-3.5 w-3.5" />,
    write_file: <FileText className="h-3.5 w-3.5" />,
    edit_file: <FileEdit className="h-3.5 w-3.5" />,
    apply_patch_file: <FileText className="h-3.5 w-3.5" />,
    multiedit_file: <Files className="h-3.5 w-3.5" />,
    list_directory: <FolderOpen className="h-3.5 w-3.5" />,
    list_files: <FolderOpen className="h-3.5 w-3.5" />,
    manage_directory: <FolderCog className="h-3.5 w-3.5" />,
    search_files: <Search className="h-3.5 w-3.5" />,
    grep_files: <Search className="h-3.5 w-3.5" />,
    
    // 代码执行
    execute_command: <Terminal className="h-3.5 w-3.5" />,
    query_command_status: <Activity className="h-3.5 w-3.5" />,
    cancel_command: <XCircle className="h-3.5 w-3.5" />,
    bash_command: <Terminal className="h-3.5 w-3.5" />,
    python_code: <Code className="h-3.5 w-3.5" />,
    run_macro: <Play className="h-3.5 w-3.5" />,
    
    // 网络/搜索
    search_web: <Search className="h-3.5 w-3.5" />,
    read_url_content: <Globe className="h-3.5 w-3.5" />,
    scrape_dynamic: <Globe className="h-3.5 w-3.5" />,
    browser_control: <Chrome className="h-3.5 w-3.5" />,
    
    // 设备控制
    desktop_control: <Monitor className="h-3.5 w-3.5" />,
    mobile_control: <Smartphone className="h-3.5 w-3.5" />,
    find_element: <Locate className="h-3.5 w-3.5" />,
    verify_ui_state: <CheckCircle className="h-3.5 w-3.5" />,
    quick_check_screen: <Eye className="h-3.5 w-3.5" />,
    
    // 知识/记忆
    remember: <Brain className="h-3.5 w-3.5" />,
    recall: <Brain className="h-3.5 w-3.5" />,
    search_history: <History className="h-3.5 w-3.5" />,
    save_concepts: <Lightbulb className="h-3.5 w-3.5" />,
    auto_harvest_knowledge: <Sprout className="h-3.5 w-3.5" />,
    
    // 项目/任务
    create_hierarchical_task: <ListTodo className="h-3.5 w-3.5" />,
    get_task_tree: <GitBranch className="h-3.5 w-3.5" />,
    update_task_progress: <TrendingUp className="h-3.5 w-3.5" />,
    get_next_executable_task: <PlayCircle className="h-3.5 w-3.5" />,
    list_project_tasks: <List className="h-3.5 w-3.5" />,
    create_project_task: <PlusCircle className="h-3.5 w-3.5" />,
    
    // 检查点
    create_checkpoint: <Bookmark className="h-3.5 w-3.5" />,
    list_checkpoints: <Bookmark className="h-3.5 w-3.5" />,
    rollback_checkpoint: <RotateCcw className="h-3.5 w-3.5" />,
    delete_checkpoint: <Trash className="h-3.5 w-3.5" />,
    
    // Wiki
    list_wiki_pages: <BookOpen className="h-3.5 w-3.5" />,
    read_wiki_page: <BookOpen className="h-3.5 w-3.5" />,
    write_wiki_page: <PenTool className="h-3.5 w-3.5" />,
    
    // 学习/技能
    search_skills: <Wand2 className="h-3.5 w-3.5" />,
    learn_skill_from_trace: <GraduationCap className="h-3.5 w-3.5" />,
    reconcile_skill: <RefreshCw className="h-3.5 w-3.5" />,
    search_native_tools: <Search className="h-3.5 w-3.5" />,
    
    // 其他
    analyze_image: <Image className="h-3.5 w-3.5" />,
    use_mcp_server: <Server className="h-3.5 w-3.5" />,
    ask_human: <UserCircle className="h-3.5 w-3.5" />,
    ask_confirm: <HelpCircle className="h-3.5 w-3.5" />,
    wait_for: <Clock className="h-3.5 w-3.5" />,
    route_to: <ExternalLink className="h-3.5 w-3.5" />,
    memory: <Database className="h-3.5 w-3.5" />,
    task_boundary: <Wrench className="h-3.5 w-3.5" />,
    delegate_periodic_intent: <Calendar className="h-3.5 w-3.5" />,
    inspect_task_health: <Activity className="h-3.5 w-3.5" />,
    list_autonomous_tasks: <List className="h-3.5 w-3.5" />,
    query_app_atlas: <MapIcon className="h-3.5 w-3.5" />,
    list_app_atlas: <MapIcon className="h-3.5 w-3.5" />,
    get_app_usage_ranker: <BarChart className="h-3.5 w-3.5" />,
    consult_architecture: <Building className="h-3.5 w-3.5" />,
    query_excel: <Table className="h-3.5 w-3.5" />,
    document_reader: <FileType className="h-3.5 w-3.5" />,
    stash_to_clipboard: <Clipboard className="h-3.5 w-3.5" />,
    retrieve_from_clipboard: <ClipboardList className="h-3.5 w-3.5" />,
    create_python_tool: <Code className="h-3.5 w-3.5" />,
}

// Tool name to friendly display name mapping
const TOOL_NAMES: Record<string, string> = {
    read_file: "读取分析",
    write_file: "写入文件",
    edit_file: "编辑文件",
    apply_patch_file: "应用补丁",
    multiedit_file: "批量编辑",
    list_directory: "扫描目录",
    list_files: "查找文件",
    grep_files: "搜索代码",
    execute_command: "执行命令",
    query_command_status: "查询命令状态",
    cancel_command: "取消命令",
    bash_command: "运行命令",
    python_code: "执行脚本",
    run_macro: "执行宏",
    search_web: "检索网络",
    read_url_content: "读取网页",
    scrape_dynamic: "动态抓取",
    browser_control: "浏览器控制",
    
    // 设备控制
    desktop_control: "桌面控制",
    mobile_control: "移动设备控制",
    find_element: "查找元素",
    verify_ui_state: "验证UI状态",
    quick_check_screen: "快速检查屏幕",
    
    // 知识/记忆
    remember: "记住",
    recall: "回忆",
    search_history: "搜索历史",
    save_concepts: "保存概念",
    auto_harvest_knowledge: "自动收获知识",
    
    // 项目/任务
    create_hierarchical_task: "创建层级任务",
    get_task_tree: "获取任务树",
    update_task_progress: "更新任务进度",
    get_next_executable_task: "获取待执行任务",
    list_project_tasks: "列出项目任务",
    create_project_task: "创建项目任务",
    
    // 检查点
    create_checkpoint: "创建检查点",
    list_checkpoints: "列出检查点",
    rollback_checkpoint: "回滚检查点",
    delete_checkpoint: "删除检查点",
    
    // Wiki
    list_wiki_pages: "列出Wiki页面",
    read_wiki_page: "读取Wiki页面",
    write_wiki_page: "写入Wiki页面",
    
    // 学习/技能
    search_skills: "搜索技能",
    learn_skill_from_trace: "从轨迹学习",
    reconcile_skill: "调和技能",
    search_native_tools: "搜索原生工具",
    
    // 其他
    analyze_image: "分析图像",
    use_mcp_server: "使用MCP服务器",
    ask_human: "询问用户",
    ask_confirm: "确认操作",
    wait_for: "等待",
    route_to: "路由请求",
    memory: "记忆操作",
    task_boundary: "任务边界",
    delegate_periodic_intent: "委托周期性意图",
    inspect_task_health: "检查任务健康",
    list_autonomous_tasks: "列出自主任务",
    query_app_atlas: "查询应用图谱",
    list_app_atlas: "列出应用图谱",
    get_app_usage_ranker: "获取应用使用排名",
    consult_architecture: "架构咨询",
    query_excel: "查询Excel",
    document_reader: "读取文档",
    stash_to_clipboard: "暂存到剪贴板",
    retrieve_from_clipboard: "从剪贴板检索",
    create_python_tool: "创建Python工具",
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
        const toolType = step.tool || step.name?.replace("Using ", "") || "unknown"

        // Filter out noisy internal steps that don't have user-facing value
        // Match both raw names and localized Chinese descriptions from snapshots
        const noisePatterns = [
            "route_to", "list_directory", "list_files", "read_file", "inspect_task_health",
            "正在列出", "正在读取", "扫描目录", "查找文件", "读取分析"
        ]
        
        const isInternal = step.type === "internal" || toolType === "route_to" || displayName.includes("route_to")
        const isNoise = noisePatterns.some(p => displayName.includes(p) || toolType.includes(p))

        if (isInternal || isNoise) {
            return
        }

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

    // Aggregation logic: group consecutive similar tool steps
    const aggregateSteps = (rawSteps: any[]) => {
        const result: any[] = []
        rawSteps.forEach(step => {
            const prev = result[result.length - 1]
            const type = step.tool || step.name
            
            // Only aggregate certain boring tools
            const canAggregate = ['read_file', 'list_files', 'list_directory'].includes(type)
            const isFinished = (s: any) => s.status === 'done' || s.status === 'success'
            
            if (prev && canAggregate && (prev.tool || prev.name) === type && isFinished(prev) && isFinished(step)) {
                if (!prev.items) prev.items = [prev]
                prev.items.push(step)
                prev.id = step.id // update to latest
                return
            }
            result.push({ ...step })
        })
        return result
    }

    headerMap.forEach((header, id) => {
        const children = childrenMap.get(id) || []
        const displayName = header.tool_name || header.tool || header.name || ""

        groups.push({
            id: `g-${header.id}`,
            title: displayName.replace("► ", "").replace("Phase: ", ""),
            status: header.status,
            steps: aggregateSteps(children),
            isImplicit: false
        })
    })

    if (orphans.length > 0) {
        groups.push({
            id: "g-implicit",
            title: t("chat.steps.execution"),
            status: orphans.some(s => s.status === "running") ? "running" : "success",
            steps: aggregateSteps(orphans),
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
        tool_name_display: step.tool_name_display,
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
    
    // Priority: 1. Backend friendly name (tool_name_display) 2. Legacy tool_name 3. Frontend mapping 4. Raw tool name
    let toolName = step.tool_name_display || step.tool_name || TOOL_NAMES[step.tool] || step.tool || t("chat.steps.unknown", "未知工具")

    // Optimization: Fallback to raw tool ID if 'unknown' and we have a tool ID
    if ((toolName === "unknown" || toolName === t("chat.steps.unknown")) && step.tool && step.tool !== "unknown") {
        toolName = step.tool
    }

    // Handle nested translation keys if they leak from backend
    if (typeof toolName === 'string' && toolName.includes("database_logger.")) {
        toolName = t("chat.steps.executingCommand", "正在执行命令")
    }
    
    // Aggregated row
    if ((step as any).items) {
        const count = (step as any).items.length
        return (
            <div className="group flex items-center gap-1.5 py-1 px-3 text-[10px] text-muted-foreground/60 transition-colors">
                <div className="flex h-4 w-4 shrink-0 items-center justify-center opacity-40">
                    <ClipboardList className="h-3 w-3" />
                </div>
                <div className="truncate">
                    {t("chat.steps.batchAction", "批量执行")} {toolName} · {count} {t("chat.steps.actions", "个动作")}
                </div>
            </div>
        )
    }

    const inputInfo = formatToolInput(step.tool, step.input, t)
    const outputSummary = summarizeOutput(step.tool, step.output)
    
    // For read_file tool, append the file path to the tool name
    if (step.tool === 'read_file' && inputInfo?.value) {
        toolName = `${toolName}: ${inputInfo.value}`
    }

    const isRunning = step.status === "running"
    const isFailed = step.status === "failure" || step.status === "failed"
    // Only check for explicit JSON error status, not simple string inclusion
    // to avoid false positives from normal output containing "error" (e.g., error/ directory)
    const hasError = step.output?.includes('"status":"error"')

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
                            {hasError && <span className="text-red-500 mr-1">{t("chat.steps.failed")}:</span>}
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

    // Logic: If historical (no header/streaming) and steps > 5, collapse
    const MAX_VISIBLE_STEPS = 5
    const isHistorical = !header
    const shouldCollapse = isHistorical && steps.length > MAX_VISIBLE_STEPS && !isFullyExpanded
    
    const visibleGroups = shouldCollapse 
        ? groups.slice(0, 1).map(g => ({...g, steps: g.steps.slice(0, MAX_VISIBLE_STEPS)}))
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
                    {t("chat.steps.showMore", "查看更多执行步骤")} ({steps.length - MAX_VISIBLE_STEPS}+)
                </Button>
            )}
        </div>
    )
}
