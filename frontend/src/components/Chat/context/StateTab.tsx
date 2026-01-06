import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { PlanningService } from "@/client"
import { ScrollArea } from "@/components/ui/scroll-area"

interface StateTabProps {
  activeThreadId?: string
}

export function StateTab({ activeThreadId }: StateTabProps) {
  const { t } = useTranslation()

  // Reuse query data from PlanTab (same key)
  const { data: planData } = useQuery({
    queryKey: ["threadPlan", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return null
      return PlanningService.getPlan({ threadId: activeThreadId })
    },
    enabled: !!activeThreadId,
  })

  const typedPlanData = planData as any

  return (
    <div className="h-full m-0 flex flex-col">
      <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
        <span className="text-xs font-medium text-muted-foreground">
          {t("chat.context.stateTitle")}
        </span>
      </div>
      <ScrollArea className="flex-1 p-3">
        {!typedPlanData?.state ? (
          <div className="text-center text-xs text-muted-foreground py-8">
            {t("chat.context.noState")}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase">
                Context
              </div>
              <div className="grid grid-cols-[80px_1fr] gap-2 text-xs">
                <span className="text-muted-foreground">Project:</span>
                <span className="font-mono">
                  {typeof typedPlanData.state.project_id === "object"
                    ? JSON.stringify(typedPlanData.state.project_id)
                    : typedPlanData.state.project_id || "-"}
                </span>
                <span className="text-muted-foreground">Work Dir:</span>
                <span className="font-mono break-all">
                  {typeof typedPlanData.state.working_directory === "object"
                    ? JSON.stringify(typedPlanData.state.working_directory)
                    : typedPlanData.state.working_directory || "-"}
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase">
                Scratchpad
              </div>
              <div className="bg-muted/50 p-2 rounded-md border text-xs font-mono whitespace-pre-wrap break-words min-h-[100px]">
                {typeof typedPlanData.state.scratchpad === "object"
                  ? JSON.stringify(typedPlanData.state.scratchpad, null, 2)
                  : typedPlanData.state.scratchpad || "Empty"}
              </div>
            </div>
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
