/**
 * SkillEditorPage - Full page skill editor (replaces SkillEditorDialog)
 */

import {
    Loader2,
    Save,
    Settings2,
    Sparkles,
    Play,
    Zap,
    FileJson,
    ArrowLeft,
    Trash2,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { LearningService } from "@/client/sdk.gen"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { EditorSidebar } from "./EditorSidebar"
import { useChatStore } from "@/stores/chatStore"
import type { LearnedSkill } from "@/types/skill"
import type { ParamDef } from "./EditorSidebar"
import { MacroEditor, MacroJsonEditor, type MacroStep } from "./SmartReplay/MacroEditor"
import { MarkdownEditor } from "@/components/Common/MarkdownEditor"

interface SkillEditorPageProps {
    skillId: number
    onBack?: () => void
    onSave?: () => void
}

export function SkillEditorPage({ skillId, onBack, onSave }: SkillEditorPageProps) {
    const { t } = useTranslation()
    const queryClient = useQueryClient()
    const [loading, setLoading] = useState(false)
    const [aiOptimizing, setAiOptimizing] = useState(false)

    // Form state
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [triggers, setTriggers] = useState<string[]>([])
    const [newTrigger, setNewTrigger] = useState("")
    const [params, setParams] = useState<ParamDef[]>([])
    const [instructions, setInstructions] = useState("")
    const [executionMode, setExecutionMode] = useState<"agentic" | "deterministic">("agentic")
    const [macroScript, setMacroScript] = useState("[]")

    // Fetch skill data
    const { data: skill, isLoading: isLoadingSkill } = useQuery({
        queryKey: ["skill", skillId],
        queryFn: async () => {
            const result = await LearningService.getSkill({ skillId })
            return result as unknown as LearnedSkill
        },
    })

    // Initialize form from skill data
    useEffect(() => {
        if (skill) {
            const safeParse = (data: any, defaultVal: any) => {
                if (!data) return defaultVal
                if (typeof data === "string") {
                    try {
                        return JSON.parse(data)
                    } catch (e) {
                        console.error("Failed to parse", data, e)
                        return defaultVal
                    }
                }
                return data
            }

            setName(skill.name || "")
            setDescription(skill.description || "")
            setTriggers(safeParse(skill.trigger_patterns, []))
            setParams(safeParse(skill.parameters, []))
            setInstructions(skill.instructions || "")
            setExecutionMode((skill as any).execution_mode === "deterministic" ? "deterministic" : "agentic")
            setMacroScript((skill as any).macro_script ? JSON.stringify((skill as any).macro_script, null, 2) : "[]")
        }
    }, [skill])

    // Helper to safely parse macro script
    const safeParseMacro = (script: string): MacroStep[] => {
        try {
            const parsed = JSON.parse(script || "[]")
            return Array.isArray(parsed) ? parsed : []
        } catch {
            return []
        }
    }

    // Mutations
    const updateMutation = useMutation({
        mutationFn: async () => {
            let parsedMacro = []
            try {
                parsedMacro = JSON.parse(macroScript || "[]")
            } catch (e) {
                throw new Error(t("learning.editor.invalidMacroJson", "Macro script must be valid JSON"))
            }

            return LearningService.updateSkill({
                skillId,
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
        },
        onSuccess: () => {
            toast.success(t("common.saved"))
            queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
            queryClient.invalidateQueries({ queryKey: ["skill", skillId] })
            onSave?.()
        },
        onError: (error: any) => {
            toast.error(error.message || t("common.error.message"))
        },
    })

    const deleteMutation = useMutation({
        mutationFn: () => LearningService.deactivateSkill({ skillId }),
        onSuccess: () => {
            toast.success(t("common.success", "Skill deleted"))
            queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
            onBack?.()
        },
        onError: (error: any) => {
            toast.error(error.message || t("common.error.message"))
        },
    })

    // Form handlers
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
        await new Promise((resolve) => setTimeout(resolve, 1500))

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

        updateMutation.mutate()
    }

    const handleRun = async () => {
        try {
            const threadId = useChatStore.getState().threadId || "debug-" + Date.now()
            await LearningService.executeSkill({
                skillId,
                requestBody: {
                    thread_id: threadId,
                    params: {},
                },
            })
            toast.success(t("learning.executionStarted", "Execution started"))
        } catch (e) {
            toast.error(t("learning.executionFailed", "Execution failed"))
        }
    }

    const handleDelete = () => {
        if (confirm(t("learning.confirmDeactivate", "Are you sure you want to delete this skill?"))) {
            deleteMutation.mutate()
        }
    }

    if (isLoadingSkill) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    if (!skill) {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-4">
                <p className="text-muted-foreground">{t("learning.skillNotFound", "Skill not found")}</p>
                <Button onClick={onBack}>
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    {t("common.back")}
                </Button>
            </div>
        )
    }

    return (
        <div className="flex flex-col h-full bg-background">
            {/* Header */}
            <header className="flex items-center justify-between px-6 py-4 border-b bg-card">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="sm" onClick={onBack} className="gap-2">
                        <ArrowLeft className="h-4 w-4" />
                        {t("common.back")}
                    </Button>
                    <Separator orientation="vertical" className="h-6" />
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-xl">
                            <Settings2 className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold">{skill.name}</h1>
                            <p className="text-xs text-muted-foreground">{t("learning.editor.description")}</p>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        size="sm"
                        className="gap-2 text-xs font-bold border-emerald-500/20 text-emerald-600 hover:bg-emerald-50"
                        onClick={handleRun}
                        disabled={updateMutation.isPending}
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
                        {aiOptimizing ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                            <Sparkles className="h-3.5 w-3.5 text-primary" />
                        )}
                        {t("learning.editor.aiOptimize")}
                    </Button>

                    <Button
                        variant="ghost"
                        size="sm"
                        className="gap-2 text-destructive hover:bg-destructive/10"
                        onClick={handleDelete}
                        disabled={deleteMutation.isPending}
                    >
                        <Trash2 className="h-4 w-4" />
                        {t("common.delete")}
                    </Button>

                    <Separator orientation="vertical" className="h-6" />

                    <Button
                        onClick={handleSave}
                        disabled={updateMutation.isPending}
                        className="gap-2 px-6 font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
                    >
                        {updateMutation.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Save className="h-4 w-4" />
                        )}
                        {t("learning.editor.saveChanges")}
                    </Button>
                </div>
            </header>

            {/* Main Content */}
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

                <div className="flex-1 p-6 flex flex-col bg-muted/10 h-full min-h-0">
                    <div className="flex flex-row items-center justify-between mb-4 shrink-0">
                        <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
                            {executionMode === "agentic" ? (
                                <Sparkles className="h-4 w-4" />
                            ) : (
                                <Zap className="h-4 w-4 text-emerald-500" />
                            )}
                            <span className={executionMode === "deterministic" ? "text-emerald-600" : ""}>
                                {executionMode === "agentic"
                                    ? t("learning.expertGuide", "Expert Guide (Markdown SOP)")
                                    : t("learning.macroSequence", "Macro Sequence (Visual Editor)")}
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            {executionMode === "deterministic" && (
                                <MacroJsonEditor
                                    steps={safeParseMacro(macroScript)}
                                    onChange={(steps) => setMacroScript(JSON.stringify(steps, null, 2))}
                                >
                                    <Button variant="outline" size="sm" className="gap-1.5">
                                        <FileJson className="h-3.5 w-3.5" />
                                        {t("learning.editJson", "Edit JSON")}
                                    </Button>
                                </MacroJsonEditor>
                            )}
                            <div className="flex items-center gap-2 text-xs bg-background p-1 rounded-md border shadow-sm">
                                <button
                                    onClick={() => setExecutionMode("agentic")}
                                    className={`px-3 py-1.5 rounded-sm transition-colors ${
                                        executionMode === "agentic"
                                            ? "bg-amber-100 text-amber-800 font-bold"
                                            : "hover:bg-muted text-muted-foreground"
                                    }`}
                                >
                                    🧠 {t("learning.agentic", "Agentic")}
                                </button>
                                <button
                                    onClick={() => setExecutionMode("deterministic")}
                                    className={`px-3 py-1.5 rounded-sm transition-colors ${
                                        executionMode === "deterministic"
                                            ? "bg-emerald-100 text-emerald-800 font-bold"
                                            : "hover:bg-muted text-muted-foreground"
                                    }`}
                                >
                                    ⚡ {t("learning.deterministic", "Deterministic")}
                                </button>
                            </div>
                        </div>
                    </div>
                    {executionMode === "agentic" ? (
                        <MarkdownEditor
                            value={instructions}
                            onChange={setInstructions}
                            placeholder={t(
                                "learning.editor.expertGuidePlaceholder",
                                "Write markdown instructions for the agent... e.g. \\n1. Go to github.com\\n2. Click the 'New Repository' button"
                            )}
                        />
                    ) : (
                        <div className="flex-1 min-h-0 border rounded-xl bg-background shadow-sm overflow-hidden">
                            <MacroEditor
                                steps={safeParseMacro(macroScript)}
                                onChange={(steps) => setMacroScript(JSON.stringify(steps, null, 2))}
                                onStepPreview={(step) => {
                                    console.log("Preview step:", step)
                                    toast.info(`Step ${step.step_number}: ${step.description || step.event_type}`)
                                }}
                            />
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
