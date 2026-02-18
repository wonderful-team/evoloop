import React, { useState } from "react"
import { useTranslation } from "react-i18next"
import {
    History,
    HelpCircle,
    LayoutTemplate,
    Code2,
    Plus,
    Trash2
} from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { SimpleStepCard } from "./SimpleStepCard"
import { StepActionSelector } from "./StepActionSelector"
import { DebugPanel } from "./DebugPanel"
import { useChatStore } from "@/stores/chatStore"
import type { SkillStep } from "@/types/skill"
import type { ParamDef } from "./EditorSidebar"

interface LogicWorkspaceProps {
    steps: SkillStep[]
    params: ParamDef[]
    isSimpleMode: boolean
    setIsSimpleMode: (val: boolean) => void
    handleAddStepWithIndex: (path?: number[], step?: SkillStep) => void
    handleUpdateStep: (path: number[], newStep: SkillStep) => void
    handleDeleteStep: (path: number[]) => void
    handleMoveStep: (path: number[], direction: 'up' | 'down') => void
    showPreview: boolean
    setShowPreview: (val: boolean) => void
}

export const LogicWorkspace: React.FC<LogicWorkspaceProps> = ({
    steps,
    params,
    isSimpleMode,
    setIsSimpleMode,
    handleAddStepWithIndex,
    handleUpdateStep,
    handleDeleteStep,
    handleMoveStep,
    showPreview,
    setShowPreview,
}) => {
    const { t } = useTranslation()
    const { agentState } = useChatStore()
    const [actionSelectorOpen, setActionSelectorOpen] = useState(false)
    const [insertPath, setInsertPath] = useState<number[] | undefined>(undefined)

    const activePath = agentState?.details?.type === "debug" ? agentState.details.step_path : null;

    const isActive = (path: number[]) => {
        if (!activePath) return false;
        if (path.length !== activePath.length) return false;
        return path.every((v, i) => v === activePath[i]);
    };

    const openActionSelector = (path?: number[]) => {
        setInsertPath(path)
        setActionSelectorOpen(true)
    }

    const handleActionSelect = (step: SkillStep) => {
        handleAddStepWithIndex(insertPath, step)
    }

    const renderSteps = (stepsToRender: SkillStep[], parentPath: number[] = []) => {
        return stepsToRender.map((step, i) => {
            const currentPath = [...parentPath, i];
            const isLogic = ["loop", "condition", "group"].includes(step.action);

            return (
                <SimpleStepCard
                    key={(step as any).step_id || `${currentPath.join("-")}-${step.action}`}
                    step={step}
                    index={i}
                    path={currentPath}
                    isActive={isActive(currentPath)}
                    totalSteps={stepsToRender.length}
                    availableParams={params}
                    onUpdate={(newStep) => handleUpdateStep(currentPath, newStep)}
                    onDelete={() => handleDeleteStep(currentPath)}
                    onMove={(dir) => handleMoveStep(currentPath, dir)}
                    onInsert={() => openActionSelector([...parentPath, i + 1])}
                    onAddInner={() => openActionSelector([...currentPath, 0])}
                >
                    {isLogic && (step.children || []).length > 0 && (
                        renderSteps(step.children || [], currentPath)
                    )}
                </SimpleStepCard>
            );
        });
    }

    return (
        <div className="flex-1 flex flex-col bg-background relative overflow-hidden transition-all border-r">
            <div className="h-[52px] px-4 border-b bg-muted/5 flex items-center justify-between sticky top-0 z-20 backdrop-blur-sm shrink-0">
                <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-primary/10 rounded-lg">
                        <History className="h-4 w-4 text-primary" />
                    </div>
                    <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80 flex items-center gap-2">
                        {t("learning.steps")}
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <HelpCircle
                                        className="h-3.5 w-3.5 text-muted-foreground/40 cursor-help hover:text-primary transition-colors" />
                                </TooltipTrigger>
                                <TooltipContent side="right">
                                    {t("learning.editor.logicHelp")}
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </h3>
                    <Badge variant="secondary" className="font-mono text-[11px] ml-2">{steps.length} Steps</Badge>
                </div>
                <div className="flex items-center gap-2">
                    <div className="flex items-center bg-muted/30 p-1 rounded-lg border gap-1">
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="flex">
                                        <Button
                                            variant={isSimpleMode ? "secondary" : "ghost"}
                                            size="sm"
                                            className={`h-7 px-3 text-[11px] font-bold gap-1 ${isSimpleMode ? "bg-background shadow-sm text-primary" : "text-muted-foreground"}`}
                                            onClick={() => setIsSimpleMode(true)}
                                        >
                                            <LayoutTemplate className="h-3 w-3" />
                                            {t("skills.editor.simpleMode", "Simple")}
                                        </Button>
                                        <Button
                                            variant={!isSimpleMode ? "secondary" : "ghost"}
                                            size="sm"
                                            className={`h-7 px-3 text-[11px] font-bold gap-1 ${!isSimpleMode ? "bg-background shadow-sm text-primary" : "text-muted-foreground"}`}
                                            onClick={() => setIsSimpleMode(false)}
                                        >
                                            <Code2 className="h-3 w-3" />
                                            {t("skills.editor.jsonMode", "JSON")}
                                        </Button>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-[200px]">{t("learning.editor.modeHelp")}</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </div>

                    <Button
                        size="sm"
                        variant="outline"
                        className="h-9 px-4 text-xs font-bold gap-2 bg-primary/5 hover:bg-primary/10 border-primary/20 rounded-xl"
                        onClick={() => openActionSelector()}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        {t("learning.editor.addStep")}
                    </Button>
                </div>
            </div>

            <ScrollArea className="flex-1">
                <div className="p-6 space-y-6 pb-20">
                    {steps.length === 0 && (
                        <div className="text-center py-20 opacity-20 flex flex-col items-center border-2 border-dashed rounded-3xl mt-10 mx-6">
                            <History className="h-16 w-16 mb-4" />
                            <p className="text-[11px] font-bold uppercase tracking-widest opacity-70">{t("learning.editor.noLogic")}</p>
                        </div>
                    )}

                    {isSimpleMode ? (
                        <div className="space-y-4">
                            {renderSteps(steps)}
                        </div>
                    ) : (
                        <div className="space-y-4 ml-4">
                            {steps.map((step, i) => (
                                <div key={i} className="relative pl-10 pb-6 last:pb-0 border-l-2 border-primary/20 hover:border-primary/50 transition-all">
                                    <div className="absolute left-[-11px] top-0 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-[10px] text-white font-bold shadow-lg shadow-primary/20 z-10">
                                        {i + 1}
                                    </div>
                                    <div className="bg-card border rounded-xl p-4 shadow-sm hover:border-primary/30 transition-all group">
                                        <div className="flex items-center justify-between mb-3">
                                            <span className="text-sm font-bold text-primary px-2 py-0.5 rounded-md bg-primary/5">{step.action}</span>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-all text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                                                onClick={() => handleDeleteStep([i])}
                                            >
                                                <Trash2 className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                        <div className="bg-black/5 p-3 rounded-xl text-[10px] font-mono border border-black/5 whitespace-pre overflow-x-auto text-muted-foreground/80">
                                            {JSON.stringify(step, null, 2)}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </ScrollArea>

            {showPreview && (
                <div className="absolute right-0 top-0 bottom-0 z-30 animate-in slide-in-from-right duration-300">
                    <DebugPanel onClose={() => setShowPreview(false)} />
                </div>
            )}

            <StepActionSelector
                open={actionSelectorOpen}
                onOpenChange={setActionSelectorOpen}
                onSelect={handleActionSelect}
            />
        </div>
    )
}
