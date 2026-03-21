import {
  CheckCircle2,
  Cpu,
  Loader2,
  Sparkles,
  Terminal,
  XCircle,
} from "lucide-react"
import { memo, useMemo } from "react"
import { useTranslation } from "react-i18next"

export interface StepItem {
  id: number
  name: string
  status: "running" | "done" | "failed" | "cancelled"
  type: "node" | "tool" | "ai" | "skill"
  parent_id?: number // Link to parent phase
  time: string
  details?: string
}

// A Group is a collection of steps under a header
interface StepGroup {
  id: string
  title: string
  status: string // derived from children
  steps: StepItem[] // The actual steps in this phase
  isImplicit?: boolean // If true, didn't have a header step
}

interface ExecutionStepsProps {
  steps: StepItem[]
}

// Replaces legacy assumption-based grouping with direct parent_id hierarchy
function groupSteps(steps: StepItem[], t: any): StepGroup[] {
  const groups: StepGroup[] = []

  // 1. Separate Headers and Children
  const headerMap = new Map<number, StepItem>()
  const childrenMap = new Map<number, StepItem[]>() // parent_id -> steps
  const orphans: StepItem[] = []

  // First pass: Organize by parent_id
  steps.forEach(step => {
    // Ensure parent_id is a number (JSON deserialization may convert to string)
    const parentId = step.parent_id != null ? Number(step.parent_id) : null
    const stepId = Number(step.id)

    if (parentId) {
      if (!childrenMap.has(parentId)) {
        childrenMap.set(parentId, [])
      }
      childrenMap.get(parentId)?.push(step)
    } else {
      // Potential Header (or Orphan)
      if (step.name.startsWith("►") || step.type === "node") {
        headerMap.set(stepId, step)
      } else {
        orphans.push(step)
      }
    }
  })

  // 2. Create Groups from Headers
  headerMap.forEach((header, id) => {
    const children = childrenMap.get(Number(id)) || []

    // determine group status based on children + header
    let status = header.status
    if (status === "running" && children.some(c => c.status === "failed")) {
      // Keep header status as truth.
    }

    groups.push({
      id: `g-${header.id}`,
      title: header.name.replace("► ", "").replace("Phase: ", ""),
      status: status,
      steps: children,
      isImplicit: false
    })
  })

  // 3. Handle Orphans (implicit Execution group)
  if (orphans.length > 0) {
    const implicitGroup: StepGroup = {
      id: "g-implicit",
      title: t("chat.steps.execution", "Execution"), // "执行阶段"
      status: orphans.some(t => t.status === "running") ? "running" : "done",
      steps: orphans,
      isImplicit: true
    }
    groups.push(implicitGroup)
  }

  // 4. Sort Groups by ID
  groups.sort((a, b) => {
    const getOrder = (g: StepGroup) => {
      if (g.isImplicit && g.steps.length > 0) return g.steps[0].id
      return parseInt(g.id.replace("g-", "")) || 999999
    }
    return getOrder(a) - getOrder(b)
  })

  return groups
}

const StepNodeItem = memo(({ step }: { step: StepItem }) => {
  return (
    <div className="flex items-start gap-3 p-2 rounded-lg text-sm font-mono bg-muted/10 ml-2 border-l border-muted pl-3 hover:bg-muted/20 transition-colors animate-in fade-in slide-in-from-left-2">
      {/* Status Icon */}
      <div className="mt-0.5 shrink-0">
        {step.status === "running" && (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
        )}
        {step.status === "done" && (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
        )}
        {(step.status === "failed" || step.status === "cancelled") && (
          <XCircle className="w-3.5 h-3.5 text-destructive" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Type Icon */}
          {step.type === "skill" && (
            <Sparkles className="w-3 h-3 text-amber-500" />
          )}
          {step.type === "tool" && (
            <Terminal className="w-3 h-3 text-muted-foreground" />
          )}
          {step.type === "ai" && (
            <Cpu className="w-3 h-3 text-muted-foreground" />
          )}

          <span className={`truncate ${step.status === "running" ? "text-foreground" : "text-muted-foreground"}`}>
            {step.name}
          </span>
        </div>

        {/* Details */}
        {step.details && !(step.type === "ai" && step.status === "running") && (
          <div className="text-xs text-muted-foreground pl-5 pt-1 break-words whitespace-pre-wrap opacity-80 line-clamp-4">
            {step.details}
          </div>
        )}
      </div>

      {/* Time */}
      {step.time && (
        <div className="text-[10px] text-muted-foreground shrink-0 mt-0.5 opacity-50">
          {step.time}
        </div>
      )}
    </div>
  )
})
StepNodeItem.displayName = "StepNodeItem"

// Simplified StepGroupItem - no outer collapsible since parent handles it
const StepGroupItem = memo(({ group }: { group: StepGroup }) => {
  const { t } = useTranslation()

  return (
    <div className="w-full min-w-0 border rounded-lg bg-background/50 overflow-hidden mb-2 shadow-sm">
      <div className={`p-2 px-3 flex items-center justify-between ${group.status === "running" ? "bg-primary/5" : ""}`}>
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

          <span className="text-xs text-muted-foreground">
            {group.steps.length} {t("chat.steps.steps", "steps")}
          </span>
        </div>
      </div>

      {/* Always show steps since outer collapsible controls visibility */}
      <div className="p-2 pt-0 flex flex-col gap-1 mt-1 border-t border-border/30">
        {group.steps.length === 0 && (
          <div className="text-xs text-muted-foreground italic pl-8 py-2">
            {t("chat.steps.initializingPhase", "Initializing phase...")}
          </div>
        )}
        {group.steps.map(step => (
          <StepNodeItem key={step.id} step={step} />
        ))}
      </div>
    </div>
  )
})
StepGroupItem.displayName = "StepGroupItem"


export function ExecutionSteps({ steps }: ExecutionStepsProps) {
  const { t } = useTranslation()
  const groups = useMemo(() => groupSteps(steps || [], t), [steps, t])

  if (!steps || steps.length === 0) return null

  return (
    <div className="flex flex-col gap-1 w-full min-w-0 animate-in fade-in">
      {groups.map(group => (
        <StepGroupItem key={group.id} group={group} />
      ))}
    </div>
  )
}
