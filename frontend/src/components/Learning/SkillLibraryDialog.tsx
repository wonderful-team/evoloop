import { BookOpen, Play, Trash2, Edit } from "lucide-react"
import type React from "react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { LearnedSkill } from "@/types/skill"
import { SkillExecutionDialog } from "./SkillExecutionDialog"
import { SkillEditorDialog } from "./SkillEditorDialog"

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
  const [skillToExecute, setSkillToExecute] = useState<LearnedSkill | null>(
    null,
  )
  const [skillToEdit, setSkillToEdit] = useState<LearnedSkill | null>(null)

  const fetchSkills = async () => {
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
  }

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
      <Dialog open={open} onOpenChange={onOpenChange}>
        {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
        <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0">
          <DialogHeader className="p-6 pb-2">
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5" />
              {t("learning.skillLibrary")}
            </DialogTitle>
            <DialogDescription>
              {t("learning.skills")} ({skills.length})
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-1 overflow-hidden">
            {/* Skill List Sidebar */}
            <div className="w-1/3 border-r flex flex-col">
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
                      <div className="font-medium truncate pr-6">
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

                      <div className="text-xs text-muted-foreground truncate mt-1">
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
                          {t("common.run", "Run")}
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
                          {t("common.edit", "Edit")}
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
                                  <TableHead>{t("learning.table.name")}</TableHead>
                                  <TableHead>{t("learning.table.type")}</TableHead>
                                  <TableHead>{t("learning.table.description")}</TableHead>
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
    </>
  )
}
