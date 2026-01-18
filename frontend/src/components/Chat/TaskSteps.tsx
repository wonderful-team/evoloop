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
  parent_id?: number // Phase 18: Link to phase
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

import { useTranslation } from "react-i18next"

// Replaces legacy assumption-based grouping with direct parent_id hierarchy
function groupTasks(tasks: TaskItem[], t: any): TaskGroup[] {
  const groups: TaskGroup[] = []

  // 1. Separate Headers (Phases) and Children
  // Headers are explicitly marked as "node" with friendly names OR we can use the "parent_id" linking
  // In the new system, headers are tasks where type="node" (usually) and they are parents.

  // Strategy: 
  // - Find tasks that ARE parents (id referenced by others) OR are explicit phase headers
  // - Group others under them

  const headerMap = new Map<number, TaskItem>()
  const childrenMap = new Map<number, TaskItem[]>() // parent_id -> tasks
  const orphans: TaskItem[] = []

  // First pass: Organize by parent_id
  tasks.forEach(task => {
    if (task.parent_id) {
      if (!childrenMap.has(task.parent_id)) {
        childrenMap.set(task.parent_id, [])
      }
      childrenMap.get(task.parent_id)?.push(task)
    } else {
      // Potential Header (or Orphan)
      // We consider it a header if it starts with "►" (Phase marker from backend)
      if (task.name.startsWith("►") || task.type === "node") {
        headerMap.set(task.id, task)
      } else {
        orphans.push(task)
      }
    }
  })

  // 2. Create Groups from Headers
  headerMap.forEach((header, id) => {
    const children = childrenMap.get(id) || []

    // determine group status based on children + header
    let status = header.status
    if (status === "running" && children.some(c => c.status === "failed")) {
      // If header says running but a child failed? usually header will update eventually.
      // Keep header status as truth.
    }

    groups.push({
      id: `g-${header.id}`,
      title: header.name.replace("► ", "").replace("Phase: ", ""),
      status: status,
      tasks: children,
      isImplicit: false
    })
  })

  // 3. Handle Orphans (Implicit "Execution" Phase)
  if (orphans.length > 0) {
    // Check if we already have an "Execution" group? No, implicit is unique.
    // Grouping orphans together allows handling legacy events or untracked tools
    const implicitGroup: TaskGroup = {
      id: "g-implicit",
      title: t("chat.steps.execution", "Execution"), // "执行阶段"
      status: orphans.some(t => t.status === "running") ? "running" : "done",
      tasks: orphans,
      isImplicit: true
    }
    // Put implicit group at the place where the first orphan appeared? 
    // Or at bottom? Time-based sorting usually prefers implicit stuff to flow naturally.
    // For now, simpler to append.
    groups.push(implicitGroup)
  }

  // 4. Sort Groups by ID (assuming ID is roughly chronological)
  // Headers usually created sequentially.
  // Implicit group ID is string, maybe put it based on first orphan ID?
  groups.sort((a, b) => {
    const getOrder = (g: TaskGroup) => {
      if (g.isImplicit && g.tasks.length > 0) return g.tasks[0].id
      return parseInt(g.id.replace("g-", "")) || 999999
    }
    return getOrder(a) - getOrder(b)
  })

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
  const { t } = useTranslation()
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
                {group.tasks.length} {t("chat.steps.steps", "steps")}
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
              {t("chat.steps.initializingPhase", "Initializing phase...")}
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
  const { t } = useTranslation()
  const groups = useMemo(() => groupTasks(tasks || [], t), [tasks, t])

  if (!tasks || tasks.length === 0) return null

  return (
    <div className="flex flex-col gap-1 w-full max-w-[95%] animate-in fade-in">
      {groups.map(group => (
        <TaskGroupItem key={group.id} group={group} />
      ))}
    </div>
  )
}
