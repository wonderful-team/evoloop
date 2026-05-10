import { ChevronRight, Home, Loader2 } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { useQuery } from "@tanstack/react-query"
import { PlanningService } from "@/client"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"

export const BreadcrumbStatus = memo(() => {
    const { t } = useTranslation()
    const currentProject = useProjectStore((s) => s.currentProject)
    const threadId = useChatStore((s) => s.threadId)
    const status = useChatStore((s) => s.status)
    const agentState = useChatStore((s) => s.agentState)

    // Fetch Plan
    const { data: planData } = useQuery({
        queryKey: ["threadPlan", threadId],
        queryFn: async () => {
            if (!threadId) return null
            return PlanningService.getPlan({ threadId })
        },
        enabled: !!threadId,
        staleTime: 5000,
    })

    // Use 'any' type casting to avoid strict type issues if types aren't fully synced
    // Assuming response structure: { plan: { title, steps: [...] }, ... }
    const typedPlan = planData as any
    const planTitle = typedPlan?.plan?.title
    const sessionGoal = useChatStore((s) => s.sessionGoal)
    const activeStep = typedPlan?.plan?.steps?.find((s: any) => s.status === "in_progress")

    // Decide what to show
    const displayTitle = planTitle || sessionGoal

    if (!currentProject) return null

    const isRunning = status === "running" || status === "summarizing"

    return (
        <div className="flex items-center text-xs text-muted-foreground px-4 py-2 border-b bg-muted/20 select-none overflow-hidden">
            {/* Project */}
            <div className="flex items-center whitespace-nowrap hover:text-foreground transition-colors cursor-default">
                <Home size={12} className="mr-1.5 opacity-70" />
                <span className="font-medium max-w-[120px] truncate">
                    {currentProject.name}
                </span>
            </div>

            {/* Separator */}
            <ChevronRight size={12} className="mx-2 opacity-50 shrink-0" />

            {/* Plan / Goal */}
            {displayTitle ? (
                <div className="flex items-center whitespace-nowrap hover:text-foreground transition-colors cursor-default min-w-0">
                    <span className="truncate max-w-[200px]" title={displayTitle}>
                        {displayTitle}
                    </span>
                </div>
            ) : (
                <span className="opacity-50 italic">
                    {t("chat.status.ready", "Ready")}
                </span>
            )}

            {/* Active Step (Only if running or active plan) */}
            {(activeStep || isRunning) && (
                <>
                    <ChevronRight size={12} className="mx-2 opacity-50 shrink-0" />
                    <div className="flex items-center text-primary whitespace-nowrap min-w-0 animate-in fade-in slide-in-from-left-2">
                        {isRunning && <Loader2 size={10} className="mr-1.5 animate-spin" />}
                        <span className="font-medium truncate" title={activeStep?.description || agentState?.task_name}>
                            {activeStep?.description || agentState?.task_name || (isRunning ? t("chat.status.working", "Working...") : "")}
                        </span>
                    </div>
                </>
            )}
        </div>
    )
})

BreadcrumbStatus.displayName = "BreadcrumbStatus"
