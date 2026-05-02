import { useQuery } from "@tanstack/react-query"
import {
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  Loader2,
  Map as MapIcon,
  XCircle,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { MessageContent } from "../MessageContent"
import { useTranslation } from "react-i18next"
import { PlanningService } from "@/client"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { useChatStore } from "@/stores/chatStore"
import type { ToolStep } from "@/types/toolstep"

interface PlanStep {
  id: string
  title: string
  status: "pending" | "in_progress" | "completed" | "failed"
  result?: string
  execution_run_id?: string
}

interface Plan {
  id: string
  title: string
  steps: PlanStep[]
  current_step_id?: string
}

interface MessageGroup {
  turn: number
  messageId: string | number
  isStreaming: boolean
  steps: ToolStep[]
}

interface ActivityTabProps {
  activeThreadId?: string
}

/**
 * ActivityTab — Agent execution dashboard.
 *
 * Layout order:
 *   1. Thinking
 *   2. Plan
 *   3. Execution Steps (grouped by AI message turn)
 *
 * Execution steps are grouped by AI message. The currently-running group
 * is expanded; completed groups are collapsed. Nothing disappears.
 */
export function ActivityTab({ activeThreadId }: ActivityTabProps) {
  const { t } = useTranslation()
  const messages = useChatStore((state) => state.messages)
  const status = useChatStore((state) => state.status)

  const isAgentActive =
    status === "running" || status === "interrupted" || status === "summarizing"

  // ------------------------------------------------------------------
  // Thinking — from the latest AI message (real-time while streaming)
  // ------------------------------------------------------------------
  const lastAiMessage = useMemo(
    () => [...messages].reverse().find((m) => m.role === "ai"),
    [messages],
  )

  const persistedThinking = lastAiMessage?.thinking || ""
  const streamingThinking = useChatStore(state => state.streamingThinking)
  const thinking = (persistedThinking + streamingThinking).trim()

  // ------------------------------------------------------------------
  // Plan — thread-level, persisted in DB
  // ------------------------------------------------------------------
  const { data: planData, isLoading: isLoadingPlan } = useQuery({
    queryKey: ["threadPlan", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return null
      return PlanningService.getPlan({ threadId: activeThreadId })
    },
    enabled: !!activeThreadId,
    refetchInterval: 3000,
  })

  const typedPlanData = planData as any
  const plan = typedPlanData?.plan as Plan | null
  const planStatus = typedPlanData?.status

  // ------------------------------------------------------------------
  // Execution steps — grouped by conversation turn.
  // A "turn" is everything between two human messages (or from start
  // to the first human message). Within one turn there may be multiple
  // AI messages; their steps are merged into a single group.
  // ------------------------------------------------------------------
  const stepGroups = useMemo(() => {
    const groups: MessageGroup[] = []
    let bufferSteps: ToolStep[] = []
    let bufferAiIds: (string | number)[] = []
    let bufferIsStreaming = false
    let turn = 1

    // Helper to deduplicate steps
    const deduplicateSteps = (steps: ToolStep[]) => {
      const seenIds = new Set<string>()
      return steps.filter(s => {
        const id = s.id || `${s.name}-${s.tool_name}`
        if (seenIds.has(id)) return false
        seenIds.add(id)
        return true
      })
    }

    // Walk backwards so we can split on human-message boundaries.
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === "human") {
        // End of a turn — flush the buffer.
        if (bufferSteps.length > 0) {
          groups.unshift({
            turn,
            messageId: bufferAiIds[0] || m.id,
            isStreaming: bufferIsStreaming,
            steps: deduplicateSteps(bufferSteps),
          })
          turn++
        }
        bufferSteps = []
        bufferAiIds = []
        bufferIsStreaming = false
      } else if (m.role === "tool") {
        // NEW: Handle flat tool messages
        bufferSteps.unshift({
          id: m.id as string,
          name: m.meta_data?.tool_name || m.tool_name || t("chat.messageList.toolExecution"),
          status: m.status as any,
          input: m.meta_data?.input || {},
          output: undefined, // Per user request: Don't show huge output in UI
          tool_meta: m.meta_data?.tool_meta
        })
      } else if (m.role === "ai") {
        // Handle nested steps (compatibility with existing folded messages)
        const s = m.steps || []
        if (s.length > 0) {
          bufferSteps.unshift(...s)
          bufferAiIds.unshift(m.id)
        }
        if (m.status === "streaming") bufferIsStreaming = true
      }
    }

    // Handle initial messages
    if (bufferSteps.length > 0) {
      groups.unshift({
        turn,
        messageId: bufferAiIds[0] || "start",
        isStreaming: bufferIsStreaming,
        steps: deduplicateSteps(bufferSteps),
      })
    }

    return groups
  }, [messages, t])

  // ------------------------------------------------------------------
  // Collapse state — auto-expand when content exists, collapse when empty
  // ------------------------------------------------------------------
  const [thinkingOpen, setThinkingOpen] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)
  const [stepsOpen, setStepsOpen] = useState(false)

  useEffect(() => {
    if (lastAiMessage?.status === "streaming") {
      setThinkingOpen(!!(thinking && thinking.trim().length > 0))
    } else {
      setThinkingOpen(false)
    }
  }, [thinking, lastAiMessage?.status])

  useEffect(() => {
    setPlanOpen(!!plan)
  }, [plan])

  useEffect(() => {
    setStepsOpen(stepGroups.length > 0)
  }, [stepGroups])

  return (
    <ScrollArea className="h-full bg-muted/5">
      <div className="flex flex-col">
        {/* === BLOCK 1: THINKING === */}
        <Collapsible open={thinkingOpen} onOpenChange={setThinkingOpen}>
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b">
              {thinkingOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <BrainCircuit className="h-3.5 w-3.5 text-primary/70" />
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
                {t("chat.thinkingTitle")}
              </span>
              {thinking && thinking.trim().length > 0 && isAgentActive && (
                <span className="text-[10px] text-primary animate-pulse">
                  {t("chat.thinkingActive")}
                </span>
              )}
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="p-2">
              {thinking && thinking.trim().length > 0 ? (
                <div className="text-xs text-muted-foreground break-words leading-relaxed pl-5">
                  <MessageContent content={thinking} />
                </div>
              ) : (
                <div className="text-xs text-muted-foreground italic text-center py-4">
                  {isAgentActive
                    ? t("chat.thinkingWaiting")
                    : t("chat.noThinking")}
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* === BLOCK 2: PLAN === */}
        <Collapsible open={planOpen} onOpenChange={setPlanOpen}>
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b bg-muted/20">
              {planOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <MapIcon className="h-3.5 w-3.5 text-primary/70" />
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
                {t("chat.context.planTitle")}
              </span>
              <span className="text-[10px] uppercase font-bold text-muted-foreground/50">
                {planStatus === "no_graph"
                  ? t("chat.context.statusOffline")
                  : planStatus === "no_state" || planStatus === "no_plan"
                    ? t("chat.context.statusIdle")
                    : t("chat.context.statusActive")}
              </span>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="p-2">
              {isLoadingPlan ? (
                <div className="flex justify-center p-4">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : !plan ? (
                <div className="text-center text-xs text-muted-foreground py-6 border-2 border-dashed rounded-md">
                  {t("chat.context.noPlan")}
                </div>
              ) : (
                <div className="space-y-2">
                  {plan.steps.map((step, idx) => (
                    <div
                      key={step.id}
                      onClick={() => {
                        if (step.execution_run_id) {
                          window.dispatchEvent(
                            new CustomEvent("chat-scroll-to-run", {
                              detail: { runId: step.execution_run_id },
                            }),
                          )
                        }
                      }}
                      className={`relative pl-4 border-l-2 transition-colors ${
                        step.status === "completed"
                          ? "border-primary"
                          : step.status === "in_progress"
                            ? "border-yellow-500"
                            : "border-muted"
                      } ${step.execution_run_id ? "cursor-pointer hover:bg-muted/10 pr-2 rounded-r" : ""}`}
                    >
                      <div className="text-xs font-medium flex items-center gap-2">
                        <span
                          className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                            step.status === "completed"
                              ? "bg-primary text-primary-foreground"
                              : step.status === "in_progress"
                                ? "bg-yellow-500 text-white"
                                : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {idx + 1}
                        </span>
                        <span
                          className={
                            step.execution_run_id
                              ? "underline decoration-dotted underline-offset-2"
                              : ""
                          }
                        >
                          {step.title}
                        </span>
                      </div>
                      {step.result && (
                        <div className="mt-1 text-[10px] text-muted-foreground bg-muted/30 p-1.5 rounded">
                          {step.result}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* === BLOCK 3: EXECUTION STEPS (grouped by turn) === */}
        <Collapsible open={stepsOpen} onOpenChange={setStepsOpen}>
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b bg-muted/20">
              {stepsOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <Loader2
                className={`h-3.5 w-3.5 ${isAgentActive ? "animate-spin text-primary" : ""}`}
              />
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
                {t("chat.liveStepsTitle")}
              </span>
              {stepGroups.length > 0 && (
                <span className="text-[10px] text-muted-foreground">
                  {t("chat.stepGroupsCount", { count: stepGroups.length })}
                </span>
              )}
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="p-2">
              {stepGroups.length === 0 ? (
                <div className="text-xs text-muted-foreground italic text-center py-4">
                  {isAgentActive
                    ? t("chat.waitingForSteps")
                    : t("chat.noSteps")}
                </div>
              ) : (
                <div className="space-y-3">
                  {stepGroups.map((group) => (
                    <StepGroup key={group.messageId} group={group} />
                  ))}
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </ScrollArea>
  )
}

function StepGroup({ group }: { group: MessageGroup }) {
  const { t } = useTranslation()
  // Expand the group if it is currently streaming; otherwise collapse.
  const [expanded, setExpanded] = useState(group.isStreaming)

  const runningCount = group.steps.filter((s) => s.status === "running").length
  const doneCount = group.steps.filter((s) => s.status === "done").length
  const failedCount = group.steps.filter((s) => s.status === "failed").length

  return (
    <div className="border-b border-border/30">
      <button
        className="w-full flex items-center justify-between py-2"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          {group.isStreaming ? (
            <Loader2 className="h-3 w-3 animate-spin text-yellow-500" />
          ) : failedCount > 0 ? (
            <XCircle className="h-3 w-3 text-red-500" />
          ) : (
            <CheckCircle2 className="h-3 w-3 text-primary" />
          )}
          <span className="text-xs font-medium">
            {t("chat.turnLabel", { turn: group.turn })}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {group.isStreaming
              ? t("chat.turnRunning", { running: runningCount, total: group.steps.length })
              : t("chat.turnDone", { done: doneCount, failed: failedCount, total: group.steps.length })}
          </span>
        </div>
        {expanded ? (
          <ChevronUp className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="p-2 space-y-2">
          {group.steps.map((step, i) => (
            <StepRow key={step.id || i} step={step} />
          ))}
        </div>
      )}
    </div>
  )
}

function StepRow({ step }: { step: ToolStep }) {
  const [expanded, setExpanded] = useState(false)
  const displayName = step.name || step.tool_name || step.tool || "unknown"

  const statusConfig = {
    running: {
      icon: <Loader2 className="h-3 w-3 animate-spin text-yellow-500" />,
      bg: "bg-yellow-500/10 border-yellow-500/30",
      text: "text-yellow-600",
    },
    done: {
      icon: <CheckCircle2 className="h-3 w-3 text-primary" />,
      bg: "bg-primary/5 border-primary/20",
      text: "text-primary",
    },
    failed: {
      icon: <XCircle className="h-3 w-3 text-red-500" />,
      bg: "bg-red-500/10 border-red-500/30",
      text: "text-red-600",
    },
    pending: {
      icon: <Circle className="h-3 w-3 text-muted-foreground" />,
      bg: "bg-muted/10 border-muted",
      text: "text-muted-foreground",
    },
  }

  const config =
    statusConfig[step.status as keyof typeof statusConfig] || statusConfig.pending

  return (
    <div className={`p-2 transition-colors ${config.bg}`}>
      <button
        className="w-full flex items-center gap-2"
        onClick={() => setExpanded((v) => !v)}
      >
        {config.icon}
        <span className={`text-xs font-medium flex-1 text-left ${config.text}`}>
          {displayName}
        </span>
        {expanded ? (
          <ChevronUp className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="mt-2 space-y-1.5 pl-5">
          {step.input && Object.keys(step.input).length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-muted-foreground uppercase">
                Input
              </div>
              <div className="text-[10px] font-mono bg-muted/40 p-1.5 rounded break-all">
                {JSON.stringify(step.input, null, 2)}
              </div>
            </div>
          )}
          {step.output && (
            <div>
              <div className="text-[10px] font-semibold text-muted-foreground uppercase">
                Output
              </div>
              <div className="text-[10px] text-muted-foreground bg-muted/40 p-1.5 rounded whitespace-pre-wrap break-words max-h-[120px] overflow-y-auto">
                {step.output}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
