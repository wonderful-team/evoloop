import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Loader2,
  Sparkles,
  Terminal,
  XCircle,
} from "lucide-react"
import { memo, useEffect, useMemo, useState } from "react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"

export interface TaskItem {
  id: number
  name: string
  status: "running" | "done" | "failed" | "cancelled"
  type: "node" | "tool" | "ai" | "skill"
  time: string
  details?: string
}

// A Group is a collection of tasks under a header (Phase)
interface TaskGroup {
  id: string
  title: string
  status: string // derived from children (running if any running, done if all done)
  tasks: TaskItem[] // The actual steps in this phase
  isImplicit?: boolean // If true, didn't have a header task
}

interface TaskStepsProps {
  tasks: TaskItem[]
}

// New Helper: Group flat list into Phases
function groupTasks(tasks: TaskItem[]): TaskGroup[] {
  const groups: TaskGroup[] = []
  let currentGroup: TaskGroup | null = null

  tasks.forEach((task) => {
    // 1. Is this a Phase Header? (Type='node' or name like "► ...")
    // We treating 'node' type as phase headers now based on backend change
    const isHeader = task.type === "node" || task.name.startsWith("►")

    if (isHeader) {
      // Start new group
      currentGroup = {
        id: `g-${task.id}`,
        title: task.name.replace("► ", "").replace("Phase: ", ""), // Clean up
        status: task.status, // Initially use header status
        tasks: [],
      }
      groups.push(currentGroup)
    } else {
      // It's a step (tool/thought)
      if (!currentGroup) {
        // Create implicit group if none exists
        currentGroup = {
          id: "g-start",
          title: "Execution",
          status: "running",
          tasks: [],
          isImplicit: true,
        }
        groups.push(currentGroup)
      }

      // Add to current group
      currentGroup.tasks.push(task)

      // Update Group Status: if ANY child is running, group is running
      if (task.status === "running") {
        currentGroup.status = "running"
      } else if (task.status === "failed") {
        currentGroup.status = "failed"
      }
    }
  })

  // Final Pass: Logic consistency
  // If a group has no running tasks, but header is running, it's running.
  // If header is done, but has running tasks? (Shouldn happen in linear log).

  return groups
}

const TaskNodeItem = memo(({ task }: { task: TaskItem }) => {
  return (
    <div className="flex items-start gap-3 p-2 rounded-lg text-sm font-mono bg-muted/10 ml-2 border-l border-muted pl-3 hover:bg-muted/20 transition-colors animate-in fade-in slide-in-from-left-2">
      {/* Status Icon */}
      <div className="mt-0.5 shrink-0">
        {task.status === "running" && (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
        )}
        {task.status === "done" && (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
        )}
        {(task.status === "failed" || task.status === "cancelled") && (
          <XCircle className="w-3.5 h-3.5 text-destructive" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Type Icon */}
          {task.type === "skill" && (
            <Sparkles className="w-3 h-3 text-amber-500" />
          )}
          {task.type === "tool" && (
            <Terminal className="w-3 h-3 text-muted-foreground" />
          )}
          {task.type === "ai" && (
            <Cpu className="w-3 h-3 text-muted-foreground" />
          )}

          <span className={`truncate ${task.status === "running" ? "text-foreground" : "text-muted-foreground"}`}>
            {task.name}
          </span>
        </div>

        {/* Details */}
        {task.details && !(task.type === "ai" && task.status === "running") && (
          <div className="text-xs text-muted-foreground pl-5 pt-1 break-words whitespace-pre-wrap opacity-80 line-clamp-4">
            {task.details}
          </div>
        )}
      </div>

      {/* Time */}
      {task.time && (
        <div className="text-[10px] text-muted-foreground shrink-0 mt-0.5 opacity-50">
          {task.time}
        </div>
      )}
    </div>
  )
})
TaskNodeItem.displayName = "TaskNodeItem"

const TaskGroupItem = memo(({ group }: { group: TaskGroup }) => {
  // Auto-Folding Logic:
  // Open if status is 'running' OR it's the very last group (often active).
  // Closed if status is 'done'.
  const [isOpen, setIsOpen] = useState(group.status === "running")

  useEffect(() => {
    setIsOpen(group.status === "running")
  }, [group.status])

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className="w-full border rounded-lg bg-background/50 overflow-hidden mb-2 shadow-sm"
    >
      <div className={`p-2 px-3 flex items-center justify-between cursor-pointer hover:bg-muted/50 transition-colors ${group.status === "running" ? "bg-primary/5" : ""}`}>
        <CollapsibleTrigger asChild>
          <div className="flex items-center gap-2 flex-1 w-full">
            {/* Header Icon */}
            {group.status === "running" ? (
              <Loader2 className="w-4 h-4 animate-spin text-primary shrink-0" />
            ) : group.status === "failed" ? (
              <XCircle className="w-4 h-4 text-destructive shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
            )}

            <span className={`text-sm font-semibold flex-1 ${group.status === "running" ? "text-primary" : "text-foreground"}`}>
              {group.title}
            </span>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {group.tasks.length} steps
              </span>
              {isOpen ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
            </div>
          </div>
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent>
        <div className="p-2 pt-0 flex flex-col gap-1 mt-1">
          {group.tasks.length === 0 && (
            <div className="text-xs text-muted-foreground italic pl-8 py-2">
              Initializing phase...
            </div>
          )}
          {group.tasks.map(task => (
            <TaskNodeItem key={task.id} task={task} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})
TaskGroupItem.displayName = "TaskGroupItem"


export function TaskSteps({ tasks }: TaskStepsProps) {
  const groups = useMemo(() => groupTasks(tasks || []), [tasks])

  if (!tasks || tasks.length === 0) return null

  return (
    <div className="flex flex-col gap-1 w-full max-w-[95%] animate-in fade-in">
      {groups.map(group => (
        <TaskGroupItem key={group.id} group={group} />
      ))}
    </div>
  )
}
