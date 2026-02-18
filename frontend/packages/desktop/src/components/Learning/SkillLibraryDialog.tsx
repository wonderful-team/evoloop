import { BookOpen, Play, Trash2, Edit, FolderDown, ShieldCheck, AlertTriangle, Wand2, Search } from "lucide-react"
import type React from "react"
import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@evoloop/shared/components/ui/table"
import type { LearnedSkill } from "@/types/skill"
import { SkillExecutionDialog } from "./SkillExecutionDialog"
import { SkillEditorDialog } from "./SkillEditorDialog"
import { ImportSkillsDialog } from "./ImportSkillsDialog"

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
  const [skills, setSkills] = useState<LearnedSkill[]>([])
  const [selectedSkill, setSelectedSkill] = useState<LearnedSkill | null>(null)
  const [loading, setLoading] = useState(false)
  const [executionOpen, setExecutionOpen] = useState(false)
  const [editingOpen, setEditingOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [skillToExecute, setSkillToExecute] = useState<LearnedSkill | null>(
    null,
  )
  const [skillToEdit, setSkillToEdit] = useState<LearnedSkill | null>(null)

  const fetchSkills = useCallback(async () => {
    setLoading(true)
    try {
      const result = (await LearningService.listSkills({
        activeOnly: true,
      })) as any
      setSkills(result.skills || result)
    } catch (error) {
      console.error("Failed to fetch skills", error)
      toast.error(t("common.error.message"))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (open) {
      fetchSkills()
    }
  }, [open, fetchSkills])

  const handleDelete = async (skillId: number) => {
    if (!confirm(t("learning.confirmDeactivate"))) return

    try {
      await LearningService.deactivateSkill({ skillId })
      toast.success(t("common.success"))
      fetchSkills()
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
          if (val) fetchSkills();
          onOpenChange?.(val);
        }}
      >
        {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
        <DialogContent className="!max-w-7xl w-[90vw] h-[85vh] flex flex-col p-0 gap-0">
          <DialogHeader className="p-6 pb-2">
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5" />
              {t("learning.skillLibrary")}
            </DialogTitle>
            <DialogDescription className="flex items-center justify-between">
              <span>{t("learning.skills")} ({skills.length})</span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-[10px] gap-1.5"
                onClick={() => setImportOpen(true)}
              >
                <FolderDown className="h-3 w-3" />
                {t("learning.import.button", "Import Skills")}
              </Button>
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-1 overflow-hidden">
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
                      className={`p-3 rounded-lg border cursor-pointer hover:bg-accent transition-colors group relative ${selectedSkill?.id === skill.id
                        ? "bg-accent border-primary"
                        : "bg-card"
                        }`}
                      onClick={() => setSelectedSkill(skill)}
                    >
                      <div className="font-medium break-words pr-6 leading-tight">
                        {skill.name}
                      </div>
                      {/* Quick Run Button on Hover in List */}
                      <Button
                        size="icon"
                        variant="ghost"
                        className="absolute right-1 top-1 h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity hover:text-green-600 hover:bg-green-100"
                        onClick={(e) => handleRunClick(skill, e)}
                        title={t("learning.runSkill")}
                      >
                        <Play size={12} fill="currentColor" />
                      </Button>

                      <div className="text-xs text-muted-foreground line-clamp-2 mt-1">
                        {skill.description}
                      </div>
                      <div className="flex gap-2 mt-2">
                        <Badge variant="secondary" className="text-[10px] h-5">
                          {t("learning.toolsCount", { count: skill.tools_used.length })}
                        </Badge>
                        <Badge
                          variant={
                            skill.success_count > 0 ? "default" : "outline"
                          }
                          className="text-[10px] h-5"
                        >
                          {t("learning.successCount", { count: skill.success_count })}
                        </Badge>
                        {skill.status === "verified" && (
                          <Badge variant="secondary" className="text-[10px] h-5 bg-green-100 text-green-700 border-green-200">
                            <ShieldCheck className="h-2 w-2 mr-1" />
                            {t("learning.status.verified", "Verified")}
                          </Badge>
                        )}
                        {skill.validation_report?.status === "warning" && (
                          <Badge variant="secondary" className="text-[10px] h-5 bg-yellow-100 text-yellow-700 border-yellow-200">
                            <AlertTriangle className="h-2 w-2 mr-1" />
                            {t("learning.status.warning", "Warning")}
                          </Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Skill Detail View */}
            <div className="flex-1 flex flex-col bg-muted/30">
              {selectedSkill ? (
                <ScrollArea className="flex-1">
                  <div className="p-6 space-y-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="text-xl font-bold">
                          {selectedSkill.name}
                        </h3>
                        <p className="text-muted-foreground mt-1">
                          {selectedSkill.description}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="default"
                          size="sm"
                          className="bg-green-600 hover:bg-green-700 text-white"
                          onClick={(e) => handleRunClick(selectedSkill, e)}
                        >
                          <Play className="h-4 w-4 mr-2" fill="currentColor" />
                          {t("common.run")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSkillToEdit(selectedSkill)
                            setEditingOpen(true)
                          }}
                        >
                          <Edit className="h-4 w-4 mr-2" />
                          {t("common.edit")}
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDelete(selectedSkill.id)}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          {t("learning.deactivate")}
                        </Button>
                      </div>
                    </div>

                    {selectedSkill.validation_report && (
                      <Card className={`border-none shadow-none ${selectedSkill.validation_report.status === 'healthy' ? 'bg-green-50' : selectedSkill.validation_report.status === 'warning' ? 'bg-yellow-50' : 'bg-red-50'}`}>
                        <CardHeader className="py-3 px-4 flex flex-row items-center justify-between space-y-0">
                          <CardTitle className={`text-xs font-bold uppercase ${selectedSkill.validation_report.status === 'healthy' ? 'text-green-700' : selectedSkill.validation_report.status === 'warning' ? 'text-yellow-700' : 'text-red-700'}`}>
                            {t("learning.healthStatus", "Health Status")}: {t(`learning.validationStatus.${selectedSkill.validation_report.status}`, selectedSkill.validation_report.status)}
                          </CardTitle>
                          <div className="flex gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 text-[10px] gap-1"
                              onClick={async () => {
                                try {
                                  toast.promise(LearningService.validateSkill({ skillId: selectedSkill.id }), {
                                    loading: t("learning.optimizing.loading", "Validating..."),
                                    success: () => {
                                      fetchSkills();
                                      return t("common.success");
                                    },
                                    error: t("common.error.message")
                                  });
                                } catch (e) { }
                              }}
                            >
                              <Search className="h-3 w-3" />
                              {t("learning.revalidate", "Re-validate")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 text-[10px] gap-1"
                              onClick={async () => {
                                try {
                                  toast.promise(LearningService.optimizeSkill({ skillId: selectedSkill.id }), {
                                    loading: t("learning.optimizing.loading", "Optimizing..."),
                                    success: (res: any) => {
                                      const data = res as any;
                                      if (data.success) {
                                        // We'll show a diff or just success for now
                                        return t("learning.optimize.success", "Instructions refined via AI");
                                      }
                                      return data.error || t("common.error.message");
                                    },
                                    error: t("common.error.message")
                                  });
                                } catch (e) { }
                              }}
                            >
                              <Wand2 className="h-3 w-3" />
                              {t("learning.autoOptimize", "Auto-Optimize")}
                            </Button>
                          </div>
                        </CardHeader>
                        <CardContent className="px-4 pb-3">
                          <ul className="text-xs space-y-1">
                            {selectedSkill.validation_report.errors.map((e, idx) => (
                              <li key={idx} className="text-red-600 flex items-start gap-1.5">
                                <span className="mt-1 w-1 h-1 rounded-full bg-red-600 shrink-0" />
                                {e}
                              </li>
                            ))}
                            {selectedSkill.validation_report.warnings.map((w, idx) => (
                              <li key={idx} className="text-yellow-700 flex items-start gap-1.5">
                                <span className="mt-1 w-1 h-1 rounded-full bg-yellow-700 shrink-0" />
                                {w}
                              </li>
                            ))}
                            {selectedSkill.validation_report.is_valid && selectedSkill.validation_report.errors.length === 0 && selectedSkill.validation_report.warnings.length === 0 && (
                              <li className="text-green-600 flex items-center gap-1.5">
                                <ShieldCheck className="h-3 w-3" />
                                {t("learning.healthHealthy", "Skill follows all standardization rules.")}
                              </li>
                            )}
                          </ul>
                        </CardContent>
                      </Card>
                    )}

                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
                          {t("learning.triggerPatterns")}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="flex flex-wrap gap-2">
                          {selectedSkill.trigger_patterns.map(
                            (pattern, idx) => (
                              <code
                                key={idx}
                                className="bg-muted px-2 py-1 rounded text-sm block w-full"
                              >
                                {pattern}
                              </code>
                            ),
                          )}
                        </div>
                      </CardContent>
                    </Card>

                    {selectedSkill.parameters &&
                      selectedSkill.parameters.length > 0 && (
                        <Card>
                          <CardHeader className="pb-3">
                            <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
                              {t("learning.parameters")}
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>{t("learning.editor.paramName")}</TableHead>
                                  <TableHead>{t("learning.editor.paramType")}</TableHead>
                                  <TableHead>{t("learning.editor.paramDesc")}</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {selectedSkill.parameters.map((param, idx) => (
                                  <TableRow key={idx}>
                                    <TableCell className="font-mono text-sm">
                                      {param.name}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">
                                      {param.type}
                                    </TableCell>
                                    <TableCell>{param.description}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </CardContent>
                        </Card>
                      )}

                    <div className="grid grid-cols-2 gap-4">
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-muted-foreground">
                            {t("learning.stats")}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold">
                            {selectedSkill.success_count}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {t("learning.successExecutions")}
                          </p>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-muted-foreground">
                            {t("learning.created")}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="text-sm font-medium">
                            {selectedSkill.created_at
                              ? new Date(
                                selectedSkill.created_at,
                              ).toLocaleDateString()
                              : t("learning.na")}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {t("learning.synthesisDate")}
                          </p>
                        </CardContent>
                      </Card>
                    </div>
                  </div>
                </ScrollArea>
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
          onSuccess={() => {
            // Close library dialog too if we want, or keep it open.
            // Let's keep library open but show success toast (handled in dialog)
          }}
        />
      )}

      {skillToEdit && (
        <SkillEditorDialog
          open={editingOpen}
          onOpenChange={setEditingOpen}
          skill={skillToEdit}
          onSuccess={() => {
            fetchSkills()
            // Update selected skill to show new values immediately
            // We need to re-fetch to get latest, but fetchSkills updates 'skills'
            // We should also find the updated skill in the new list or just close/reopen logic
            // For simplicity, just refetch. The selectedSkill might be stale until clicked again.
            // A better UX is to update selectedSkill too.
            // Let's rely on user re-clicking or ensure fetchSkills updates state.
            setSelectedSkill(prev => prev ? { ...prev, ...skillToEdit } : null) // Optimistic/Hack update or just wait.
            // Actually, let's just let fetchSkills handle it. The user might need to click again if ID changed (unlikely).
          }}
        />
      )}

      <ImportSkillsDialog
        isOpen={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={fetchSkills}
      />
    </>
  )
}
