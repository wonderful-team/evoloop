import { useEffect, useMemo, useState } from "react"
import {
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Map as MapIcon,
  XCircle,
} from "lucide-react"
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
import { useQuery } from "@tanstack/react-query"

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
 */
export function ActivityTab({ activeThreadId }: ActivityTabProps) {
  const { t } = useTranslation()
  const messages = useChatStore((state) => state.messages)
  const status = useChatStore((state) => state.status)

  const isAgentActive =
    status === "running" || status === "interrupted" || status === "summarizing"

  const lastAiMessage = useMemo(
    () => [...messages].reverse().find((m) => m.role === "ai"),
    [messages],
  )

  const persistedThinking = lastAiMessage?.thinking || ""
  const streamingThinking = useChatStore(state => state.streamingThinking)
  
  // Scheme A: Latest Only. Prioritize current streaming thought, 
  // or show the last persisted one if it's the very latest activity.
  const thinking = (streamingThinking.trim().length > 0 
    ? streamingThinking 
    : persistedThinking).trim()

  const { data: planData, isLoading: isLoadingPlan } = useQuery({
    queryKey: ["threadPlan", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return null
      return PlanningService.getPlan({ threadId: activeThreadId })
    },
    enabled: !!activeThreadId,
    refetchInterval: isAgentActive ? 3000 : false,
  })

  const typedPlanData = planData as any
  const plan = typedPlanData?.plan as Plan | null
  const planStatus = typedPlanData?.status

  // Optimization: Split messages into stable "historical turns" and the "current active turn".
  // Historical turns only change when a new human message arrives (rare).
  // Current turn changes on every streaming token (frequent).
  // This prevents the expensive full reverse-scan from running on every token.
  const { historyTurnMessages, currentTurnMessages } = useMemo(() => {
    // Find the index of the last human message
    let lastHumanIdx = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'human') {
        lastHumanIdx = i
        break
      }
    }
    if (lastHumanIdx === -1) {
      return { historyTurnMessages: [], currentTurnMessages: messages }
    }
    return {
      historyTurnMessages: messages.slice(0, lastHumanIdx + 1), // includes the human message
      currentTurnMessages: messages.slice(lastHumanIdx + 1),    // only the current AI/tool responses
    }
  }, [messages])

  // Build step groups for HISTORICAL turns — runs only when a new human message arrives
  const historyStepGroups = useMemo(() => {
    const groups: MessageGroup[] = []
    let bufferSteps: ToolStep[] = []
    let bufferAiIds: (string | number)[] = []
    let turn = 1

    const deduplicateSteps = (steps: ToolStep[]) => {
      const seenIds = new Set<string>()
      return steps.filter(s => {
        const id = s.tool_call_id || s.id || `${s.name}-${s.tool_name}`
        if (seenIds.has(id)) return false
        seenIds.add(id)
        return true
      })
    }

    for (let i = historyTurnMessages.length - 1; i >= 0; i--) {
      const m = historyTurnMessages[i]
      if (m.role === 'human') {
        if (bufferSteps.length > 0) {
          groups.unshift({
            turn,
            messageId: bufferAiIds[0] || m.id,
            isStreaming: false,
            steps: deduplicateSteps(bufferSteps),
          })
          turn++
        }
        bufferSteps = []
        bufferAiIds = []
      } else if (m.role === 'tool') {
        const msgAny = m as any
        const toolCallId = msgAny.tool_call_id || msgAny.meta_data?.tool_call_id
        const tName = msgAny.meta_data?.tool_name || m.tool_name || 'unknown'
        bufferSteps.unshift({
          id: (toolCallId || m.id) as string,
          tool_call_id: toolCallId as string,
          tool: tName,
          name: msgAny.meta_data?.tool_name || m.tool_name || t('chat.messageList.toolExecution'),
          status: (m.status === 'completed' ? 'done' : m.status) as any,
          input: msgAny.meta_data?.input || {},
          output: undefined,
          tool_meta: msgAny.meta_data?.tool_meta
        })
      } else if (m.role === 'ai') {
        if (m.id) bufferAiIds.unshift(m.id)
      }
    }
    return groups
  }, [historyTurnMessages, t])

  // Build step group for CURRENT active turn — runs on every streaming token (cheap, only current turn)
  const currentTurnStepGroup = useMemo((): MessageGroup | null => {
    if (currentTurnMessages.length === 0) return null

    const bufferSteps: ToolStep[] = []
    const bufferAiIds: (string | number)[] = []
    let isStreaming = false

    const deduplicateSteps = (steps: ToolStep[]) => {
      const seenIds = new Set<string>()
      return steps.filter(s => {
        const id = s.tool_call_id || s.id || `${s.name}-${s.tool_name}`
        if (seenIds.has(id)) return false
        seenIds.add(id)
        return true
      })
    }

    for (const m of currentTurnMessages) {
      if (m.role === 'tool') {
        const msgAny = m as any
        const toolCallId = msgAny.tool_call_id || msgAny.meta_data?.tool_call_id
        const tName = msgAny.meta_data?.tool_name || m.tool_name || 'unknown'
        bufferSteps.push({
          id: (toolCallId || m.id) as string,
          tool_call_id: toolCallId as string,
          tool: tName,
          name: msgAny.meta_data?.tool_name || m.tool_name || t('chat.messageList.toolExecution'),
          status: (m.status === 'completed' ? 'done' : m.status) as any,
          input: msgAny.meta_data?.input || {},
          output: undefined,
          tool_meta: msgAny.meta_data?.tool_meta
        })
      } else if (m.role === 'ai') {
        if (m.status === 'streaming') isStreaming = true
        if (m.id) bufferAiIds.push(m.id)
      }
    }

    if (bufferSteps.length === 0 && !isStreaming) return null

    const turnNumber = historyStepGroups.length + 1
    return {
      turn: turnNumber,
      messageId: bufferAiIds[0] || 'current',
      isStreaming,
      steps: deduplicateSteps(bufferSteps),
    }
  }, [currentTurnMessages, historyStepGroups.length, t])

  // Merge history groups + current turn group
  const stepGroups = useMemo(() => {
    if (currentTurnStepGroup) return [...historyStepGroups, currentTurnStepGroup]
    return historyStepGroups
  }, [historyStepGroups, currentTurnStepGroup])

  const [thinkingOpen, setThinkingOpen] = useState(true)
  const [planOpen, setPlanOpen] = useState(false)
  const [stepsOpen, setStepsOpen] = useState(true)

  // Controlled by user after initial mount
  useEffect(() => {
    if (plan) setPlanOpen(true)
  }, [plan])

  useEffect(() => {
    if (stepGroups.length > 0) setStepsOpen(true)
  }, [stepGroups])

  const sessionGoal = useChatStore((state) => state.sessionGoal)
  const [goalOpen, setGoalOpen] = useState(true)

  return (
    <div className="h-full w-full min-w-0 flex flex-col bg-muted/5 overflow-hidden">
        {/* === BLOCK 0: GOAL === */}
        {sessionGoal && (
          <Collapsible 
            open={goalOpen} 
            onOpenChange={setGoalOpen} 
            className={`flex flex-col min-h-0 border-b border-border transition-all duration-200 ${goalOpen ? "shrink-0" : "shrink-0"}`}
          >
            <CollapsibleTrigger asChild>
              <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
                {goalOpen ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <BrainCircuit className="h-3.5 w-3.5 text-primary/70" />
                <span className="text-[10px] font-bold text-muted-foreground flex-1">
                  {t("chat.context.sessionGoalTitle")}
                </span>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="min-h-0 overflow-hidden flex flex-col">
              <div className="p-3 text-xs text-foreground leading-relaxed font-medium bg-background/50 border-b border-border/50">
                {sessionGoal}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
        {/* === BLOCK 1: PLAN === */}
        <Collapsible 
          open={planOpen} 
          onOpenChange={setPlanOpen} 
          className={`flex flex-col min-h-0 border-b border-border transition-all duration-200 ${planOpen ? "flex-1" : "shrink-0"}`}
        >
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
              {planOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <MapIcon className="h-3.5 w-3.5 text-primary/70" />
              <span className="text-[10px] font-bold text-muted-foreground flex-1">
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
          <CollapsibleContent className="flex-1 min-h-0 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="p-2">
                {isLoadingPlan ? (
                  <div className="flex justify-center p-4">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : !plan ? (
                  <div className="text-center text-xs text-muted-foreground py-6 border-2 border-dashed rounded-md mx-2">
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
            </ScrollArea>
          </CollapsibleContent>
        </Collapsible>

        {/* === BLOCK 2: THINKING === */}
        <Collapsible 
          open={thinkingOpen} 
          onOpenChange={setThinkingOpen} 
          className={`flex flex-col min-h-0 min-w-0 w-full overflow-hidden border-b border-border transition-all duration-200 ${thinkingOpen ? "flex-1" : "shrink-0"}`}
        >
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors shrink-0 w-full overflow-hidden">
              {thinkingOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              )}
              <BrainCircuit className="h-3.5 w-3.5 text-primary/70 shrink-0" />
              <span className="text-[10px] font-bold text-muted-foreground flex-1 truncate">
                {t("chat.thinkingTitle")}
              </span>
              {thinking && thinking.trim().length > 0 && isAgentActive && (
                <span className="text-[10px] text-primary shrink-0 ml-1">
                  {t("chat.thinkingActive")}
                </span>
              )}
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex-1 min-h-0 min-w-0 w-full overflow-hidden flex flex-col">
            <ScrollArea className="flex-1 min-w-0 w-full">
              <div className="p-2 min-w-0 w-full overflow-hidden">
                {thinking && thinking.trim().length > 0 ? (
                  <div className="text-xs text-muted-foreground break-words leading-relaxed min-w-0 w-full overflow-hidden [word-break:break-word] whitespace-normal">
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
            </ScrollArea>
          </CollapsibleContent>
        </Collapsible>

        {/* === BLOCK 3: EXECUTION STEPS === */}
        <Collapsible 
          open={stepsOpen} 
          onOpenChange={setStepsOpen} 
          className={`flex flex-col min-h-0 transition-all duration-200 ${stepsOpen ? "flex-1" : "shrink-0"}`}
        >
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
              {stepsOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <Loader2
                className={`h-3.5 w-3.5 ${isAgentActive ? "animate-spin text-primary" : ""}`}
              />
              <span className="text-[10px] font-bold text-muted-foreground flex-1">
                {t("chat.liveStepsTitle")}
              </span>
              {stepGroups.length > 0 && (
                <span className="text-[10px] text-muted-foreground">
                  {t("chat.stepGroupsCount", { count: stepGroups.length })}
                </span>
              )}
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex-1 min-h-0 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
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
            </ScrollArea>
          </CollapsibleContent>
        </Collapsible>
    </div>
  )
}

function StepGroup({ group }: { group: MessageGroup }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(group.isStreaming)

  useEffect(() => {
    if (group.isStreaming) setExpanded(true)
  }, [group.isStreaming])

  const runningCount = group.steps.filter((s) => s.status === "running").length
  const doneCount = group.steps.filter((s) => s.status === "done" || (s.status as any) === "completed").length
  const failedCount = group.steps.filter((s) => s.status === "failed").length

  return (
    <div className="border-b border-border/30 last:border-0 overflow-hidden w-full min-w-0">
      <button
        className="w-full flex items-center justify-between py-2.5 px-1 hover:bg-muted/30 transition-colors rounded-sm min-w-0"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2 min-w-0 truncate">
          {group.isStreaming ? (
            <div className="relative shrink-0">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            </div>
          ) : failedCount > 0 ? (
            <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-primary/60 shrink-0" />
          )}
          <span className="text-[10px] font-bold text-muted-foreground truncate">
            {t("chat.turnLabel", { turn: group.turn })}
          </span>
          <span className="text-[9px] text-muted-foreground/50 font-mono shrink-0">
            {group.isStreaming
              ? `${runningCount} RUNNING`
              : `${doneCount} DONE`}
          </span>
        </div>
        <ChevronRight className={`h-3 w-3 text-muted-foreground/30 transition-transform duration-200 shrink-0 ml-1 ${expanded ? 'rotate-90' : ''}`} />
      </button>
      
        {expanded && (
          <div className="pb-3 space-y-1 w-full min-w-0 overflow-hidden">
            {group.steps.map((step, i) => (
              <StepRow key={step.id || i} step={step} />
            ))}
          </div>
        )}
    </div>
  )
}

function StepRow({ step }: { step: ToolStep }) {
  const { t } = useTranslation()
  const isRunning = step.status === "running"
  const isFailed = step.status === "failed"
  const isCompleted = step.status === "done" || (step.status as any) === "completed"

  const [isOpen, setIsOpen] = useState(isRunning)

  useEffect(() => {
    if (isRunning) setIsOpen(true)
    if (isCompleted) setIsOpen(false)
  }, [isRunning, isCompleted])

  return (
    <div className="relative pl-6 py-2 group border-l border-border border-transparent hover:border-primary/10 transition-colors w-full min-w-0 overflow-hidden">
      <div className="absolute left-[-1.5px] top-0 bottom-0 w-[1px] bg-border/20 group-hover:bg-primary/20" />
      <div className={`absolute left-[-4.5px] top-4 w-2 h-2 rounded-full border-2 border-background z-10 transition-colors ${
        isRunning ? 'bg-primary' : isFailed ? 'bg-red-500' : isCompleted ? 'bg-primary/40' : 'bg-muted'
      }`} />

      <div 
        className="flex items-center gap-2 cursor-pointer select-none w-full min-w-0 overflow-hidden"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="text-[10px] font-bold text-muted-foreground/80 tracking-tight flex-1 truncate font-mono min-w-0">
          {step.name || step.tool_name || t("chat.messageList.toolExecution")}
        </span>
        <div className="flex items-center gap-2 shrink-0 ml-1">
          {isRunning ? (
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
          ) : isFailed ? (
            <XCircle className="h-3 w-3 text-red-500/50" />
          ) : (
            <CheckCircle2 className="h-3 w-3 text-primary/30" />
          )}
          <ChevronRight className={`h-3 w-3 text-muted-foreground/20 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
        </div>
      </div>

      {isOpen && step.input && (
        <div className="mt-1.5 p-2 bg-muted/20 rounded-sm text-[10px] font-mono text-muted-foreground/70 break-all border border-border/10 leading-relaxed shadow-inner w-full min-w-0 overflow-x-auto max-h-60">
          <pre className="whitespace-pre-wrap font-mono [word-break:break-word] m-0 text-[10px]">
            {typeof step.input === "string" 
              ? step.input 
              : JSON.stringify(step.input, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
