import { BookOpen, Play, Trash2, Edit, Terminal, TrendingUp, Info, Sparkles, Layout } from "lucide-react"
import type React from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { LearningService } from "@/client/sdk.gen"
import type { PaginatedSkillsResponse } from "@/client/types.gen"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import type { LearnedSkill } from "@/types/skill"
import { SkillExecutionDialog } from "./SkillExecutionDialog"
import { Separator } from "@evoloop/shared/components/ui/separator"


interface SkillLibraryDialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  trigger?: React.ReactNode
  threadId: string
  projectId?: number
}


export function SkillLibraryDialog({
  open,
  onOpenChange,
  trigger,
  threadId,
  projectId,
}: SkillLibraryDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [selectedSkill, setSelectedSkill] = useState<LearnedSkill | null>(null)
  const [executionOpen, setExecutionOpen] = useState(false)
  const [skillToExecute, setSkillToExecute] = useState<LearnedSkill | null>(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const { data, isLoading } = useQuery({
    queryKey: ["learnedSkills", page, pageSize],
    queryFn: async () => {
      const result = (await LearningService.listSkills({
        activeOnly: true,
        page,
        pageSize,
      })) as unknown as PaginatedSkillsResponse

      // Handle response format
      if (result && Array.isArray(result.items)) {
        return result
      } else if (Array.isArray((result as any).skills)) {
        // Fallback
        return {
          items: (result as any).skills,
          total: (result as any).skills.length,
          page: 1,
          page_size: pageSize,
          total_pages: 1,
        } as PaginatedSkillsResponse
      }
      return { items: [], total: 0, page: 1, page_size: pageSize, total_pages: 0 } as PaginatedSkillsResponse
    },
    enabled: open,
  })

  const skills = data?.items || []
  const totalPages = data?.total_pages || 0
  const loading = isLoading



  const handleDelete = async (skillId: number) => {
    if (!confirm(t("learning.confirmDeactivate"))) return

    try {
      await LearningService.deactivateSkill({ skillId })
      toast.success(t("common.success"))
      queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
      if (selectedSkill?.id === skillId) {
        setSelectedSkill(null)
      }
    } catch (error) {
      console.error("Failed to delete skill", error)
      toast.error(t("common.error.message"))
    }
  }

  const handleRunClick = (skill: LearnedSkill, e: React.MouseEvent) => {
    e.stopPropagation()
    setSkillToExecute(skill)
    setExecutionOpen(true)
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(val) => {
          onOpenChange?.(val);
        }}
      >
        {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
        <DialogContent className="!max-w-7xl w-[90vw] h-[85vh] flex flex-col p-0 gap-0">
          <DialogHeader className="p-6 pb-2">
            <div className="flex items-center justify-between">
              <DialogTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                {t("learning.skillLibrary", "Skill Library")}
              </DialogTitle>

            </div>
          </DialogHeader>

          <div className="flex-1 flex overflow-hidden border-t">
            {/* Skill List Sidebar */}
            <div className="w-1/3 min-w-[300px] border-r flex flex-col">
              <ScrollArea className="flex-1">
                <div className="p-4 space-y-2">
                  {skills.length === 0 && !loading && (
                    <div className="text-center text-muted-foreground py-8 text-sm">
                      {t("learning.noSkills")}
                    </div>
                  )}
                  {skills.map((skill) => (
                    <div
                      key={skill.id}
                      className={`p-3 rounded-xl border cursor-pointer hover:bg-accent/50 transition-all group relative ${selectedSkill?.id === skill.id
                        ? "bg-accent border-primary shadow-sm"
                        : "bg-card hover:border-primary/20"
                        }`}
                      onClick={() => setSelectedSkill(skill as unknown as LearnedSkill)}
                    >
                      <div className="font-semibold text-sm break-words pr-6 leading-tight">
                        {skill.name}
                      </div>
                      <div className="text-xs text-muted-foreground/80 line-clamp-2 mt-1.5 leading-relaxed">
                        {skill.description}
                      </div>
                      <div className="flex gap-2 mt-2.5">
                        <Badge variant="secondary" className="text-[10px] px-1.5 h-5 font-medium">
                          {t("learning.toolsCount", { count: skill.tools_used.length })}
                        </Badge>
                        <Badge
                          variant={skill.success_count > 0 ? "default" : "outline"}
                          className="text-[10px] px-1.5 h-5 font-medium"
                        >
                          {t("learning.successCount", { count: skill.success_count })}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>

              {/* Pagination Controls */}
              <div className="p-2 border-t flex justify-between items-center bg-background/50 text-xs">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  &lt;
                </Button>
                <span className="text-muted-foreground">
                  {page} / {totalPages || 1}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                  disabled={page >= (totalPages || 1) || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  &gt;
                </Button>
              </div>
            </div>

            {/* Skill Detail View */}
            <div className="flex-1 flex flex-col bg-muted/30">
              {selectedSkill ? (
                <>
                  <ScrollArea className="flex-1">
                    <div className="p-6 space-y-8">
                      {/* Header */}
                      <div>
                        <div className="flex items-center gap-2 text-primary mb-2">
                          <Terminal className="h-4 w-4" />
                          <span className="text-xs font-bold uppercase tracking-wider">{t("learning.skillDetails", "Skill Details")}</span>
                        </div>
                        <h3 className="text-2xl font-bold">{selectedSkill.name}</h3>
                        <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{selectedSkill.description}</p>
                      </div>

                      {/* Stats */}
                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-muted/30 p-3 rounded-xl border flex flex-col gap-1">
                          <span className="text-[10px] text-muted-foreground uppercase font-bold">{t("learning.status", "Status")}</span>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20 text-[10px]">
                              {t(`learning.statusBadge.${selectedSkill.status || "active"}`, selectedSkill.status || "active")}
                            </Badge>
                          </div>
                        </div>
                        <div className="bg-muted/30 p-3 rounded-xl border flex flex-col gap-1">
                          <span className="text-[10px] text-muted-foreground uppercase font-bold">{t("learning.performance", "Performance")}</span>
                          <div className="flex items-center gap-2 font-bold text-green-600 text-sm">
                            <TrendingUp className="h-4 w-4" />
                            {selectedSkill.success_count || 0} {t("learning.successes", "Successes")}
                          </div>
                        </div>
                      </div>

                      <Separator />

                      {/* Trigger Patterns */}
                      <section className="space-y-3">
                        <div className="flex items-center gap-2 text-sm font-bold">
                          <Info className="h-4 w-4 text-primary" />
                          {t("learning.triggerPatterns")}
                        </div>
                        {selectedSkill.trigger_patterns && selectedSkill.trigger_patterns.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {selectedSkill.trigger_patterns.map((pattern, idx) => (
                              <code key={idx} className="bg-muted/50 px-3 py-1.5 rounded-lg text-xs font-mono border border-muted-foreground/10 block w-full">
                                {pattern}
                              </code>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground italic">{t("learning.editor.noTriggers")}</p>
                        )}
                      </section>

                      {/* Expert Guide */}
                      {selectedSkill.instructions && (
                        <>
                          <Separator />
                          <section className="space-y-3">
                            <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
                              <Sparkles className="h-4 w-4" />
                              {t("learning.expertGuide", "Expert Guide")}
                            </div>
                            <div className="bg-amber-50/30 dark:bg-amber-950/10 p-4 rounded-xl border border-amber-500/20">
                              <div className="text-xs leading-relaxed whitespace-pre-wrap text-foreground/90 font-medium">
                                {selectedSkill.instructions}
                              </div>
                            </div>
                          </section>
                        </>
                      )}

                      <Separator />

                      {/* Parameters/Inputs */}
                      <section className="space-y-3">
                        <div className="flex items-center gap-2 text-sm font-bold">
                          <Layout className="h-4 w-4 text-primary" />
                          {t("learning.parameters", "Required Inputs")}
                        </div>
                        {selectedSkill.parameters && selectedSkill.parameters.length > 0 ? (
                          <div className="space-y-2">
                            {selectedSkill.parameters.map((param: any, i: number) => (
                              <div key={i} className="bg-muted/30 p-3 rounded-lg border text-xs">
                                <div className="font-bold flex items-center justify-between">
                                  {param.name}
                                  <span className="text-[9px] opacity-40 uppercase">{param.type}</span>
                                </div>
                                <p className="text-muted-foreground mt-0.5">{param.description}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground italic text-[10px]">{t("learning.execution.noParams", "No inputs required.")}</p>
                        )}
                      </section>
                    </div>
                  </ScrollArea>

                  {/* Footer Actions */}
                  <div className="p-4 border-t bg-card mt-auto flex gap-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)] z-10">
                    <Button
                      variant="default"
                      className="flex-1 h-9 font-medium shadow-sm"
                      onClick={(e) => handleRunClick(selectedSkill, e)}
                    >
                      <Play className="h-4 w-4 mr-2 fill-current" />
                      {t("common.run")}
                    </Button>
                    <Button
                      variant="outline"
                      className="h-9 px-3"
                      onClick={() => {
                        onOpenChange?.(false)
                        navigate({ to: "/learning/skills/$skillId/edit", params: { skillId: selectedSkill.id.toString() } })
                      }}
                    >
                      <Edit className="h-4 w-4 mr-2" />
                      {t("common.edit")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9 text-destructive hover:bg-destructive/10"
                      onClick={() => handleDelete(selectedSkill.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground">
                  <div className="text-center">
                    <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>{t("learning.viewDetails")}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {skillToExecute && (
        <SkillExecutionDialog
          open={executionOpen}
          onOpenChange={setExecutionOpen}
          skill={skillToExecute}
          threadId={threadId}
          projectId={projectId}
        />
      )}
    </>
  )
}
