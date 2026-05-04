import { useEffect, useMemo, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
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
  const thinking = (persistedThinking + streamingThinking).trim()

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

  const stepGroups = useMemo(() => {
    const groups: MessageGroup[] = []
    let bufferSteps: ToolStep[] = []
    let bufferAiIds: (string | number)[] = []
    let bufferIsStreaming = false
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

    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === "human") {
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
        const toolCallId = m.tool_call_id || m.meta_data?.tool_call_id
        const tName = m.meta_data?.tool_name || m.tool_name || "unknown"
        bufferSteps.unshift({
          id: (toolCallId || m.id) as string,
          tool_call_id: toolCallId as string,
          tool: tName,
          name: m.meta_data?.tool_name || m.tool_name || t("chat.messageList.toolExecution"),
          status: (m.status === "completed" ? "done" : m.status) as any,
          input: m.meta_data?.input || {},
          output: undefined,
          tool_meta: m.meta_data?.tool_meta
        })
      } else if (m.role === "ai") {
        if (m.status === "streaming") bufferIsStreaming = true
        if (m.id) bufferAiIds.unshift(m.id)
      }
    }

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

  const [thinkingOpen, setThinkingOpen] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)
  const [stepsOpen, setStepsOpen] = useState(false)

  useEffect(() => {
    if (lastAiMessage?.status === "streaming" && streamingThinking && streamingThinking.trim().length > 0) {
      setThinkingOpen(true)
    } else {
      setThinkingOpen(false)
    }
  }, [streamingThinking, lastAiMessage?.status])

  useEffect(() => {
    setPlanOpen(!!plan)
  }, [plan])

  useEffect(() => {
    setStepsOpen(stepGroups.length > 0)
  }, [stepGroups])

  return (
    <ScrollArea className="h-full bg-muted/5">
      <div className="flex flex-col min-h-full">
        {!plan && !thinking && stepGroups.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 opacity-50">
            <div className="relative">
              <BrainCircuit className="h-12 w-12 text-primary/20" />
              <motion.div 
                animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.6, 0.3] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                className="absolute inset-0 bg-primary/10 blur-xl rounded-full"
              />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
                {t("chat.activity.idleTitle", "Neural Network Idle")}
              </p>
              <p className="text-[10px] text-muted-foreground/40 max-w-[160px] mx-auto leading-relaxed">
                {t("chat.activity.idleDesc", "Waiting for conversation intent to initialize execution graph.")}
              </p>
            </div>
          </div>
        ) : (
          <motion.div layout className="flex flex-col">
            {/* === BLOCK 1: PLAN === */}
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

            {/* === BLOCK 2: THINKING === */}
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

            {/* === BLOCK 3: EXECUTION STEPS === */}
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
          </motion.div>
        )}
      </div>
    </ScrollArea>
  )
}

function StepGroup({ group }: { group: MessageGroup }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(group.isStreaming)

  useEffect(() => {
    if (group.isStreaming) setExpanded(true)
  }, [group.isStreaming])

  const runningCount = group.steps.filter((s) => s.status === "running").length
  const doneCount = group.steps.filter((s) => s.status === "done" || s.status === "completed").length
  const failedCount = group.steps.filter((s) => s.status === "failed").length

  return (
    <div className="border-b border-border/30 last:border-0 overflow-hidden">
      <button
        className="w-full flex items-center justify-between py-2.5 px-1 hover:bg-muted/30 transition-colors rounded-sm"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          {group.isStreaming ? (
            <div className="relative">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
            </div>
          ) : failedCount > 0 ? (
            <XCircle className="h-3.5 w-3.5 text-red-500" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-primary/60" />
          )}
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            {t("chat.turnLabel", { turn: group.turn })}
          </span>
          <span className="text-[9px] text-muted-foreground/50 font-mono">
            {group.isStreaming
              ? `${runningCount} RUNNING`
              : `${doneCount} DONE`}
          </span>
        </div>
        <ChevronRight className={`h-3 w-3 text-muted-foreground/30 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`} />
      </button>
      
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="pb-3 space-y-1">
              {group.steps.map((step, i) => (
                <StepRow key={step.id || i} step={step} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function StepRow({ step }: { step: ToolStep }) {
  const { t } = useTranslation()
  const isRunning = step.status === "running"
  const isFailed = step.status === "failed"
  const isCompleted = step.status === "completed" || step.status === "done"

  const [isOpen, setIsOpen] = useState(isRunning)

  useEffect(() => {
    if (isRunning) setIsOpen(true)
    if (isCompleted) setIsOpen(false)
  }, [isRunning, isCompleted])

  return (
    <motion.div 
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="relative pl-6 py-2 group border-l border-transparent hover:border-primary/10 transition-colors"
    >
      <div className="absolute left-[-1.5px] top-0 bottom-0 w-[1px] bg-border/20 group-hover:bg-primary/20" />
      <div className={`absolute left-[-4.5px] top-4 w-2 h-2 rounded-full border-2 border-background z-10 transition-colors ${
        isRunning ? 'bg-primary' : isFailed ? 'bg-red-500' : isCompleted ? 'bg-primary/40' : 'bg-muted'
      }`} />

      <div 
        className="flex items-center gap-2 cursor-pointer select-none"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-tight flex-1 truncate font-mono">
          {step.name || step.tool_name || t("chat.messageList.toolExecution")}
        </span>
        <div className="flex items-center gap-2">
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

      <AnimatePresence>
        {isOpen && step.input && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-1.5 p-2 bg-muted/20 rounded-sm text-[10px] font-mono text-muted-foreground/70 break-all border border-border/10 leading-relaxed shadow-inner">
              {typeof step.input === "string" 
                ? step.input 
                : JSON.stringify(step.input, null, 2)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
