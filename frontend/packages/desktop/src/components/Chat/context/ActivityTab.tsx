import { useEffect, useMemo, useState } from "react"
import {
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Cpu,
  Loader2,
  Map as MapIcon,
  Wrench,
} from "lucide-react"
import { MessageContent } from "../MessageContent"
import { useTranslation } from "react-i18next"
import { PlanningService, LearningService } from "@/client"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { useChatStore } from "@/stores/chatStore"
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
  const skillIds = useChatStore((state) => state.skillIds)

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

  // Extract all used skill IDs from store and message references
  const usedSkillIds = useMemo(() => {
    const ids = new Set<number>()
    // Add skillIds from store
    for (const id of skillIds) {
      ids.add(Number(id))
    }
    // Add skillIds from message references
    for (const msg of messages) {
      if (msg.references) {
        for (const ref of msg.references) {
          if (ref.type === "skill" && ref.target_id) {
            ids.add(Number(ref.target_id))
          }
        }
      }
    }
    return Array.from(ids)
  }, [skillIds, messages])

  // Fetch all active skills
  const { data: skillsCatalog, isLoading: isLoadingSkills } = useQuery({
    queryKey: ["activeSkillsCatalog"],
    queryFn: async () => {
      const res = await LearningService.listSkills({ activeOnly: true, pageSize: 100 }) as any
      return res?.data || res?.skills || []
    }
  })

  // Filter skills matching usedSkillIds
  const matchingSkills = useMemo(() => {
    if (!skillsCatalog || usedSkillIds.length === 0) return []
    return skillsCatalog.filter((skill: any) => usedSkillIds.includes(Number(skill.id)))
  }, [skillsCatalog, usedSkillIds])

  const [thinkingOpen, setThinkingOpen] = useState(true)
  const [planOpen, setPlanOpen] = useState(false)
  const [skillsOpen, setSkillsOpen] = useState(true)

  // Controlled by user after initial mount
  useEffect(() => {
    if (plan) setPlanOpen(true)
  }, [plan])

  useEffect(() => {
    if (matchingSkills.length > 0) setSkillsOpen(true)
  }, [matchingSkills.length])

  const sessionGoal = useChatStore((state) => state.sessionGoal)
  const [goalOpen, setGoalOpen] = useState(true)

  return (
    <div className="h-full w-full min-w-0 flex flex-col bg-muted/5 overflow-hidden">
        {/* === BLOCK 0: GOAL === */}
        {sessionGoal && (
          <Collapsible 
            open={goalOpen} 
            onOpenChange={setGoalOpen} 
            className={`flex flex-col min-h-0 border-b border-border transition-[border-color] duration-200 ${goalOpen ? "shrink-0" : "shrink-0"}`}
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
          className={`flex flex-col min-h-0 border-b border-border transition-[border-color] duration-200 ${planOpen ? "flex-1" : "shrink-0"}`}
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
          className={`flex flex-col min-h-0 min-w-0 w-full overflow-hidden border-b border-border transition-[border-color] duration-200 ${thinkingOpen ? "flex-1" : "shrink-0"}`}
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

        {/* === BLOCK 3: USED SKILLS === */}
        <Collapsible 
          open={skillsOpen} 
          onOpenChange={setSkillsOpen} 
          className={`flex flex-col min-h-0 ${skillsOpen ? "flex-1" : "shrink-0"}`}
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
          <CollapsibleContent className="flex-1 min-h-0 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
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
                        className="flex items-start gap-2.5 p-2 rounded-lg bg-muted/20 border border-border/30 hover:bg-muted/30 transition-colors"
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
            </ScrollArea>
          </CollapsibleContent>
        </Collapsible>
    </div>
  )
}
