/**
 * SkillReviewPanel - Review generated skill and macro script
 */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { CheckCircle2, Edit2, Save, FileJson, X } from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"

import { MacroEditor, MacroJsonEditor, MacroStep } from "./MacroEditor"

interface SkillReviewPanelProps {
    skill: {
        name: string
        description: string
        namespace: string
        trigger_patterns: string[]
        instructions: string
        execution_mode: string
    }
    macroScript: MacroStep[]
    onEdit?: () => void
    onComplete?: (skill: { skill: typeof SkillReviewPanelProps.prototype.skill; macroScript: MacroStep[] }) => void
    onCancel?: () => void
    videoPath?: string
}

export function SkillReviewPanel({
    skill,
    macroScript: initialMacroScript,
    onEdit,
    onComplete,
    onCancel,
    videoPath,
}: SkillReviewPanelProps) {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("overview")
    const [macroScript, setMacroScript] = useState<MacroStep[]>(initialMacroScript)

    return (
        <div className="flex flex-col h-full gap-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-6 w-6 text-green-500" />
                    <div>
                        <h2 className="text-lg font-semibold">{t("skillReview.title")}</h2>
                        <p className="text-sm text-muted-foreground">
                            {t("skillReview.subtitle")}
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={onCancel} className="text-muted-foreground hover:text-foreground">
                        <X className="h-5 w-5" />
                    </Button>
                    <MacroJsonEditor steps={macroScript} onChange={setMacroScript}>
                        <Button variant="outline" size="sm">
                            <FileJson className="mr-2 h-4 w-4" />
                            {t("skillReview.editJson")}
                        </Button>
                    </MacroJsonEditor>
                    <Button variant="outline" onClick={onEdit}>
                        <Edit2 className="mr-2 h-4 w-4" />
                        {t("skillReview.back")}
                    </Button>
                    <Button onClick={() => onComplete?.({ skill, macroScript })}>
                        <Save className="mr-2 h-4 w-4" />
                        {t("skillReview.saveSkill")}
                    </Button>
                </div>
            </div>

            {/* Content tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                <TabsList>
                    <TabsTrigger value="overview">{t("skillReview.overview")}</TabsTrigger>
                    <TabsTrigger value="instructions">{t("skillReview.instructions")}</TabsTrigger>
                    <TabsTrigger value="macro">{t("skillReview.macroScript", { count: macroScript.length })}</TabsTrigger>
                </TabsList>

                <div className="flex-1 mt-4 min-h-0">
                    <TabsContent value="overview" className="h-full m-0">
                        <ScrollArea className="h-full">
                            <div className="space-y-6 p-4">
                                {/* Name */}
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground">{t("skillReview.skillName")}</label>
                                    <h3 className="text-xl font-semibold">{skill.name}</h3>
                                </div>

                                {/* Description */}
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground">{t("skillReview.description")}</label>
                                    <p className="text-base">{skill.description}</p>
                                </div>

                                {/* Namespace */}
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground">{t("skillReview.namespace")}</label>
                                    <p className="text-sm font-mono bg-muted p-2 rounded">{skill.namespace}</p>
                                </div>

                                {/* Trigger Patterns */}
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground">{t("skillReview.triggerPatterns")}</label>
                                    <div className="flex flex-wrap gap-2 mt-1">
                                        {skill.trigger_patterns.map((pattern, i) => (
                                            <Badge key={i} variant="secondary">{pattern}</Badge>
                                        ))}
                                    </div>
                                </div>

                                {/* Execution Mode */}
                                <div>
                                    <label className="text-sm font-medium text-muted-foreground">{t("skillReview.executionMode")}</label>
                                    <div className="flex items-center gap-2 mt-1">
                                        <Badge variant={skill.execution_mode === "deterministic" ? "default" : "outline"}>
                                            {skill.execution_mode}
                                        </Badge>
                                        <span className="text-sm text-muted-foreground">
                                            {skill.execution_mode === "deterministic"
                                                ? t("skillReview.deterministicDesc")
                                                : t("skillReview.agenticDesc")}
                                        </span>
                                    </div>
                                </div>

                                {/* Summary stats */}
                                <div className="grid grid-cols-3 gap-4 pt-4 border-t">
                                    <div className="text-center p-4 bg-muted rounded-lg">
                                        <div className="text-2xl font-bold">{macroScript.length}</div>
                                        <div className="text-xs text-muted-foreground">{t("skillReview.totalSteps")}</div>
                                    </div>
                                    <div className="text-center p-4 bg-muted rounded-lg">
                                        <div className="text-2xl font-bold">
                                            {macroScript.filter(s => s.type === "extract").length}
                                        </div>
                                        <div className="text-xs text-muted-foreground">{t("skillReview.extractSteps")}</div>
                                    </div>
                                    <div className="text-center p-4 bg-muted rounded-lg">
                                        <div className="text-2xl font-bold">
                                            {macroScript.filter(s => s.type === "action").length}
                                        </div>
                                        <div className="text-xs text-muted-foreground">{t("skillReview.actionSteps")}</div>
                                    </div>
                                </div>
                            </div>
                        </ScrollArea>
                    </TabsContent>

                    <TabsContent value="instructions" className="h-full m-0">
                        <ScrollArea className="h-full">
                            <div className="prose prose-sm max-w-none p-4">
                                {skill.instructions ? (
                                    <div dangerouslySetInnerHTML={{ __html: renderMarkdown(skill.instructions) }} />
                                ) : (
                                    <p className="text-muted-foreground">{t("skillReview.noInstructions")}</p>
                                )}
                            </div>
                        </ScrollArea>
                    </TabsContent>

                    <TabsContent value="macro" className="h-full m-0 flex flex-col">
                        <MacroEditor
                            steps={macroScript}
                            videoPath={videoPath}
                            onChange={setMacroScript}
                            onStepPreview={(step) => {
                                console.log("Preview step:", step)
                            }}
                        />
                    </TabsContent>
                </div>
            </Tabs>
        </div>
    )
}

function renderMarkdown(markdown: string): string {
    // Simple markdown to HTML conversion
    return markdown
        .replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 class="text-xl font-semibold mt-6 mb-3">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-8 mb-4">$1</h1>')
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        .replace(/`([^`]+)`/gim, '<code class="bg-muted px-1 py-0.5 rounded text-sm">$1</code>')
        .replace(/\n/gim, '<br />')
}
