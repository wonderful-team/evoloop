import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { cn } from "@evoloop/shared/lib/utils"
import { useQuery } from "@tanstack/react-query"
import {
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Cpu,
  GitBranch,
  Loader2,
  Map as MapIcon,
  MonitorSmartphone,
  Wrench,
} from "lucide-react"
import { memo, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { PlanningService } from "@/client"
import { LearningService } from "@/client/sdk.gen"
import { SkillDetailsPanel } from "@/components/Learning/SkillDetailsPanel"
import { executeSkillErrorMessage } from "@/components/Learning/skillLifecycle"
import { useAgentStore } from "@/stores/agentStore"
import { useChatStore } from "@/stores/chatStore"
import type { LearnedSkill } from "@/types/skill"
import { MessageContent } from "../MessageContent"

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

interface ActivityTabProps {
  activeThreadId?: string
}

const SUBAGENT_STATUS_STYLE: Record<string, { dot: string; labelKey: string }> =
  {
    started: {
      dot: "bg-warning animate-pulse",
      labelKey: "chat.subagentRunning",
    },
    completed: { dot: "bg-success", labelKey: "chat.subagentCompleted" },
    failed: { dot: "bg-destructive", labelKey: "chat.subagentFailed" },
    cancelled: {
      dot: "bg-muted-foreground",
      labelKey: "chat.subagentCancelled",
    },
  }

const A2A_STATUS_STYLE: Record<string, { dot: string; labelKey: string }> = {
  started: {
    dot: "bg-warning animate-pulse",
    labelKey: "chat.a2aWaitingCallback",
  },
  completed: { dot: "bg-success", labelKey: "chat.a2aCompleted" },
  failed: { dot: "bg-destructive", labelKey: "chat.a2aFailed" },
  timeout: { dot: "bg-warning", labelKey: "chat.a2aTimeout" },
  cancelled: {
    dot: "bg-muted-foreground",
    labelKey: "chat.a2aCancelled",
  },
}

/**
 * ActivityTab — Agent execution dashboard.
 */
export function ActivityTab({ activeThreadId }: ActivityTabProps) {
  const { t } = useTranslation()
  const agentState = useAgentStore((state) => state.agentState)
  const status = useAgentStore((state) => state.status)
  const isAgentActive =
    status === "running" || status === "interrupted" || status === "summarizing"

  const {
    data: planData,
    isLoading: isLoadingPlan,
    refetch: refetchPlan,
  } = useQuery({
    queryKey: ["threadPlan", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return null
      return PlanningService.getPlan({ threadId: activeThreadId })
    },
    enabled: !!activeThreadId,
  })

  useEffect(() => {
    const handlePlanUpdate = () => {
      if (activeThreadId) {
        refetchPlan()
      }
    }
    window.addEventListener("chat-plan-updated", handlePlanUpdate)
    return () =>
      window.removeEventListener("chat-plan-updated", handlePlanUpdate)
  }, [activeThreadId, refetchPlan])

  const typedPlanData = planData as any
  const plan = typedPlanData?.plan as Plan | null
  const planStatus = typedPlanData?.status

  /**
   * Active skills shown in the panel.
   * Driven ONLY by backend via AgentStateEvent.active_skills or persisted ActivitySnapshot.
   * No client-side fallback/deduction to ensure 100% strict alignment with backend.
   */
  const matchingSkills = useMemo(() => {
    return agentState?.activeSkills ?? []
  }, [agentState?.activeSkills])

  const isLoadingSkills = false

  const [planOpen, setPlanOpen] = useState(false)
  const [skillsOpen, setSkillsOpen] = useState(false)

  const planInteracted = useRef(false)
  const skillsInteracted = useRef(false)

  // Controlled by user after initial mount, otherwise auto-expand/collapse based on data
  useEffect(() => {
    if (!planInteracted.current) {
      setPlanOpen(!!plan)
    }
  }, [!!plan])

  const hasSkills = matchingSkills.length > 0
  useEffect(() => {
    if (!skillsInteracted.current) {
      setSkillsOpen(hasSkills)
    }
  }, [hasSkills])

  const subagents = useAgentStore((state) => state.subagents)
  const activeSubagentDetail = useAgentStore(
    (state) => state.activeSubagentDetail,
  )
  const [subagentsOpen, setSubagentsOpen] = useState(false)
  const subagentsInteracted = useRef(false)
  const hasSubagents = subagents.length > 0
  useEffect(() => {
    if (!subagentsInteracted.current) {
      setSubagentsOpen(hasSubagents)
    }
  }, [hasSubagents])

  const a2aDelegations = useAgentStore((state) => state.a2aDelegations)
  const activeA2ADetail = useAgentStore((state) => state.activeA2ADetail)
  const [a2aOpen, setA2AOpen] = useState(false)
  const a2aInteracted = useRef(false)
  const hasA2A = a2aDelegations.length > 0
  useEffect(() => {
    if (!a2aInteracted.current) {
      setA2AOpen(hasA2A)
    }
  }, [hasA2A])

  const sessionGoal = useChatStore((state) => state.sessionGoal)
  const [goalOpen, setGoalOpen] = useState(true)

  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(null)
  const [isSkillPanelOpen, setIsSkillPanelOpen] = useState(false)
  const [thinkingOpen, setThinkingOpen] = useState(true)

  const { data: fullSkill } = useQuery({
    queryKey: ["learnedSkill", selectedSkillId],
    queryFn: () => LearningService.getSkill({ skillId: selectedSkillId! }),
    enabled: !!selectedSkillId && isSkillPanelOpen,
  })

  const handleRunSkill = async (skill: LearnedSkill) => {
    if (!activeThreadId) {
      toast.error(t("learning.macroRun.openChatFirst"))
      return
    }
    try {
      await LearningService.runSkill({
        skillId: skill.id,
        requestBody: {
          thread_id: activeThreadId,
          params: {
            _allow_self_healing: skill.allow_self_healing !== false,
          },
        },
      })
      toast.success(t("learning.executionStarted"))
    } catch (error) {
      console.error("Execution failed", error)
      toast.error(
        executeSkillErrorMessage(error) ?? t("learning.executionFailed"),
      )
    }
  }

  return (
    <div className="h-full w-full min-w-0 flex flex-col bg-muted/5 overflow-hidden">
      <ScrollArea
        className={cn(
          "w-full transition-all duration-300",
          thinkingOpen ? "shrink-0 max-h-[50%]" : "flex-1 min-h-0",
        )}
      >
        <div className="flex flex-col w-full">
          {/* === BLOCK 0: GOAL === */}
          {sessionGoal && (
            <Collapsible
              open={goalOpen}
              onOpenChange={setGoalOpen}
              className="flex flex-col border-b border-border transition-[border-color] duration-200 shrink-0"
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
              <CollapsibleContent>
                <div className="p-3 text-xs text-foreground leading-relaxed font-medium bg-background/50 border-b border-border/50">
                  {sessionGoal}
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}
          {/* === BLOCK 1: PLAN === */}
          <Collapsible
            open={planOpen}
            onOpenChange={(open) => {
              planInteracted.current = true
              setPlanOpen(open)
            }}
            className="flex flex-col border-b border-border transition-[border-color] duration-200 shrink-0"
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
            <CollapsibleContent>
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
                              ? "border-warning"
                              : "border-muted"
                        } ${step.execution_run_id ? "cursor-pointer hover:bg-muted/10 pr-2 rounded-r" : ""}`}
                      >
                        <div className="text-xs font-medium flex items-center gap-2">
                          <span
                            className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                              step.status === "completed"
                                ? "bg-primary text-primary-foreground"
                                : step.status === "in_progress"
                                  ? "bg-warning text-white"
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

          {/* === BLOCK 2: USED SKILLS === */}
          <Collapsible
            open={skillsOpen}
            onOpenChange={(open) => {
              skillsInteracted.current = true
              setSkillsOpen(open)
            }}
            className="flex flex-col border-b border-border transition-[border-color] duration-200 shrink-0"
          >
            <CollapsibleTrigger asChild>
              <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
                {skillsOpen ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <Cpu className="h-3.5 w-3.5 text-primary/70 shrink-0" />
                <span className="text-[10px] font-bold text-muted-foreground flex-1">
                  {t("chat.usedSkillsTitle")}
                </span>
                {matchingSkills.length > 0 && (
                  <span className="text-[10px] text-muted-foreground font-mono bg-muted px-1.5 py-0.5 rounded-sm">
                    {matchingSkills.length}
                  </span>
                )}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="p-2">
                {isLoadingSkills ? (
                  <div className="flex justify-center p-4">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : matchingSkills.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic text-center py-6 border-2 border-dashed rounded-md mx-2">
                    {t("chat.noUsedSkills")}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {matchingSkills.map((skill: any) => (
                      <div
                        key={skill.id}
                        className="flex items-start gap-2.5 p-2 rounded-lg bg-muted/20 border border-border/30 hover:bg-muted/30 transition-colors cursor-pointer"
                        onClick={() => {
                          setSelectedSkillId(skill.id)
                          setIsSkillPanelOpen(true)
                        }}
                      >
                        <Wrench className="h-3.5 w-3.5 text-primary/60 shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold text-foreground truncate">
                            {skill.name}
                          </div>
                          {skill.description && (
                            <div className="text-[10px] text-muted-foreground line-clamp-2 mt-0.5 leading-normal">
                              {skill.description}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* === BLOCK 2.5: SUBAGENTS === */}
          <Collapsible
            open={subagentsOpen}
            onOpenChange={(open) => {
              subagentsInteracted.current = true
              setSubagentsOpen(open)
            }}
            className="flex flex-col border-b border-border transition-[border-color] duration-200 shrink-0"
          >
            <CollapsibleTrigger asChild>
              <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
                {subagentsOpen ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <GitBranch className="h-3.5 w-3.5 text-primary/70 shrink-0" />
                <span className="text-[10px] font-bold text-muted-foreground flex-1">
                  {t("chat.subagentsTitle")}
                </span>
                {hasSubagents && (
                  <span className="text-[10px] text-primary shrink-0">
                    {t("chat.subagentActive")}
                  </span>
                )}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="p-2 space-y-2">
                {subagents.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic text-center py-6 border-2 border-dashed rounded-md mx-2">
                    {t("chat.noSubagents")}
                  </div>
                ) : (
                  subagents.map((s) => {
                    const style =
                      SUBAGENT_STATUS_STYLE[s.status] ??
                      SUBAGENT_STATUS_STYLE.started
                    const isActive =
                      activeSubagentDetail === s.subagent_thread_id
                    return (
                      <button
                        type="button"
                        key={s.subagent_thread_id}
                        onClick={() =>
                          useAgentStore
                            .getState()
                            ._openSubagentDetail(s.subagent_thread_id)
                        }
                        className={`flex items-start gap-2.5 p-2 rounded-lg border transition-colors cursor-pointer text-left w-full font-inherit ${
                          isActive
                            ? "bg-primary/10 border-primary/40"
                            : "bg-muted/20 border-border/30 hover:bg-muted/30"
                        }`}
                      >
                        <span
                          className={`mt-1 h-2 w-2 rounded-full shrink-0 ${style.dot}`}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-foreground line-clamp-2">
                            {s.instruction || s.subagent_id}
                          </div>
                          <div className="text-[10px] text-muted-foreground mt-0.5">
                            {t(style.labelKey)}
                          </div>
                        </div>
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-1" />
                      </button>
                    )
                  })
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* === BLOCK 2.6: A2A DELEGATIONS === */}
          <Collapsible
            open={a2aOpen}
            onOpenChange={(open) => {
              a2aInteracted.current = true
              setA2AOpen(open)
            }}
            className="flex flex-col border-b border-border transition-[border-color] duration-200 shrink-0"
          >
            <CollapsibleTrigger asChild>
              <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors bg-muted/20 shrink-0">
                {a2aOpen ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <MonitorSmartphone className="h-3.5 w-3.5 text-primary/70 shrink-0" />
                <span className="text-[10px] font-bold text-muted-foreground flex-1">
                  {t("chat.a2aTitle")}
                </span>
                {hasA2A && (
                  <span className="text-[10px] text-primary shrink-0">
                    {t("chat.a2aActive")}
                  </span>
                )}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="p-2 space-y-2">
                {a2aDelegations.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic text-center py-6 border-2 border-dashed rounded-md mx-2">
                    {t("chat.noA2ADelegations")}
                  </div>
                ) : (
                  a2aDelegations.map((d) => {
                    const style =
                      A2A_STATUS_STYLE[d.status] ?? A2A_STATUS_STYLE.started
                    const isActive = activeA2ADetail === d.task_id
                    return (
                      <button
                        type="button"
                        key={d.task_id}
                        onClick={() =>
                          useAgentStore.getState()._openA2ADetail(d.task_id)
                        }
                        className={`flex items-start gap-2.5 p-2 rounded-lg border transition-colors cursor-pointer text-left w-full font-inherit ${
                          isActive
                            ? "bg-primary/10 border-primary/40"
                            : "bg-muted/20 border-border/30 hover:bg-muted/30"
                        }`}
                      >
                        <span
                          className={`mt-1 h-2 w-2 rounded-full shrink-0 ${style.dot}`}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-foreground line-clamp-2">
                            {d.instruction || d.task_id}
                          </div>
                          <div className="text-[10px] text-muted-foreground mt-0.5">
                            {d.target_device_name || d.target_device_key} ·{" "}
                            {t(style.labelKey)}
                          </div>
                        </div>
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-1" />
                      </button>
                    )
                  })
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </ScrollArea>

      {/* === BLOCK 3: THINKING === */}
      <ThinkingBlock
        isAgentActive={isAgentActive}
        thinkingOpen={thinkingOpen}
        setThinkingOpen={setThinkingOpen}
      />

      <SkillDetailsPanel
        skill={(fullSkill as any) || null}
        open={isSkillPanelOpen}
        onOpenChange={(open) => {
          setIsSkillPanelOpen(open)
          if (!open) setTimeout(() => setSelectedSkillId(null), 200)
        }}
        onRun={handleRunSkill}
      />
    </div>
  )
}

const ThinkingBlock = memo(
  ({
    isAgentActive,
    thinkingOpen,
    setThinkingOpen,
  }: {
    isAgentActive: boolean
    thinkingOpen: boolean
    setThinkingOpen: (val: boolean) => void
  }) => {
    const { t } = useTranslation()
    const streamingThinking = useAgentStore((state) => state.streamingThinking)
    const thinking = useChatStore((state) => {
      if (streamingThinking && streamingThinking.trim().length > 0)
        return streamingThinking.trim()
      for (let i = state.messages.length - 1; i >= 0; i--) {
        if (state.messages[i].role === "ai") {
          return (state.messages[i].thinking || "").trim()
        }
      }
      return ""
    })

    const bottomRef = useRef<HTMLDivElement>(null)
    const [isAutoScroll, setIsAutoScroll] = useState(true)

    useEffect(() => {
      if (isAutoScroll && bottomRef.current) {
        bottomRef.current.scrollIntoView({ behavior: "instant", block: "end" })
      }
    }, [thinking, isAutoScroll])

    useEffect(() => {
      if (isAgentActive) {
        setIsAutoScroll(true)
      }
    }, [isAgentActive])

    const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
      const target = e.currentTarget
      const isAtBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight < 50
      setIsAutoScroll(isAtBottom)
    }

    return (
      <Collapsible
        open={thinkingOpen}
        onOpenChange={setThinkingOpen}
        className={cn(
          "flex flex-col min-w-0 w-full overflow-hidden border-border transition-all duration-300",
          thinkingOpen ? "flex-1 min-h-0" : "shrink-0",
        )}
      >
        <CollapsibleTrigger asChild>
          <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors shrink-0 w-full overflow-hidden bg-muted/20">
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
        <CollapsibleContent className="flex-1 min-w-0 w-full overflow-hidden flex flex-col data-[state=closed]:hidden">
          <div
            onScroll={handleScroll}
            className="flex-1 p-2 min-w-0 w-full overflow-y-auto"
          >
            {thinking && thinking.trim().length > 0 ? (
              <div className="text-xs text-muted-foreground break-words leading-relaxed min-w-0 w-full overflow-hidden [word-break:break-word] whitespace-pre-wrap">
                <MessageContent content={thinking} />
              </div>
            ) : (
              <div className="text-xs text-muted-foreground italic text-center py-4">
                {isAgentActive
                  ? t("chat.thinkingWaiting")
                  : t("chat.noThinking")}
              </div>
            )}
            <div ref={bottomRef} className="h-1 w-full shrink-0" />
          </div>
        </CollapsibleContent>
      </Collapsible>
    )
  },
)
ThinkingBlock.displayName = "ThinkingBlock"
