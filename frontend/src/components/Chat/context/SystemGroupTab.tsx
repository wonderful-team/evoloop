import { useQuery } from "@tanstack/react-query"
import { Cpu, Loader2, Wrench } from "lucide-react"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { PlanningService, ToolsService } from "@/client"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useChatStore } from "@/stores/chatStore"

interface SystemGroupTabProps {
    activeThreadId?: string
}

export function SystemGroupTab({ activeThreadId }: SystemGroupTabProps) {
    const { t } = useTranslation()

    // --- STATE & DATA ---

    // 1. TOOLS
    const steps = useChatStore((state) => state.steps)
    const activeTools = useMemo(() => {
        const toolSet = new Set<string>()
        steps.forEach((step) => {
            if (step.name && step.status === "running") {
                const toolPatterns = ["read_", "write_", "search_", "run_", "manage_", "create_", "delete_", "view_", "list_"]
                if (toolPatterns.some((p) => step.name.toLowerCase().includes(p))) {
                    toolSet.add(step.name.toLowerCase())
                }
                if (step.details) {
                    const match = step.details.match(/`([^`]+)`/)
                    if (match) toolSet.add(match[1].toLowerCase())
                }
            }
        })
        return toolSet
    }, [steps])

    const { data: tools, isLoading: isLoadingTools } = useQuery({
        queryKey: ["tools"],
        queryFn: async () => ToolsService.listRuntimeTools(),
    })

    // 2. STATE
    const { data: planData } = useQuery({
        queryKey: ["threadPlan", activeThreadId],
        queryFn: async () => {
            if (!activeThreadId) return null
            return PlanningService.getPlan({ threadId: activeThreadId })
        },
        enabled: !!activeThreadId,
    })
    const typedPlanData = planData as any

    // Helpers
    const isToolActive = (toolName: string) => {
        const lowerName = toolName.toLowerCase()
        return activeTools.has(lowerName) || Array.from(activeTools).some(at => lowerName.includes(at) || at.includes(lowerName))
    }

    return (
        <ScrollArea className="h-full bg-muted/5">
            <div className="p-3 space-y-4">

                {/* === CARD 1: RUNTIME TOOLS === */}
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
                    <div className="p-3 border-b flex items-center justify-between bg-muted/20">
                        <div className="flex items-center gap-2 font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                            <Wrench className="h-3.5 w-3.5" />
                            {t("chat.toolsTitle")}
                        </div>
                        {activeTools.size > 0 && (
                            <span className="text-[10px] bg-green-500/10 text-green-600 px-2 py-0.5 rounded-full font-medium animate-pulse border border-green-500/20">
                                {t("chat.toolsActive", { count: activeTools.size })}
                            </span>
                        )}
                    </div>

                    <div className="p-3">
                        {isLoadingTools ? (
                            <div className="flex justify-center"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
                        ) : tools && tools.length > 0 ? (
                            <div className="grid grid-cols-2 gap-2">
                                {[...tools]
                                    .sort((a: any, b: any) => {
                                        const aActive = isToolActive(a.name)
                                        const bActive = isToolActive(b.name)
                                        if (aActive && !bActive) return -1
                                        if (!aActive && bActive) return 1
                                        return 0
                                    })
                                    .map((tool: any, i: number) => {
                                        const active = isToolActive(tool.name)
                                        return (
                                            <div key={i} className={`flex items-center gap-2 p-2 rounded border text-xs transition-colors ${active ? "bg-primary/10 border-primary ring-1 ring-primary/30" : "bg-muted/10 border-transparent hover:bg-muted/20"}`}>
                                                <div className={`w-1.5 h-1.5 rounded-full ${active ? "bg-green-500 animate-pulse" : "bg-muted-foreground/30"}`} />
                                                <span className={`truncate font-mono ${active ? "font-semibold text-primary" : "text-muted-foreground"}`} title={tool.description}>
                                                    {tool.name}
                                                </span>
                                            </div>
                                        )
                                    })}
                            </div>
                        ) : (
                            <div className="text-xs text-muted-foreground italic text-center py-4">{t("chat.noTools")}</div>
                        )}
                    </div>
                </div>

                {/* === CARD 2: AGENT STATE === */}
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
                    <div className="p-3 border-b flex items-center justify-between bg-muted/20">
                        <div className="flex items-center gap-2 font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                            <Cpu className="h-3.5 w-3.5" />
                            {t("chat.context.stateTitle")}
                        </div>
                    </div>
                    <div className="p-3 space-y-3">
                        {!typedPlanData?.state ? (
                            <div className="text-xs text-muted-foreground italic text-center py-4">{t("chat.context.noState")}</div>
                        ) : (
                            <>
                                <div className="grid grid-cols-[80px_1fr] gap-2 text-xs">
                                    <span className="text-muted-foreground">{t("chat.stateProject")}:</span>
                                    <span className="font-mono">{typeof typedPlanData.state.project_id === "object" ? JSON.stringify(typedPlanData.state.project_id) : typedPlanData.state.project_id || "-"}</span>
                                    <span className="text-muted-foreground">{t("chat.stateWorkDir")}:</span>
                                    <span className="font-mono break-all text-xs">{typeof typedPlanData.state.working_directory === "object" ? JSON.stringify(typedPlanData.state.working_directory) : typedPlanData.state.working_directory || "-"}</span>
                                </div>

                                <div>
                                    <div className="text-[10px] font-semibold text-muted-foreground uppercase mb-1.5">{t("chat.stateScratchpad")}</div>
                                    <div className="bg-muted/50 p-2 rounded border text-[10px] font-mono whitespace-pre-wrap break-words min-h-[60px] max-h-[200px] overflow-y-auto">
                                        {typeof typedPlanData.state.scratchpad === "object" ? JSON.stringify(typedPlanData.state.scratchpad, null, 2) : typedPlanData.state.scratchpad || t("chat.stateEmpty")}
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </div>

            </div>
        </ScrollArea>
    )
}
