import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Separator } from "@evoloop/shared/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  Clock,
  Edit,
  Info,
  Layout,
  Play,
  Sparkles,
  Terminal,
  Trash2,
  TrendingUp,
  Zap,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import type { LearnedSkill } from "@/types/skill"
import { isSkillRoutable } from "./skillLifecycle"

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
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()

  const confirmMutation = useMutation({
    mutationFn: async (skillId: number) => {
      return await LearningService.confirmLearnedSkill({ skillId })
    },
    onSuccess: () => {
      toast.success(t("learning.confirmSuccess"))
      queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast.error(t("learning.confirmError", { message: error.message }))
    },
  })

  if (!skill) return null

  // Parse fields from JSON if needed (in case they are strings in the type/DB)
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

  const triggerPatterns = safeParse(skill.trigger_patterns, [])
  const parameters = safeParse(skill.parameters, [])
  const macroScript = safeParse((skill as any).macro_script, [])
  const executionMode = (skill as any).execution_mode || "agentic"

  // Check if skill has macro script
  const hasMacroScript = Array.isArray(macroScript) && macroScript.length > 0

  // Recursive function to flatten macro script for flat table display with indentation
  const flattenMacroScript = (steps: any[], depth = 0): any[] => {
    let result: any[] = []
    steps.forEach((step) => {
      result.push({ ...step, depth })
      if (step.type === "if") {
        if (step.then_steps)
          result = [
            ...result,
            ...flattenMacroScript(step.then_steps, depth + 1),
          ]
        if (step.else_steps)
          result = [
            ...result,
            ...flattenMacroScript(step.else_steps, depth + 1),
          ]
      } else if (step.type === "loop") {
        if (step.steps)
          result = [...result, ...flattenMacroScript(step.steps, depth + 1)]
      }
    })
    return result
  }

  const flattenedMacro = hasMacroScript ? flattenMacroScript(macroScript) : []

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[800px] w-[90vw] p-0 flex flex-col">
        <SheetHeader className="p-6 pb-2 border-b border-border">
          <div className="flex items-center gap-2 text-primary mb-1">
            <Terminal className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-wider">
              {t("learning.skillDetails")}
            </span>
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
              <div className="bg-muted/30 p-4 rounded-xl border border-border flex flex-col gap-1">
                <span className="text-[10px] text-muted-foreground uppercase font-bold">
                  {t("learning.status")}
                </span>
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge
                    variant="outline"
                    className="bg-primary/5 text-primary border-primary/20"
                  >
                    {t(
                      `learning.statusBadge.${skill.status || "pending_review"}`,
                    )}
                  </Badge>
                  <Badge
                    variant="outline"
                    className={
                      executionMode === "deterministic"
                        ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[9px]"
                        : "bg-amber-500/10 text-amber-600 border-amber-500/20 text-[9px]"
                    }
                  >
                    {executionMode === "deterministic"
                      ? `${t("learning.deterministicIcon")} ${t("learning.deterministic")}`
                      : `${t("learning.agenticIcon")} ${t("learning.agentic")}`}
                  </Badge>
                </div>
              </div>
              <div className="bg-muted/30 p-4 rounded-xl border border-border flex flex-col gap-1">
                <span className="text-[10px] text-muted-foreground uppercase font-bold">
                  {t("learning.performance")}
                </span>
                <div className="flex items-center gap-2 font-bold text-green-600">
                  <TrendingUp className="h-4 w-4" />
                  {skill.success_count || 0} {t("learning.successes")}
                </div>
              </div>
            </div>

            {/* Trigger Patterns */}
            <section className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold">
                <Info className="h-4 w-4 text-primary" />
                {t("learning.triggerPatterns")}
              </div>
              <div className="space-y-2">
                {triggerPatterns?.map((pattern: string, i: number) => (
                  <div
                    key={i}
                    className="bg-muted/50 px-3 py-2 rounded-lg text-xs font-mono border border-muted-foreground/10"
                  >
                    {pattern}
                  </div>
                ))}
              </div>
            </section>

            <Separator />

            {/* User Inputs (Renamed from Parameters) */}
            <section className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold">
                <Layout className="h-4 w-4 text-primary" />
                {t("learning.parameters")}
              </div>
              {parameters && parameters.length > 0 ? (
                <div className="space-y-2">
                  {parameters.map((param: any, i: number) => (
                    <div
                      key={i}
                      className="bg-muted/30 p-4 rounded-xl border border-border flex flex-col gap-1.5 transition-all hover:border-primary/20"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tight">
                          {t("learning.editor.paramType")}
                          {t("common.colon")} {param.type}
                        </span>
                        <Badge
                          variant="outline"
                          className="text-[9px] font-mono opacity-50"
                        >
                          {param.name}
                        </Badge>
                      </div>
                      <p className="text-sm font-medium leading-snug">
                        {param.description || param.name}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground italic px-1">
                  {t("learning.execution.noParams")}
                </p>
              )}
            </section>

            <Separator />

            {/* Expert Guide - Moved to top priority if exists */}
            {skill.instructions ? (
              <section className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
                  <Sparkles className="h-4 w-4" />
                  {t("learning.expertStrategicGuide")}
                </div>
                <div className="bg-amber-50/30 dark:bg-amber-950/10 p-5 rounded-2xl border border-amber-500/20 shadow-[0_4px_20px_rgba(245,158,11,0.05)]">
                  <div className="text-[13px] leading-relaxed text-foreground/90">
                    <MarkdownRenderer content={skill.instructions} />
                  </div>
                  <div className="mt-4 flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[9px] font-bold"
                    >
                      {t("learning.optimizedBadge")}
                    </Badge>
                  </div>
                </div>
              </section>
            ) : (
              <div className="bg-muted/20 p-6 rounded-2xl border border-dashed flex flex-col items-center justify-center text-center gap-2">
                <Info className="h-8 w-8 text-muted-foreground/30" />
                <p className="text-xs text-muted-foreground">
                  {t("learning.noExpertGuide")}
                </p>
              </div>
            )}

            {/* Macro Script - Only show if exists */}
            {hasMacroScript && (
              <>
                <Separator className="opacity-50" />
                <section className="space-y-4">
                  <div className="flex items-center gap-2 text-sm font-bold text-emerald-600">
                    <Zap className="h-4 w-4" />
                    {t("learning.macroScript")}
                    <Badge
                      variant="outline"
                      className="text-[9px] ml-2 bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                    >
                      {t("learning.deterministicIcon")}{" "}
                      {t("learning.deterministic")}
                    </Badge>
                  </div>
                  <div className="bg-emerald-50/30 dark:bg-emerald-950/10 p-4 rounded-2xl border border-emerald-500/20">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-emerald-500/20 text-emerald-700 dark:text-emerald-400">
                          <th className="text-left py-2 px-2 w-10 font-bold">
                            {t("common.hash")}
                          </th>
                          <th className="text-left py-2 px-2 w-16 font-bold">
                            {t("macroEditor.type")}
                          </th>
                          <th className="text-left py-2 px-2 w-20 font-bold">
                            {t("macroEditor.eventType")}
                          </th>
                          <th className="text-left py-2 px-2 font-bold">
                            {t("macroEditor.selector")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {flattenedMacro.map((step: any, i: number) => (
                          <tr
                            key={i}
                            className="border-b border-emerald-500/10 last:border-0 hover:bg-emerald-500/5"
                          >
                            <td className="py-2 px-2 font-mono text-emerald-600 font-bold">
                              <div className="flex items-center">
                                {step.depth > 0 && (
                                  <div className="flex mr-1.5 h-4 items-center">
                                    {[...Array(Number(step.depth) || 0)].map(
                                      (_, idx) => (
                                        <div
                                          key={idx}
                                          className="w-2.5 h-full border-l-2 border-emerald-500/20 ml-1"
                                        />
                                      ),
                                    )}
                                  </div>
                                )}
                                {String(step.step_number || i + 1)}
                              </div>
                            </td>
                            <td className="py-2 px-2">
                              <Badge
                                variant="outline"
                                className="text-[9px] capitalize bg-background"
                              >
                                {step.type
                                  ? String(
                                      t(`macroEditor.stepTypes.${step.type}`),
                                    )
                                  : "-"}
                              </Badge>
                            </td>
                            <td className="py-2 px-2">
                              <span className="capitalize">
                                {step.event_type
                                  ? String(
                                      t(
                                        `macroEditor.eventTypes.${step.event_type}`,
                                      ),
                                    )
                                  : "-"}
                              </span>
                            </td>
                            <td className="py-2 px-2">
                              <code className="text-[10px] font-mono text-muted-foreground bg-background/80 px-1.5 py-0.5 rounded">
                                {step.selector || step.target_selector || "-"}
                              </code>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="mt-3 flex items-center gap-2 pt-3 border-t border-border border-emerald-500/20">
                      <Badge
                        variant="outline"
                        className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[9px] font-bold"
                      >
                        {t("learning.steps", {
                          count: flattenedMacro.length,
                        })}
                      </Badge>
                    </div>
                  </div>
                </section>
              </>
            )}

            <Separator className="opacity-50" />

            {/* Metadata & Inputs */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <section className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  <Layout className="h-4 w-4" />
                  {t("learning.parameters")}
                </div>
                {parameters && parameters.length > 0 ? (
                  <div className="space-y-2">
                    {parameters.map((param: any, i: number) => (
                      <div
                        key={i}
                        className="bg-muted/20 p-3 rounded-lg border border-border text-xs"
                      >
                        <div className="font-bold flex items-center justify-between">
                          {param.name}
                          <span className="text-[9px] opacity-40 uppercase">
                            {param.type}
                          </span>
                        </div>
                        <p className="text-muted-foreground mt-0.5">
                          {param.description}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[10px] text-muted-foreground italic">
                    {t("learning.execution.noParams")}
                  </p>
                )}
              </section>

              <section className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  {t("learning.history")}
                </div>
                <div className="space-y-2 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
                      {t("learning.created")}
                    </span>
                    <span>
                      {new Intl.DateTimeFormat(i18n.language, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      }).format(new Date(skill.created_at))}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
                      {t("learning.successCountLabel")}
                    </span>
                    <span className="text-green-600 font-bold">
                      {skill.success_count || 0}
                    </span>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-border bg-card mt-auto flex gap-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)]">
          {skill.status === "pending_review" ? (
            <Button
              variant="default"
              className="flex-1 h-10 font-medium shadow-sm transition-all hover:shadow-md bg-emerald-600 hover:bg-emerald-700"
              onClick={() => confirmMutation.mutate(skill.id)}
              disabled={confirmMutation.isPending}
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              {confirmMutation.isPending
                ? t("common.processing")
                : t("common.confirm")}
            </Button>
          ) : (
            <Button
              variant="default"
              className="flex-1 h-10 font-medium shadow-sm transition-all hover:shadow-md"
              disabled={!isSkillRoutable(skill)}
              title={
                isSkillRoutable(skill)
                  ? undefined
                  : t("learning.runNeedsConfirm")
              }
              onClick={() => {
                onRun?.(skill)
                onOpenChange(false)
              }}
            >
              <Play className="h-4 w-4 mr-2 fill-current" />
              {t("learning.runSkill")}
            </Button>
          )}
          <Button
            variant="outline"
            className="h-10 px-4"
            onClick={() => {
              onEdit?.(skill)
              onOpenChange(false)
            }}
          >
            <Edit className="h-4 w-4 mr-2" />
            {t("common.edit")}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-destructive hover:bg-destructive/10"
            onClick={() => {
              onDelete?.(skill.id)
              onOpenChange(false)
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
