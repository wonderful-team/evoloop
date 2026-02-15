import {
    Loader2,
    Save,
    Plus,
    Trash2,
    X,
    Terminal,
    Settings2,
    Sparkles,
    History,
    BarChart3,
    Info,
    Eye,
    TrendingUp,
    CheckCircle2
} from "lucide-react"
import { useEffect, useState, useMemo } from "react"
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
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { Separator } from "@evoloop/shared/components/ui/separator"
import type { LearnedSkill } from "@/types/skill"

interface SkillEditorDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    skill: LearnedSkill
    onSuccess: () => void
}

interface ParamDef {
    name: string
    type: string
    description: string
    required?: boolean
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
    const [activeTab, setActiveTab] = useState("general")

    useEffect(() => {
        if (open && skill) {
            setName(skill.name)
            setDescription(skill.description)
            setTriggers(skill.trigger_patterns || [])
            const p = skill.parameters || []
            setParams(Array.isArray(p) ? p : [])
        }
    }, [open, skill])

    const steps = useMemo(() => {
        if (!skill?.steps) return []
        return typeof skill.steps === 'string' ? JSON.parse(skill.steps) : skill.steps
    }, [skill])

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

        // Simulating AI improvement
        const betterDescription = description || "AI refined description based on execution logic."
        if (!triggers.includes("automated " + name.toLowerCase())) {
            setTriggers([...triggers, "automated " + name.toLowerCase()])
        }
        setDescription(betterDescription + " (Optimized)")

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
                },
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
            <DialogContent className="sm:max-w-[1000px] w-[95vw] h-[85vh] flex flex-col p-0 overflow-hidden bg-background/95 backdrop-blur-xl border border-primary/10">
                <div className="flex h-full overflow-hidden">
                    {/* Left Side: Editor */}
                    <div className="flex-1 flex flex-col border-r bg-background/50">
                        <DialogHeader className="p-6 pb-2 border-b bg-muted/20">
                            <div className="flex items-center justify-between">
                                <div className="space-y-1">
                                    <DialogTitle className="flex items-center gap-2 text-xl font-bold">
                                        <Settings2 className="h-5 w-5 text-primary animate-pulse" />
                                        {t("learning.editor.title", { name: skill.name })}
                                    </DialogTitle>
                                    <DialogDescription className="text-xs">
                                        {t("learning.editor.description")}
                                    </DialogDescription>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="gap-2 bg-primary/5 border-primary/20 hover:bg-primary/10 transition-all text-xs font-bold"
                                    onClick={handleAiOptimize}
                                    disabled={aiOptimizing}
                                >
                                    {aiOptimizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-primary" />}
                                    {t("learning.editor.aiOptimize")}
                                </Button>
                            </div>
                        </DialogHeader>

                        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
                            <TabsList className="bg-transparent border-b px-6 py-0 h-12 justify-start gap-4">
                                <TabsTrigger value="general" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-full gap-2 px-1 text-xs">
                                    <Settings2 className="h-3.5 w-3.5" />
                                    {t("learning.editor.tabs.general")}
                                </TabsTrigger>
                                <TabsTrigger value="logic" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-full gap-2 px-1 text-xs">
                                    <History className="h-3.5 w-3.5" />
                                    {t("learning.editor.tabs.logic")}
                                </TabsTrigger>
                                <TabsTrigger value="stats" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-full gap-2 px-1 text-xs">
                                    <BarChart3 className="h-3.5 w-3.5" />
                                    {t("learning.editor.tabs.stats")}
                                </TabsTrigger>
                            </TabsList>

                            <ScrollArea className="flex-1">
                                <div className="p-6 space-y-8 pb-12">
                                    <TabsContent value="general" className="mt-0 space-y-8 animate-in fade-in slide-in-from-left-2">
                                        {/* Basic Info */}
                                        <section className="space-y-4">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Badge variant="outline" className="h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px] font-bold">1</Badge>
                                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground/70">{t("learning.editor.skillName")}</h3>
                                            </div>
                                            <Input
                                                value={name}
                                                onChange={(e) => setName(e.target.value)}
                                                className="h-10 text-base font-medium bg-muted/20 border-muted focus-visible:ring-primary/30"
                                            />

                                            <div className="flex items-center gap-2 mb-2 pt-2">
                                                <Badge variant="outline" className="h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px] font-bold">2</Badge>
                                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground/70">{t("learning.editor.skillDescription")}</h3>
                                            </div>
                                            <Textarea
                                                value={description}
                                                onChange={(e) => setDescription(e.target.value)}
                                                rows={3}
                                                className="bg-muted/20 border-muted focus-visible:ring-primary/30"
                                            />
                                        </section>

                                        {/* Trigger Patterns */}
                                        <section className="space-y-4 p-5 bg-muted/30 rounded-2xl border border-dashed border-muted-foreground/20">
                                            <div className="flex items-center justify-between gap-2">
                                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-2">
                                                    <Terminal className="h-4 w-4 text-primary" />
                                                    {t("learning.editor.triggerPatterns")}
                                                </h3>
                                                <Badge variant="secondary" className="text-[10px] opacity-60">{triggers.length} {t("learning.mirror.found")}</Badge>
                                            </div>

                                            <div className="flex flex-wrap gap-2 min-h-[40px] p-1">
                                                {triggers.length === 0 && (
                                                    <span className="text-xs text-muted-foreground italic">
                                                        {t("learning.editor.noTriggers")}
                                                    </span>
                                                )}
                                                {triggers.map((trigger, i) => (
                                                    <Badge key={i} variant="secondary" className="pl-3 pr-1 py-1 gap-1 border border-primary/10 bg-background/50 hover:border-primary/30 transition-all">
                                                        {trigger}
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-4 w-4 rounded-full hover:bg-destructive hover:text-white"
                                                            onClick={() => handleRemoveTrigger(i)}
                                                        >
                                                            <X className="h-2.5 w-2.5" />
                                                        </Button>
                                                    </Badge>
                                                ))}
                                            </div>

                                            <div className="flex gap-2">
                                                <Input
                                                    value={newTrigger}
                                                    onChange={(e) => setNewTrigger(e.target.value)}
                                                    placeholder={t("learning.editor.addTrigger")}
                                                    className="h-9 text-xs bg-background"
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Enter") {
                                                            e.preventDefault()
                                                            handleAddTrigger()
                                                        }
                                                    }}
                                                />
                                                <Button size="sm" variant="outline" className="h-9 w-9 p-0" onClick={handleAddTrigger}>
                                                    <Plus className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </section>

                                        {/* Parameters */}
                                        <section className="space-y-4">
                                            <div className="flex items-center justify-between border-b pb-2">
                                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground/70">{t("learning.editor.parameters")}</h3>
                                                <Button size="sm" variant="outline" className="h-7 text-[10px] gap-1 bg-primary/5 hover:bg-primary/10 border-primary/10" onClick={handleAddParam}>
                                                    <Plus className="h-3 w-3" />
                                                    {t("learning.editor.addParameter")}
                                                </Button>
                                            </div>

                                            <div className="space-y-3">
                                                {params.length === 0 && (
                                                    <div className="text-center py-10 border-2 border-dashed border-muted rounded-2xl text-muted-foreground/50 flex flex-col items-center gap-2">
                                                        <Settings2 className="h-10 w-10 stroke-1" />
                                                        <span className="text-xs font-medium">{t("learning.noParameters")}</span>
                                                    </div>
                                                )}
                                                {params.map((param, i) => (
                                                    <div key={i} className="grid grid-cols-[1fr,100px,1.5fr,auto] gap-3 items-start border p-4 rounded-2xl bg-background/50 shadow-sm transition-all hover:shadow-md group">
                                                        <div className="grid gap-1.5">
                                                            <Label className="text-[10px] font-bold uppercase text-muted-foreground/80">{t("learning.editor.paramName")}</Label>
                                                            <Input
                                                                value={param.name}
                                                                onChange={(e) => handleParamChange(i, "name", e.target.value)}
                                                                className="h-8 text-xs font-mono bg-muted/20"
                                                                placeholder="e.g. city"
                                                            />
                                                        </div>
                                                        <div className="grid gap-1.5">
                                                            <Label className="text-[10px] font-bold uppercase text-muted-foreground/80">{t("learning.editor.paramType")}</Label>
                                                            <select
                                                                value={param.type}
                                                                onChange={(e) => handleParamChange(i, "type", e.target.value)}
                                                                className="flex h-8 w-full rounded-md border border-input bg-muted/20 px-3 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                                                            >
                                                                <option value="string">string</option>
                                                                <option value="number">number</option>
                                                                <option value="boolean">boolean</option>
                                                                <option value="array">array</option>
                                                            </select>
                                                        </div>
                                                        <div className="grid gap-1.5">
                                                            <Label className="text-[10px] font-bold uppercase text-muted-foreground/80">{t("learning.editor.paramDesc")}</Label>
                                                            <Input
                                                                value={param.description}
                                                                onChange={(e) => handleParamChange(i, "description", e.target.value)}
                                                                className="h-8 text-xs bg-muted/20"
                                                                placeholder="Context for this param"
                                                            />
                                                        </div>
                                                        <div className="pt-6">
                                                            <Button
                                                                variant="ghost"
                                                                size="icon"
                                                                className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                                                                onClick={() => handleRemoveParam(i)}
                                                            >
                                                                <Trash2 className="h-4 w-4" />
                                                            </Button>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </section>
                                    </TabsContent>

                                    <TabsContent value="logic" className="mt-0 space-y-6 animate-in fade-in slide-in-from-right-2">
                                        <div className="flex items-center gap-2 mb-4">
                                            <History className="h-5 w-5 text-primary" />
                                            <h3 className="text-base font-bold">{t("learning.steps")}</h3>
                                            <Badge variant="outline" className="ml-auto font-mono text-[10px]">{steps.length} Steps</Badge>
                                        </div>

                                        <div className="space-y-6 relative ml-4">
                                            {steps.length === 0 && (
                                                <div className="text-center py-20 opacity-20 flex flex-col items-center">
                                                    <History className="h-16 w-16 mb-4" />
                                                    <p className="text-sm font-medium">No execution logic recorded yet</p>
                                                </div>
                                            )}
                                            {steps.map((step: any, i: number) => (
                                                <div key={i} className="relative pl-10 pb-6 last:pb-0 border-l-2 border-primary/20 hover:border-primary/50 transition-all">
                                                    <div className="absolute left-[-11px] top-0 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-[10px] text-white font-bold shadow-lg shadow-primary/20 z-10">
                                                        {i + 1}
                                                    </div>
                                                    <div className="bg-card/50 border border-primary/5 rounded-2xl p-4 shadow-sm hover:shadow-md transition-all group">
                                                        <div className="flex items-center justify-between mb-3">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-sm font-bold text-primary px-2 py-0.5 rounded-md bg-primary/5">{step.action}</span>
                                                                {step.condition && (
                                                                    <Badge variant="outline" className="text-[10px] font-bold border-yellow-500/30 text-yellow-600 bg-yellow-50/50">
                                                                        IF: {step.condition}
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                            <Button variant="ghost" size="icon" className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-all">
                                                                <X className="h-3 w-3" />
                                                            </Button>
                                                        </div>
                                                        <div className="bg-black/5 p-3 rounded-xl text-[10px] font-mono leading-relaxed overflow-x-auto border border-black/5">
                                                            {JSON.stringify(step.args, null, 2)}
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </TabsContent>

                                    <TabsContent value="stats" className="mt-0 space-y-6 animate-in zoom-in-95">
                                        <div className="grid grid-cols-3 gap-4">
                                            <div className="bg-primary/5 border border-primary/10 p-6 rounded-3xl flex flex-col items-center text-center gap-2">
                                                <CheckCircle2 className="h-8 w-8 text-green-500 mb-2" />
                                                <span className="text-3xl font-black text-primary">{skill.success_count || 0}</span>
                                                <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground/60">{t("learning.successes")}</span>
                                            </div>
                                            <div className="bg-purple-500/5 border border-purple-500/10 p-6 rounded-3xl flex flex-col items-center text-center gap-2">
                                                <TrendingUp className="h-8 w-8 text-purple-500 mb-2" />
                                                <span className="text-3xl font-black text-primary">92%</span>
                                                <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground/60">Effectiveness</span>
                                            </div>
                                            <div className="bg-blue-500/5 border border-blue-500/10 p-6 rounded-3xl flex flex-col items-center text-center gap-2">
                                                <History className="h-8 w-8 text-blue-500 mb-2" />
                                                <span className="text-3xl font-black text-primary">12s</span>
                                                <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground/60">Avg. Duration</span>
                                            </div>
                                        </div>

                                        <div className="bg-muted/10 border p-6 rounded-3xl space-y-4">
                                            <h4 className="text-sm font-bold opacity-60 flex items-center gap-2">
                                                <History className="h-4 w-4" />
                                                RECENT RUNS
                                            </h4>
                                            <div className="space-y-2 opacity-40 italic text-xs text-center py-10">
                                                Detailed execution logs will appear here in Phase 6.
                                            </div>
                                        </div>
                                    </TabsContent>
                                </div>
                            </ScrollArea>
                        </Tabs>

                        <DialogFooter className="p-6 border-t bg-muted/10 mt-auto">
                            <Button
                                variant="ghost"
                                onClick={() => onOpenChange(false)}
                                disabled={loading}
                                className="text-xs font-bold uppercase tracking-widest opacity-60 hover:opacity-100"
                            >
                                {t("common.cancel")}
                            </Button>
                            <Button onClick={handleSave} disabled={loading} className="gap-2 px-8 rounded-full font-bold shadow-lg shadow-primary/20 transition-all hover:scale-105 active:scale-95">
                                {loading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Save className="h-4 w-4" />
                                )}
                                {t("learning.editor.saveChanges")}
                            </Button>
                        </DialogFooter>
                    </div>

                    {/* Right Side: Live Preview Panel */}
                    <div className="w-[320px] bg-muted/10 flex flex-col border-l overflow-hidden">
                        <div className="p-4 border-b bg-muted/20 flex items-center gap-2">
                            <Eye className="h-4 w-4 text-primary" />
                            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/80">{t("learning.editor.preview")}</span>
                        </div>
                        <ScrollArea className="flex-1">
                            <div className="p-6 space-y-6">
                                {/* Preview Card */}
                                <div className="p-5 bg-card border rounded-3xl shadow-xl space-y-4 transform scale-[0.95] origin-top transition-all border-primary/20">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="h-10 w-10 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/10">
                                            <Terminal className="h-5 w-5 text-primary" />
                                        </div>
                                        <Badge variant="outline" className="bg-green-500/5 text-green-600 border-green-500/20 text-[9px] font-bold">
                                            {skill.status || "active"}
                                        </Badge>
                                    </div>
                                    <div className="space-y-1">
                                        <h3 className="font-bold text-lg leading-tight line-clamp-1">{name || "Untitled Skill"}</h3>
                                        <p className="text-[11px] text-muted-foreground line-clamp-3 leading-relaxed">
                                            {description || "No description provided."}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 pt-1">
                                        {triggers.slice(0, 3).map((t, idx) => (
                                            <Badge key={idx} variant="secondary" className="text-[8px] bg-muted/50 px-1.5 py-0.5 rounded-sm">
                                                {t}
                                            </Badge>
                                        ))}
                                        {triggers.length > 3 && (
                                            <span className="text-[8px] text-muted-foreground font-bold">+{triggers.length - 3}</span>
                                        )}
                                    </div>
                                    <Separator className="opacity-50" />
                                    <div className="flex items-center justify-between text-[10px] font-bold text-muted-foreground">
                                        <div className="flex items-center gap-1.5 text-primary">
                                            <TrendingUp className="h-3 w-3" />
                                            {skill.success_count || 0}
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <History className="h-3 w-3" />
                                            {steps.length} Steps
                                        </div>
                                    </div>
                                </div>

                                {/* Preview Stats Pane */}
                                <div className="p-4 bg-primary/5 rounded-2xl border border-primary/10 space-y-3">
                                    <div className="flex items-center gap-2 text-[10px] font-bold text-primary italic">
                                        <Info className="h-3 w-3" />
                                        EDITOR INSIGHTS
                                    </div>
                                    <div className="grid gap-2">
                                        <div className="flex justify-between text-[9px] font-medium">
                                            <span className="opacity-60">Triggers Count</span>
                                            <span className={triggers.length === 0 ? "text-destructive" : "text-green-600"}>{triggers.length}</span>
                                        </div>
                                        <div className="flex justify-between text-[9px] font-medium">
                                            <span className="opacity-60">Parameters</span>
                                            <span className={params.length === 0 ? "text-yellow-600" : "text-primary"}>{params.length}</span>
                                        </div>
                                        <div className="flex justify-between text-[9px] font-medium">
                                            <span className="opacity-60">Complexity</span>
                                            <span className="font-bold">{steps.length > 5 ? "Medium" : "Low"}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="text-[10px] text-muted-foreground/40 text-center px-4 leading-relaxed">
                                    This is a live representation of how your skill will appear in the library.
                                </div>
                            </div>
                        </ScrollArea>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
