import { useState } from "react"
import { CheckCircle2, Loader2, XCircle, Terminal, Cpu, ChevronDown, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"

export interface TaskItem {
    id: number
    name: string
    status: "running" | "done" | "failed" | "cancelled"
    type: "node" | "tool" | "ai"
    time: string
    details?: string
}

interface TaskStepsProps {
    tasks: TaskItem[]
}

export function TaskSteps({ tasks }: TaskStepsProps) {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(false)

    if (!tasks || tasks.length === 0) return null

    // Filter logic
    const doneTasks = tasks.filter(t => t.status === 'done')
    const activeTasks = tasks.filter(t => t.status !== 'done') // running, failed, cancelled

    let visibleTasks: TaskItem[] = tasks
    let collapsedCount = 0

    // Auto-collapse logic:
    // If not expanded, and we have multiple completed tasks:
    // Show only the LAST completed task + All active tasks
    if (!isExpanded && doneTasks.length > 1) {
        collapsedCount = doneTasks.length - 1
        const lastDone = doneTasks[doneTasks.length - 1]
        visibleTasks = [lastDone, ...activeTasks]
    }

    const TaskRow = ({ task }: { task: TaskItem }) => (
        <div
            className="flex items-start gap-3 p-2 rounded-lg bg-muted/40 text-sm font-mono animate-in fade-in slide-in-from-left-2 duration-300"
        >
            <div className="mt-0.5 shrink-0">
                {task.status === 'running' && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
                {task.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                {(task.status === 'failed' || task.status === 'cancelled') && <XCircle className="w-4 h-4 text-destructive" />}
            </div>

            <div className="flex-1 space-y-1 min-w-0">
                <div className="flex items-center gap-2">
                    {/* Icon based on type */}
                    {task.type === 'tool' && <Terminal className="w-3 h-3 text-muted-foreground" />}
                    {task.type === 'ai' && <Cpu className="w-3 h-3 text-muted-foreground" />}
                    <span className={`truncate font-medium ${task.status === 'running' ? 'text-foreground' : 'text-muted-foreground'}`}>
                        {task.name}
                    </span>
                </div>
                {task.details && (
                    <div className="text-xs text-muted-foreground pl-5 break-words whitespace-pre-wrap opacity-80 line-clamp-3">
                        {task.details}
                    </div>
                )}
            </div>

            {task.time && (
                <div className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                    {task.time}
                </div>
            )}
        </div>
    )

    return (
        <div className="flex flex-col gap-2 w-full max-w-[80%]">
            {/* Collapsed Summary */}
            {collapsedCount > 0 && !isExpanded && (
                <div
                    onClick={() => setIsExpanded(true)}
                    className="flex items-center gap-2 p-2 rounded-lg bg-muted/20 text-xs text-muted-foreground cursor-pointer hover:bg-muted/40 transition-colors select-none"
                >
                    <ChevronRight className="w-3 h-3" />
                    <CheckCircle2 className="w-3 h-3 opacity-50" />
                    <span>{t('chat.steps.collapsedSummary', { count: collapsedCount })}</span>
                </div>
            )}

            {/* Expanded Header (Optional, allows collapsing back) */}
            {isExpanded && doneTasks.length > 1 && (
                <div
                    onClick={() => setIsExpanded(false)}
                    className="flex items-center gap-2 p-2 rounded-lg bg-muted/20 text-xs text-muted-foreground cursor-pointer hover:bg-muted/40 transition-colors select-none mb-1"
                >
                    <ChevronDown className="w-3 h-3" />
                    <span>{t('chat.steps.hideHistory')}</span>
                </div>
            )}

            {visibleTasks.map((task) => (
                <TaskRow key={task.id} task={task} />
            ))}
        </div>
    )
}
