import {
    Loader2,
    Save,
    Settings2,
    Sparkles,
    Play,
    Zap
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { EditorSidebar } from "./EditorSidebar"
import { useChatStore } from "@/stores/chatStore"
import type { LearnedSkill } from "@/types/skill"
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
    const [instructions, setInstructions] = useState("")
    const [executionMode, setExecutionMode] = useState<"agentic" | "deterministic">("agentic")
    const [macroScript, setMacroScript] = useState("[]")

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

            setName(skill.name || "")
            setDescription(skill.description || "")
            setTriggers(safeParse(skill.trigger_patterns, []))
            setParams(safeParse(skill.parameters, []))
            setInstructions(skill.instructions || "")
            setExecutionMode((skill as any).execution_mode === "deterministic" ? "deterministic" : "agentic")
            setMacroScript((skill as any).macro_script ? JSON.stringify((skill as any).macro_script, null, 2) : "[]")
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

    const handleAiOptimize = async () => {
        setAiOptimizing(true)
        // Mock AI optimization delay
        await new Promise(resolve => setTimeout(resolve, 1500))

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
            let parsedMacro = [];
            try {
                parsedMacro = JSON.parse(macroScript || "[]");
            } catch (e) {
                toast.error(t("learning.editor.invalidMacroJson", "Macro script must be valid JSON"));
                return;
            }

            await LearningService.updateSkill({
                skillId: skill.id,
                requestBody: {
                    name,
                    description,
                    trigger_patterns: triggers,
                    parameters: params as any[],
                    instructions: instructions,
                    execution_mode: executionMode,
                    macro_script: parsedMacro,
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
            <DialogContent className="sm:max-w-[1200px] w-[90vw] h-[80vh] flex flex-col p-0 overflow-hidden bg-background border shadow-2xl">
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
                                        variant="outline"
                                        size="sm"
                                        className="gap-2 text-xs font-bold border-emerald-500/20 text-emerald-600 hover:bg-emerald-50"
                                        onClick={async () => {
                                            try {
                                                const threadId = useChatStore.getState().threadId || "debug-" + Date.now();
                                                await LearningService.executeSkill({
                                                    skillId: skill.id,
                                                    requestBody: {
                                                        thread_id: threadId,
                                                        params: {},
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

                            <div className="flex-1 p-6 flex flex-col bg-muted/10 h-full">
                                <div className="flex flex-row items-center justify-between mb-4">
                                    <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
                                        {executionMode === "agentic" ? <Sparkles className="h-4 w-4" /> : <Zap className="h-4 w-4 text-emerald-500" />}
                                        <span className={executionMode === "deterministic" ? "text-emerald-600" : ""}>
                                            {executionMode === "agentic" ? t("learning.expertGuide", "Expert Guide (Markdown SOP)") : "Macro Sequence (JSON)"}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs bg-background p-1 rounded-md border shadow-sm">
                                        <button
                                            onClick={() => setExecutionMode("agentic")}
                                            className={`px-3 py-1.5 rounded-sm transition-colors ${executionMode === "agentic" ? "bg-amber-100 text-amber-800 font-bold" : "hover:bg-muted text-muted-foreground"}`}
                                        >
                                            🧠 Agentic
                                        </button>
                                        <button
                                            onClick={() => setExecutionMode("deterministic")}
                                            className={`px-3 py-1.5 rounded-sm transition-colors ${executionMode === "deterministic" ? "bg-emerald-100 text-emerald-800 font-bold" : "hover:bg-muted text-muted-foreground"}`}
                                        >
                                            ⚡ Deterministic
                                        </button>
                                    </div>
                                </div>
                                {executionMode === "agentic" ? (
                                    <Textarea
                                        className="flex-1 font-mono text-sm resize-none bg-background rounded-xl p-4 border shadow-sm leading-relaxed"
                                        value={instructions}
                                        onChange={(e) => setInstructions(e.target.value)}
                                        placeholder={t("learning.editor.expertGuidePlaceholder", "Write markdown instructions for the agent... e.g. \\n1. Go to github.com\\n2. Click the 'New Repository' button")}
                                    />
                                ) : (
                                    <Textarea
                                        className="flex-1 font-mono text-sm resize-none bg-slate-950 text-emerald-400 rounded-xl p-4 border shadow-sm leading-relaxed"
                                        value={macroScript}
                                        onChange={(e) => setMacroScript(e.target.value)}
                                        placeholder="[{ 'event_type': 'click', 'target_selector': '.btn' }]"
                                    />
                                )}
                            </div>
                        </div>

                        <DialogFooter className="p-6 border-t bg-background mt-auto gap-3 shrink-0">
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

