
import { CheckCircle2, Loader2, XCircle, Terminal, Cpu } from "lucide-react"

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
    if (!tasks || tasks.length === 0) return null

    return (
        <div className="flex flex-col gap-2 w-full max-w-[80%]">
            {tasks.map((task) => (
                <div
                    key={task.id}
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
            ))}
        </div>
    )
}
