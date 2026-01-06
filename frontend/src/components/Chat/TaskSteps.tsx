import { useState, useMemo, memo, useEffect } from "react"
import { CheckCircle2, Loader2, XCircle, Terminal, Cpu, ChevronDown, ChevronRight, LayoutList } from "lucide-react"

export interface TaskItem {
    id: number
    name: string
    status: "running" | "done" | "failed" | "cancelled"
    type: "node" | "tool" | "ai"
    time: string
    details?: string
}

interface TreeTask extends TaskItem {
    children: TreeTask[]
}

interface TaskStepsProps {
    tasks: TaskItem[]
}

// Helper to build hierarchy based on naming conventions
function buildTaskTree(tasks: TaskItem[]): TreeTask[] {
    const root: TreeTask[] = []
    const stack: { list: TreeTask[], parentName?: string }[] = [{ list: root }]

    // Regex to detect scope entry/exit (supporting optional brackets)
    const RE_ENTER = /^Entering (?:\[(.+)\]|(.+))/
    const RE_EXIT = /^Exiting (?:\[(.+)\]|(.+))/

    tasks.forEach(task => {
        const currentLevel = stack[stack.length - 1].list
        const treeNode: TreeTask = { ...task, children: [] }

        // Check for Entry
        const enterMatch = task.name.match(RE_ENTER)
        const exitMatch = task.name.match(RE_EXIT)

        if (enterMatch) {
            // New Scope
            currentLevel.push(treeNode)
            stack.push({ list: treeNode.children, parentName: enterMatch[1] || enterMatch[2] })
        } else if (exitMatch) {
            // Close Scope (add this task to current, then pop)
            currentLevel.push(treeNode)
            if (stack.length > 1) {
                stack.pop()
            }
        } else {
            // Normal task
            currentLevel.push(treeNode)
        }
    })

    return root
}

// Helper to check if any child (recursively) is running
const isAnyChildRunning = (node: TreeTask): boolean => {
    return node.children.some(c => c.status === 'running' || isAnyChildRunning(c));
}

const TaskNode = memo(({ node, depth = 0 }: { node: TreeTask, depth?: number }) => {
    const isFolder = node.children.length > 0
    const hasRunningChild = useMemo(() => isAnyChildRunning(node), [node])
    const [isOpen, setIsOpen] = useState(node.status === 'running' || hasRunningChild)

    // Sync open state with status: Auto-expand when running, Auto-collapse when done
    useEffect(() => {
        setIsOpen(node.status === 'running' || hasRunningChild)
    }, [node.status, hasRunningChild])

    // Adjust visual style for folders vs atomic tasks
    const isScopeNode = /^Entering|Exiting/.test(node.name)

    // Simplification: Don't render "Exiting", just "Entering" as the container
    if (node.name.startsWith("Exiting")) return null

    return (
        <div className="flex flex-col animate-in fade-in duration-300">
            <div
                className={`
                    flex items-start gap-3 p-2 rounded-lg text-sm font-mono transition-colors
                    ${depth > 0 ? 'ml-3 border-l-2 border-muted pl-3' : ''}
                    ${isScopeNode ? 'bg-muted/30 font-semibold' : 'bg-muted/10'}
                `}
            >
                {/* Status Icon */}
                <div className="mt-0.5 shrink-0">
                    {node.status === 'running' && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
                    {node.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                    {(node.status === 'failed' || node.status === 'cancelled') && <XCircle className="w-4 h-4 text-destructive" />}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                    <div
                        className="flex items-center gap-2 cursor-pointer select-none"
                        onClick={() => isFolder && setIsOpen(!isOpen)}
                    >
                        {isFolder && (
                            <span className="text-muted-foreground mr-1">
                                {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                            </span>
                        )}

                        {/* Type Icon */}
                        {node.type === 'tool' && <Terminal className="w-3 h-3 text-muted-foreground" />}
                        {node.type === 'ai' && <Cpu className="w-3 h-3 text-muted-foreground" />}
                        {isScopeNode && <LayoutList className="w-3 h-3 text-primary" />}

                        <span className={`truncate ${node.status === 'running' ? 'text-foreground' : 'text-muted-foreground'}`}>
                            {node.name.replace(/^Entering /, '')}
                        </span>
                    </div>

                    {/* Details (only for leaf nodes usually) */}
                    {node.details && !isFolder && !(node.type === 'ai' && node.status === 'running') && (
                        <div className="text-xs text-muted-foreground pl-5 pt-1 break-words whitespace-pre-wrap opacity-80 line-clamp-4">
                            {node.details}
                        </div>
                    )}
                </div>

                {/* Time */}
                {node.time && (
                    <div className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                        {node.time}
                    </div>
                )}
            </div>

            {/* Children */}
            {isFolder && isOpen && (
                <div className="flex flex-col mt-1">
                    {node.children.map(child => (
                        <TaskNode key={child.id} node={child} depth={depth + 1} />
                    ))}
                </div>
            )}
        </div>
    )
})
TaskNode.displayName = "TaskNode"

// TaskSteps.displayName = "TaskSteps"

export function TaskSteps({ tasks }: TaskStepsProps) {
    const taskTree = useMemo(() => buildTaskTree(tasks || []), [tasks])

    if (!tasks || tasks.length === 0) return null

    // For now, removing the "Collapsed Summary" feature for tree view as it complicates things.
    // We can re-introduce it if needed by checking root nodes.

    return (
        <div className="flex flex-col gap-2 w-full max-w-[90%]">
            {taskTree.map((node) => (
                <TaskNode key={node.id} node={node} />
            ))}
        </div>
    )
}
