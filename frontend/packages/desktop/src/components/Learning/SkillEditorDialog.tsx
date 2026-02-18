import {
    Loader2,
    Save,
    Settings2,
    Sparkles,
    Eye,
    Play,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Button } from "@evoloop/shared/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { EditorSidebar } from "./EditorSidebar"
import { LogicWorkspace } from "./LogicWorkspace"
import { EditorStatsPreview } from "./EditorStatsPreview"
import { useChatStore } from "@/stores/chatStore"
import type { LearnedSkill, SkillStep } from "@/types/skill"
import type { ParamDef } from "./EditorSidebar"

interface SkillEditorDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    skill: LearnedSkill
    onSuccess: () => void
}

export function SkillEditorDialog({
    open,
    onOpenChange,
    skill,
    onSuccess,
}: SkillEditorDialogProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [aiOptimizing, setAiOptimizing] = useState(false)
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [triggers, setTriggers] = useState<string[]>([])
    const [newTrigger, setNewTrigger] = useState("")
    const [params, setParams] = useState<ParamDef[]>([])
    const [steps, setSteps] = useState<SkillStep[]>([])
    const [isSimpleMode, setIsSimpleMode] = useState(true)
    const [showPreview, setShowPreview] = useState(false)

    useEffect(() => {
        if (open && skill) {
            const safeParse = (data: any, defaultVal: any) => {
                if (!data) return defaultVal;
                if (typeof data === 'string') {
                    try {
                        return JSON.parse(data);
                    } catch (e) {
                        console.error("Failed to parse", data, e);
                        return defaultVal;
                    }
                }
                return data;
            }

            setName(skill.name)
            setDescription(skill.description)
            setTriggers(safeParse(skill.trigger_patterns, []))
            setParams(safeParse(skill.parameters, []))
            setSteps(safeParse(skill.steps, []))
        }
    }, [open, skill])

    const handleAddTrigger = () => {
        if (!newTrigger.trim()) return
        if (triggers.includes(newTrigger.trim())) {
            setNewTrigger("")
            return
        }
        setTriggers([...triggers, newTrigger.trim()])
        setNewTrigger("")
    }

    const handleRemoveTrigger = (index: number) => {
        setTriggers(triggers.filter((_, i) => i !== index))
    }

    const handleAddParam = () => {
        setParams([...params, { name: "", type: "string", description: "" }])
    }

    const handleRemoveParam = (index: number) => {
        setParams(params.filter((_, i) => i !== index))
    }

    const handleParamChange = (index: number, field: keyof ParamDef, value: string) => {
        const newParams = [...params]
        newParams[index] = { ...newParams[index], [field]: value }
        setParams(newParams)
    }

    const updateStepByPath = (steps: SkillStep[], path: number[], newStep: SkillStep): SkillStep[] => {
        const [index, ...rest] = path;
        const newSteps = [...steps];
        if (rest.length === 0) {
            newSteps[index] = newStep;
        } else {
            newSteps[index] = {
                ...newSteps[index],
                children: updateStepByPath(newSteps[index].children || [], rest, newStep)
            };
        }
        return newSteps;
    }

    const deleteStepByPath = (steps: SkillStep[], path: number[]): SkillStep[] => {
        const [index, ...rest] = path;
        const newSteps = [...steps];
        if (rest.length === 0) {
            newSteps.splice(index, 1);
        } else {
            newSteps[index] = {
                ...newSteps[index],
                children: deleteStepByPath(newSteps[index].children || [], rest)
            };
        }
        return newSteps;
    }

    const addStepByPath = (steps: SkillStep[], path: number[], newStep: SkillStep): SkillStep[] => {
        if (path.length === 0) return [...steps, newStep];

        const [index, ...rest] = path;
        const newSteps = [...steps];
        if (rest.length === 0) {
            newSteps.splice(index, 0, newStep);
        } else {
            newSteps[index] = {
                ...newSteps[index],
                children: addStepByPath(newSteps[index].children || [], rest, newStep)
            };
        }
        return newSteps;
    }

    const handleUpdateStep = (path: number[], newStep: SkillStep) => {
        setSteps(updateStepByPath(steps, path, newStep))
    }

    const handleDeleteStep = (path: number[]) => {
        setSteps(deleteStepByPath(steps, path))
    }

    const handleAddStepWithIndex = (path?: number[], stepBody?: SkillStep) => {
        const newStep: SkillStep = stepBody || { action: "mobile_control", args: { action: "tap", x: 500, y: 1000 } }
        if (path) {
            setSteps(addStepByPath(steps, path, newStep))
        } else {
            setSteps([...steps, newStep])
        }
    }

    const handleMoveStep = (path: number[], direction: 'up' | 'down') => {
        const index = path[path.length - 1];
        const parentPath = path.slice(0, -1);

        const getParentList = (steps: SkillStep[], p: number[]): SkillStep[] => {
            if (p.length === 0) return steps;
            const [idx, ...rest] = p;
            return getParentList(steps[idx].children || [], rest);
        }

        const parentList = getParentList(steps, parentPath);
        if (direction === 'up' && index === 0) return
        if (direction === 'down' && index === parentList.length - 1) return

        const targetIndex = direction === 'up' ? index - 1 : index + 1

        const swapInList = (list: SkillStep[]): SkillStep[] => {
            const newList = [...list];
            const temp = newList[index];
            newList[index] = newList[targetIndex];
            newList[targetIndex] = temp;
            return newList;
        }

        if (parentPath.length === 0) {
            setSteps(swapInList(steps));
        } else {
            const updateParent = (currentSteps: SkillStep[], p: number[]): SkillStep[] => {
                const [idx, ...rest] = p;
                const newCurrent = [...currentSteps];
                if (rest.length === 0) {
                    newCurrent[idx] = {
                        ...newCurrent[idx],
                        children: swapInList(newCurrent[idx].children || [])
                    }
                } else {
                    newCurrent[idx] = {
                        ...newCurrent[idx],
                        children: updateParent(newCurrent[idx].children || [], rest)
                    }
                }
                return newCurrent;
            }
            setSteps(updateParent(steps, parentPath));
        }
    }

    const handleAiOptimize = async () => {
        setAiOptimizing(true)
        // Mock AI optimization delay
        await new Promise(resolve => setTimeout(resolve, 1500))

        // Simulating AI improvement
        const betterDescription = description || t("learning.editor.aiRefinedDesc", "AI refined description based on execution logic.")
        const autoPrefix = t("learning.editor.automatedPrefix", "automated ")
        if (!triggers.includes(autoPrefix + name.toLowerCase())) {
            setTriggers([...triggers, autoPrefix + name.toLowerCase()])
        }
        setDescription(betterDescription + t("learning.editor.optimizedSuffix", " (Optimized)"))

        setAiOptimizing(false)
        toast.success(t("common.success", "AI Refinement complete"))
    }

    const handleSave = async () => {
        if (!name.trim()) {
            toast.error(t("learning.editor.nameRequired"))
            return
        }

        for (const p of params) {
            if (!p.name.trim()) {
                toast.error(t("learning.editor.paramNameRequired"))
                return
            }
            if (/\s/.test(p.name)) {
                toast.error(t("learning.editor.paramNameNoSpaces"))
                return
            }
        }

        setLoading(true)
        try {
            await LearningService.updateSkill({
                skillId: skill.id,
                requestBody: {
                    name,
                    description,
                    trigger_patterns: triggers,
                    parameters: params as any[],
                    steps: steps as any[],
                } as any,
            })

            toast.success(t("common.saved"))
            onSuccess()
            onOpenChange(false)
        } catch (error: any) {
            console.error("Failed to update skill", error)
            toast.error(error.message || t("common.error.message"))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[1680px] w-[95vw] h-[85vh] flex flex-col p-0 overflow-hidden bg-background border shadow-2xl">
                <div className="flex h-full overflow-hidden">
                    <div className="flex-1 flex flex-col bg-background">
                        <DialogHeader className="p-6 border-b bg-background">
                            <div className="flex items-center justify-between">
                                <div className="space-y-1">
                                    <DialogTitle className="flex items-center gap-2 text-xl font-bold">
                                        <div className="p-2 bg-primary/10 rounded-xl">
                                            <Settings2 className="h-5 w-5 text-primary" />
                                        </div>
                                        <span className="truncate max-w-[500px]">
                                            {t("learning.editor.title", { name: skill.name })}
                                        </span>
                                    </DialogTitle>
                                    <DialogDescription className="text-xs px-1">
                                        {t("learning.editor.description")}
                                    </DialogDescription>
                                </div>
                                <div className="flex items-center gap-3">
                                    <Button
                                        variant={showPreview ? "secondary" : "outline"}
                                        size="sm"
                                        className={`gap-2 text-xs font-bold transition-all ${showPreview ? "bg-primary/10 border-primary/30 text-primary" : "border-primary/20"}`}
                                        onClick={() => setShowPreview(!showPreview)}
                                    >
                                        <Eye className={`h-3.5 w-3.5 ${showPreview ? "text-primary" : "text-muted-foreground"}`} />
                                        {showPreview ? t("learning.editor.hidePreview") : t("learning.editor.showPreview")}
                                    </Button>

                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="gap-2 text-xs font-bold border-emerald-500/20 text-emerald-600 hover:bg-emerald-50"
                                        onClick={async () => {
                                            if (!showPreview) setShowPreview(true);
                                            try {
                                                const threadId = useChatStore.getState().threadId || "debug-" + Date.now();
                                                await LearningService.executeSkill({
                                                    skillId: skill.id,
                                                    requestBody: {
                                                        thread_id: threadId,
                                                        params: {}, // In Phase 3 we will add parameter support for debug run
                                                    }
                                                });
                                                toast.success(t("learning.executionStarted", "Execution started"));
                                            } catch (e) {
                                                toast.error(t("learning.executionFailed", "Execution failed"));
                                            }
                                        }}
                                        disabled={loading}
                                    >
                                        <Play className="h-3.5 w-3.5 fill-current" />
                                        {t("learning.execution.runNow", "Run Skill")}
                                    </Button>

                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="gap-2 text-xs font-bold border-primary/20 hover:bg-primary/5"
                                        onClick={handleAiOptimize}
                                        disabled={aiOptimizing}
                                    >
                                        {aiOptimizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-primary" />}
                                        {t("learning.editor.aiOptimize")}
                                    </Button>
                                </div>
                            </div>
                        </DialogHeader>

                        <div className="flex-1 flex overflow-hidden">
                            <EditorSidebar
                                name={name}
                                setName={setName}
                                description={description}
                                setDescription={setDescription}
                                triggers={triggers}
                                newTrigger={newTrigger}
                                setNewTrigger={setNewTrigger}
                                handleAddTrigger={handleAddTrigger}
                                handleRemoveTrigger={handleRemoveTrigger}
                                params={params}
                                handleAddParam={handleAddParam}
                                handleRemoveParam={handleRemoveParam}
                                handleParamChange={handleParamChange}
                            />

                            <LogicWorkspace
                                steps={steps}
                                params={params}
                                isSimpleMode={isSimpleMode}
                                setIsSimpleMode={setIsSimpleMode}
                                handleAddStepWithIndex={handleAddStepWithIndex}
                                handleUpdateStep={handleUpdateStep}
                                handleDeleteStep={handleDeleteStep}
                                handleMoveStep={handleMoveStep}
                                showPreview={showPreview}
                                setShowPreview={setShowPreview}
                            />

                            <EditorStatsPreview
                                skill={skill}
                                name={name}
                                description={description}
                                triggers={triggers}
                                showPreview={showPreview}
                                setShowPreview={setShowPreview}
                            />
                        </div>

                        <DialogFooter className="p-6 border-t bg-background mt-auto gap-3 shrink-0">
                            <div className="flex-1 flex items-center gap-4 text-xs text-muted-foreground font-medium italic">
                                <span>{t("learning.editor.phase6Notice")}</span>
                            </div>
                            <Button
                                variant="ghost"
                                onClick={() => onOpenChange(false)}
                                disabled={loading}
                                className="text-xs font-semibold px-6"
                            >
                                {t("common.cancel")}
                            </Button>
                            <Button onClick={handleSave} disabled={loading} className="gap-2 px-10 h-11 font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.02] active:scale-[0.98]">
                                {loading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Save className="h-4 w-4" />
                                )}
                                {t("learning.editor.saveChanges")}
                            </Button>
                        </DialogFooter>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
