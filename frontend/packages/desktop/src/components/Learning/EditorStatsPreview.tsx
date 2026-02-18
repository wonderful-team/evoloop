import React from "react"
import { useTranslation } from "react-i18next"
import {
    BarChart3,
    CheckCircle2,
    TrendingUp,
    History,
    Eye,
    X,
    Terminal,
    Info
} from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import type { LearnedSkill } from "@/types/skill"

interface EditorStatsPreviewProps {
    skill: LearnedSkill
    showPreview: boolean
    setShowPreview: (val: boolean) => void
    name: string
    description: string
    triggers: string[]
}

export const EditorStatsPreview: React.FC<EditorStatsPreviewProps> = ({
    skill,
    showPreview,
    setShowPreview,
    name,
    description,
    triggers,
}) => {
    const { t } = useTranslation()

    return (
        <>
            {/* Column 3: Stats Details */}
            <div className="w-[320px] bg-muted/10 flex flex-col overflow-hidden">
                <div className="h-[52px] px-4 border-b bg-muted/20 flex items-center gap-2 shrink-0">
                    <BarChart3 className="h-4 w-4 text-primary" />
                    <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80">{t("learning.editor.stats")}</span>
                </div>
                <ScrollArea className="flex-1">
                    <div className="p-6 space-y-8">
                        <div className="grid grid-cols-1 gap-4">
                            <div className="bg-background border p-4 rounded-xl flex flex-col items-center text-center gap-2 font-bold shadow-sm">
                                <CheckCircle2 className="h-6 w-6 text-green-500 mb-1" />
                                <span className="text-[2xl] font-black">{skill.success_count || 0}</span>
                                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">{t("learning.successes")}</span>
                            </div>
                            <div className="bg-background border p-4 rounded-xl flex flex-col items-center text-center gap-2 font-bold shadow-sm">
                                <TrendingUp className="h-6 w-6 text-purple-500 mb-1" />
                                <span className="text-[2xl] font-black">92%</span>
                                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">{t("learning.editor.effectiveness")}</span>
                            </div>
                            <div className="bg-background border p-4 rounded-xl flex flex-col items-center text-center gap-2 font-bold shadow-sm">
                                <History className="h-6 w-6 text-blue-500 mb-1" />
                                <span className="text-[2xl] font-black">12s</span>
                                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">{t("learning.editor.avgDuration")}</span>
                            </div>
                        </div>

                        <div className="p-4 bg-muted/20 border border-dashed rounded-xl space-y-3 opacity-60">
                            <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground text-center">{t("learning.editor.recentRuns")}</h4>
                            <div className="space-y-2 text-[10px] text-center italic py-4">
                                {t("learning.editor.phase6Notice")}
                            </div>
                        </div>
                    </div>
                </ScrollArea>
            </div>

            {/* Live Preview Panel (Collapsible) */}
            {showPreview && (
                <div className="w-[320px] bg-muted/10 flex flex-col border-l overflow-hidden animate-in slide-in-from-right-3 duration-300 ease-out">
                    <div className="h-[52px] px-4 border-b bg-muted/20 flex items-center justify-between shrink-0">
                        <div className="flex items-center gap-2">
                            <Eye className="h-4 w-4 text-primary" />
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80">{t("learning.editor.preview")}</span>
                        </div>
                        <Button variant="ghost" size="icon" className="h-6 w-6 rounded-full" onClick={() => setShowPreview(false)}>
                            <X className="h-3 w-3" />
                        </Button>
                    </div>
                    <ScrollArea className="flex-1 text-card-foreground">
                        <div className="p-6 space-y-6">
                            {/* Preview Card */}
                            <div className="p-5 bg-card border rounded-xl shadow-md space-y-4 border-primary/20 ring-1 ring-primary/5">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="h-10 w-10 bg-primary/5 rounded-lg flex items-center justify-center border border-primary/10">
                                        <Terminal className="h-5 w-5 text-primary" />
                                    </div>
                                    <Badge variant="outline" className="bg-green-500/5 text-green-600 border-green-500/20 text-[9px] font-medium">
                                        {t(`learning.statusBadge.${skill.status || "active"}`, skill.status || "active")}
                                    </Badge>
                                </div>
                                <div className="space-y-1">
                                    <h3 className="font-bold text-lg leading-tight line-clamp-1">{name || t("learning.editor.untitledSkill")}</h3>
                                    <p className="text-[11px] text-muted-foreground line-clamp-3 leading-relaxed">
                                        {description || t("learning.editor.noDescription")}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-1.5 pt-1">
                                    {triggers.slice(0, 3).map((t, idx) => (
                                        <Badge key={idx} variant="outline" className="text-[8px] px-1.5 py-0 border-primary/10 bg-primary/5 text-primary/80">
                                            {t}
                                        </Badge>
                                    ))}
                                </div>
                            </div>

                            <div className="p-4 bg-primary/5 border border-primary/10 rounded-xl space-y-2">
                                <div className="flex items-center gap-1.5 text-primary font-bold text-[10px] uppercase">
                                    <Info className="h-3 w-3" />
                                    {t("learning.editor.editorInsights")}
                                </div>
                                <p className="text-[10px] text-muted-foreground leading-relaxed">
                                    {t("learning.editor.previewNotice")}
                                </p>
                            </div>

                            {/* Stats in Preview */}
                            <div className="space-y-4">
                                <div className="flex items-center gap-1.5 text-muted-foreground font-bold text-[10px] uppercase px-1">
                                    <BarChart3 className="h-3 w-3" />
                                    {t("learning.editor.stats")}
                                </div>

                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 bg-background border rounded-xl flex flex-col items-center gap-1">
                                        <span className="text-sm font-bold text-primary">{skill.success_count || 0}/{skill.success_count + (skill.failure_count || 0)}</span>
                                        <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{t("learning.editor.effectiveness")}</span>
                                    </div>
                                    <div className="p-3 bg-background border rounded-xl flex flex-col items-center gap-1">
                                        <span className="text-sm font-bold text-primary">{skill.avg_duration || "1.2s"}</span>
                                        <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{t("learning.editor.avgDuration")}</span>
                                    </div>
                                </div>

                                <div className="p-4 bg-muted/20 border border-dashed rounded-xl space-y-3 opacity-60">
                                    <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground text-center">{t("learning.editor.recentRuns")}</h4>
                                    <div className="space-y-2 text-[10px] text-center italic py-4">
                                        {t("learning.editor.phase6Notice")}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </ScrollArea>
                </div>
            )}
        </>
    )
}
