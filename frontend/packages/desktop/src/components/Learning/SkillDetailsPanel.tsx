import { Info, Terminal, Layout, Clock, TrendingUp, Play, Edit, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@evoloop/shared/components/ui/table"
import type { LearnedSkill } from "@/types/skill"

interface SkillDetailsPanelProps {
    skill: LearnedSkill | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onRun?: (skill: LearnedSkill) => void
    onEdit?: (skill: LearnedSkill) => void
    onDelete?: (skillId: number) => void
}

export function SkillDetailsPanel({
    skill,
    open,
    onOpenChange,
    onRun,
    onEdit,
    onDelete,
}: SkillDetailsPanelProps) {
    const { t } = useTranslation()

    if (!skill) return null

    // Parse steps from JSON if needed (in case they are strings in the type)
    const steps = typeof skill.steps === 'string' ? JSON.parse(skill.steps) : (skill.steps || [])

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent className="sm:max-w-xl w-[90vw] p-0 flex flex-col">
                <SheetHeader className="p-6 pb-2 border-b">
                    <div className="flex items-center gap-2 text-primary mb-1">
                        <Terminal className="h-5 w-5" />
                        <span className="text-xs font-bold uppercase tracking-wider">{t("learning.skillDetails", "Skill Details")}</span>
                    </div>
                    <SheetTitle className="text-2xl font-bold">{skill.name}</SheetTitle>
                    <SheetDescription className="mt-2 text-sm leading-relaxed">
                        {skill.description}
                    </SheetDescription>
                </SheetHeader>

                <ScrollArea className="flex-1">
                    <div className="p-6 space-y-8 pb-20">
                        {/* Stats Summary */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-muted/30 p-4 rounded-xl border flex flex-col gap-1">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold">{t("learning.status", "Status")}</span>
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20">
                                        {t(`learning.statusBadge.${skill.status || "draft"}`, skill.status || "draft")}
                                    </Badge>
                                </div>
                            </div>
                            <div className="bg-muted/30 p-4 rounded-xl border flex flex-col gap-1">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold">{t("learning.performance", "Performance")}</span>
                                <div className="flex items-center gap-2 font-bold text-green-600">
                                    <TrendingUp className="h-4 w-4" />
                                    {skill.success_count || 0} {t("learning.successes", "Successes")}
                                </div>
                            </div>
                        </div>

                        {/* Trigger Patterns */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-sm font-bold">
                                <Info className="h-4 w-4 text-primary" />
                                {t("learning.triggerPatterns", "Trigger Patterns")}
                            </div>
                            <div className="space-y-2">
                                {skill.trigger_patterns?.map((pattern, i) => (
                                    <div key={i} className="bg-muted/50 px-3 py-2 rounded-lg text-xs font-mono border border-muted-foreground/10">
                                        {pattern}
                                    </div>
                                ))}
                            </div>
                        </section>

                        <Separator />

                        {/* Parameters */}
                        <section className="space-y-3">
                            <div className="flex items-center gap-2 text-sm font-bold">
                                <Layout className="h-4 w-4 text-primary" />
                                {t("learning.parameters", "Parameters")}
                            </div>
                            {skill.parameters && skill.parameters.length > 0 ? (
                                <div className="border rounded-xl overflow-hidden">
                                    <Table>
                                        <TableHeader className="bg-muted/30">
                                            <TableRow>
                                                <TableHead className="h-9 text-xs">{t("common.name", "Name")}</TableHead>
                                                <TableHead className="h-9 text-xs">{t("common.type", "Type")}</TableHead>
                                                <TableHead className="h-9 text-xs">{t("common.description", "Description")}</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {skill.parameters.map((param, i) => (
                                                <TableRow key={i} className="text-xs">
                                                    <TableCell className="font-mono py-2">{param.name}</TableCell>
                                                    <TableCell className="py-2"><Badge variant="outline" className="text-[9px] font-normal">{param.type}</Badge></TableCell>
                                                    <TableCell className="py-2 text-muted-foreground">{param.description}</TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>
                            ) : (
                                <p className="text-xs text-muted-foreground italic">{t("learning.noParameters", "No parameters defined.")}</p>
                            )}
                        </section>

                        <Separator />

                        {/* Execution Steps */}
                        <section className="space-y-6">
                            <div className="flex items-center gap-2 text-sm font-bold">
                                <Terminal className="h-4 w-4 text-primary" />
                                {t("learning.steps", "Execution Steps")}
                            </div>
                            <div className="relative space-y-0.5">
                                {/* Vertical Connector Line */}
                                <div className="absolute left-[11px] top-2 bottom-2 w-0.5 bg-muted-foreground/10" />

                                {steps.map((step: any, i: number) => (
                                    <div key={i} className="relative pl-10 pb-6 last:pb-0">
                                        <div className="absolute left-0 top-1 h-6 w-6 rounded-full bg-background border-2 border-primary/40 flex items-center justify-center text-[10px] font-bold z-10 shadow-sm ring-4 ring-background">
                                            {i + 1}
                                        </div>
                                        <div className="bg-muted/10 hover:bg-muted/20 transition-colors border border-muted-foreground/10 rounded-xl p-4">
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="flex items-center gap-2">
                                                    <Badge variant="secondary" className="bg-primary/5 text-primary border-primary/10 text-[10px] uppercase font-bold px-2 py-0.5">
                                                        {step.action}
                                                    </Badge>
                                                </div>
                                                {step.condition && (
                                                    <div className="flex items-center gap-1.5 text-[10px] text-amber-600 font-medium bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200/50">
                                                        <Info className="h-3 w-3" />
                                                        {step.condition}
                                                    </div>
                                                )}
                                            </div>
                                            <div className="bg-background/50 border border-muted-foreground/10 p-3 rounded-lg text-[11px] font-mono whitespace-pre-wrap break-all leading-tight text-muted-foreground/80">
                                                {JSON.stringify(step.args, null, 2)}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>

                        {/* Metadata */}
                        <Separator />
                        <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
                            <div className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {t("learning.created", "Created")}: {new Date(skill.created_at).toLocaleString()}
                            </div>
                        </div>
                    </div>
                </ScrollArea>

                <div className="p-4 border-t bg-card mt-auto flex gap-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)]">
                    <Button
                        variant="default"
                        className="flex-1 h-10 font-medium shadow-sm transition-all hover:shadow-md"
                        onClick={() => { onRun?.(skill); onOpenChange(false); }}
                    >
                        <Play className="h-4 w-4 mr-2 fill-current" />
                        {t("common.run", "Run Skill")}
                    </Button>
                    <Button
                        variant="outline"
                        className="h-10 px-4"
                        onClick={() => { onEdit?.(skill); onOpenChange(false); }}
                    >
                        <Edit className="h-4 w-4 mr-2" />
                        {t("common.edit")}
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-10 w-10 text-destructive hover:bg-destructive/10"
                        onClick={() => { onDelete?.(skill.id); onOpenChange(false); }}
                    >
                        <Trash2 className="h-4 w-4" />
                    </Button>
                </div>
            </SheetContent>
        </Sheet>
    )
}
