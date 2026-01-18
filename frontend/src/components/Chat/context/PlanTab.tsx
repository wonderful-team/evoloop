import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { PlanningService } from "@/client"
import { ScrollArea } from "@/components/ui/scroll-area"

interface PlanStep {
  id: string
  title: string
  status: "pending" | "in_progress" | "completed" | "failed"
  result?: string
  execution_run_id?: string // Deep Linking
}

interface Plan {
  id: string
  title: string
  steps: PlanStep[]
  current_step_id?: string
}

interface PlanTabProps {
  activeThreadId?: string
}

export function PlanTab({ activeThreadId }: PlanTabProps) {
  const { t } = useTranslation()

  // 2. Active Plan
  const { data: planData, isLoading: isLoadingPlan } = useQuery({
    queryKey: ["threadPlan", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return null
      return PlanningService.getPlan({ threadId: activeThreadId })
    },
    enabled: !!activeThreadId,
    refetchInterval: 3000, // Poll when plan tab is open
  })

  // Safety check for plan structure
  const typedPlanData = planData as any
  const plan = typedPlanData?.plan as Plan | null
  const planStatus = typedPlanData?.status

  return (
    <div className="h-full m-0 flex flex-col">
      <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
        <span className="text-xs font-medium text-muted-foreground">
          {t("chat.context.planTitle")}
        </span>
        <span className="text-[10px] uppercase font-bold text-muted-foreground/50">
          {planStatus === "no_graph"
            ? t("chat.context.statusOffline")
            : (planStatus === "no_state" || planStatus === "no_plan")
              ? t("chat.context.statusIdle")
              : t("chat.context.statusActive")}
        </span>
      </div>
      <ScrollArea className="flex-1 p-3">
        {isLoadingPlan ? (
          <div className="flex justify-center p-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : !plan ? (
          <div className="text-center text-xs text-muted-foreground py-8 border-2 border-dashed rounded-md">
            {t("chat.context.noPlan")}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="font-medium text-sm border-b pb-2">
              {plan.title}
            </div>
            <div className="space-y-3">
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
                  className={`relative pl-4 border-l-2 transition-colors ${step.status === "completed"
                    ? "border-primary"
                    : step.status === "in_progress"
                      ? "border-yellow-500"
                      : "border-muted"
                    } ${step.execution_run_id ? "cursor-pointer hover:bg-muted/10 pr-2 rounded-r" : ""}`}
                >
                  <div className="text-xs font-medium flex items-center gap-2">
                    <span
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${step.status === "completed"
                        ? "bg-primary text-primary-foreground"
                        : step.status === "in_progress"
                          ? "bg-yellow-500 text-white"
                          : "bg-muted text-muted-foreground"
                        }`}
                    >
                      {idx + 1}
                    </span>
                    <span className={step.execution_run_id ? "underline decoration-dotted underline-offset-2" : ""}>
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
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
