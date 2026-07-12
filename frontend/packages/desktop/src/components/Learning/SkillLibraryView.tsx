import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Input } from "@evoloop/shared/components/ui/input"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  BookOpen,
  Clock,
  Edit,
  FolderDown,
  MoreVertical,
  Play,
  Search,
  Terminal,
  Trash2,
  TrendingUp,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import type { PaginatedSkillsResponse } from "@/client/types.gen"
import type { LearnedSkill } from "@/types/skill"
import { ImportSkillsDialog } from "./ImportSkillsDialog"
import { SkillDetailsPanel } from "./SkillDetailsPanel"
import { SkillExecutionDialog } from "./SkillExecutionDialog"
import { isSkillRoutable } from "./skillLifecycle"

interface SkillLibraryViewProps {
  threadId: string
  projectId?: number
  highlightSkillId?: number | null
  onClearHighlight?: () => void
}

export function SkillLibraryView({
  threadId,
  projectId,
  highlightSkillId,
  onClearHighlight,
}: SkillLibraryViewProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState("")
  const [skillToExecute, setSkillToExecute] = useState<LearnedSkill | null>(
    null,
  )
  const [selectedSkill, setSelectedSkill] = useState<LearnedSkill | null>(null)
  const [executionOpen, setExecutionOpen] = useState(false)

  const [detailsOpen, setDetailsOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  // Pagination
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const { data, isLoading } = useQuery({
    queryKey: ["learnedSkills", page, pageSize],
    queryFn: async () => {
      const result = (await LearningService.listSkills({
        activeOnly: false,
        page,
        pageSize,
      })) as unknown as PaginatedSkillsResponse

      // Handle response format
      if (result && Array.isArray(result.data)) {
        return result
      }
      if (Array.isArray((result as any).skills)) {
        // Fallback
        return {
          data: (result as any).skills,
          total: (result as any).skills.length,
          page: 1,
          page_size: pageSize,
          total_pages: 1,
        } as PaginatedSkillsResponse
      }
      return {
        data: [],
        total: 0,
        page: 1,
        page_size: pageSize,
        total_pages: 0,
      } as PaginatedSkillsResponse
    },
  })

  const skills = data?.data || []
  const totalSkills = data?.total || 0
  const totalPages = data?.total_pages || 0

  // Handle auto-navigate to editor if highlightSkillId is provided
  useEffect(() => {
    if (highlightSkillId && (skills as LearnedSkill[]).length > 0) {
      const skill = (skills as LearnedSkill[]).find(
        (s: LearnedSkill) => s.id === highlightSkillId,
      )
      if (skill) {
        navigate({
          to: "/learning/skills/$skillId/edit",
          params: { skillId: skill.id.toString() },
        })
        onClearHighlight?.()
      }
    }
  }, [highlightSkillId, skills, onClearHighlight, navigate])

  const deleteMutation = useMutation({
    mutationFn: (skillId: number) =>
      (LearningService as any).deleteSkill({ skillId }),
    onSuccess: () => {
      toast.success(t("learning.skillDeactivated"))
      queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
    },
    onError: (error: any) => {
      toast.error(error.message || t("common.error.message"))
    },
  })

  const filteredSkills = useMemo(() => {
    const items = skills as unknown as LearnedSkill[]
    if (!searchQuery) return items
    const q = searchQuery.toLowerCase()
    return items.filter(
      (s: LearnedSkill) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q),
    )
  }, [skills, searchQuery])

  const handleRunClick = (skill: LearnedSkill) => {
    setSkillToExecute(skill)
    setExecutionOpen(true)
  }

  const handleDelete = (skillId: number) => {
    deleteMutation.mutate(skillId)
  }

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t("learning.searchSkills")}
            className="pl-10"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-10 text-xs gap-1.5"
            onClick={() => setImportOpen(true)}
          >
            <FolderDown className="h-3.5 w-3.5" />
            {t("learning.import.button")}
          </Button>
          <Badge variant="outline" className="px-3 py-1 font-bold">
            {totalSkills} {t("learning.totalSkills")}
          </Badge>
        </div>
      </div>

      {/* Grid */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-1">
            {[1, 2, 3].map((i) => (
              <Card
                key={i}
                className="animate-pulse bg-muted h-48 rounded-xl"
              />
            ))}
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 bg-muted/10 rounded-2xl border-2 border-dashed">
            <BookOpen className="h-12 w-12 text-muted-foreground mb-4 opacity-20" />
            <p className="text-muted-foreground">
              {t("learning.noSkillsFound")}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-1">
            {(filteredSkills as unknown as LearnedSkill[]).map(
              (skill: LearnedSkill) => (
                <Card
                  key={skill.id}
                  className="group hover:border-primary/30 transition-all border border-border shadow-sm rounded-xl overflow-hidden flex flex-col cursor-pointer"
                  onClick={() => {
                    setSelectedSkill(skill)
                    setDetailsOpen(true)
                  }}
                >
                  <CardHeader className="p-4 pb-2">
                    <div className="flex items-start justify-between">
                      <div className="flex gap-4">
                        <div className="p-2 bg-primary/5 rounded-xl border border-border border-primary/10 group-hover:bg-primary/10 transition-colors h-fit mt-1">
                          <Terminal className="h-4 w-4 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-base font-semibold leading-tight line-clamp-1 tracking-tight">
                            {skill.name}
                          </CardTitle>
                          <div className="flex items-center gap-2 mt-1.5">
                            <Badge
                              variant="secondary"
                              className="text-[10px] px-1.5 py-0 font-medium bg-muted/50"
                            >
                              {t(
                                `learning.statusBadge.${skill.status || "pending_review"}`,
                              )}
                            </Badge>
                            <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {new Date(skill.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate({
                                to: "/learning/skills/$skillId/edit",
                                params: { skillId: skill.id.toString() },
                              })
                            }}
                          >
                            <Edit className="mr-2 h-4 w-4" /> {t("common.edit")}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDelete(skill.id)
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />{" "}
                            {t("common.delete")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </CardHeader>
                  <CardContent className="p-4 pt-2 flex-1">
                    <p className="text-[13px] text-muted-foreground/90 line-clamp-2 leading-relaxed h-10">
                      {skill.description}
                    </p>

                    {/* Trigger Preview */}
                    <div className="mt-3 bg-muted/20 p-2 rounded-lg border border-dashed text-[10px] font-mono text-muted-foreground/70 truncate">
                      {skill.trigger_patterns
                        ? typeof skill.trigger_patterns === "string"
                          ? JSON.parse(skill.trigger_patterns)[0]
                          : skill.trigger_patterns[0]
                        : t("learning.editor.noTriggers")}
                    </div>

                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {skill.instructions && (
                        <Badge
                          variant="default"
                          className="text-[9px] bg-amber-500/10 text-amber-600 border-amber-500/20 hover:bg-amber-500/20"
                        >
                          <Terminal className="h-3 w-3 mr-1" />{" "}
                          {t("learning.expertBadge")}
                        </Badge>
                      )}
                      {skill.tools_used?.slice(0, 2).map((tool, j) => (
                        <Badge
                          key={j}
                          variant="outline"
                          className="text-[9px] bg-muted/30 border-transparent"
                        >
                          {tool}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                  <CardFooter className="p-4 pt-0 flex justify-between items-center">
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-medium">
                      <TrendingUp className="h-3 w-3 text-green-500" />
                      {skill.success_count || 0} {t("learning.uses")}
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-8 gap-1.5 text-xs font-medium px-3"
                      disabled={!isSkillRoutable(skill)}
                      title={
                        isSkillRoutable(skill)
                          ? undefined
                          : t("learning.runNeedsConfirm")
                      }
                      onClick={(e) => {
                        e.stopPropagation()
                        handleRunClick(skill)
                      }}
                    >
                      <Play className="h-3 w-3 fill-current" />
                      {t("common.run")}
                    </Button>
                  </CardFooter>
                </Card>
              ),
            )}
          </div>
        )}
      </ScrollArea>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-4 py-2 bg-card border-t text-sm">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1 || isLoading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            &lt; {t("common.previous")}
          </Button>
          <span className="text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages || isLoading}
            onClick={() => setPage((p) => p + 1)}
          >
            {t("common.next")} &gt;
          </Button>
        </div>
      )}

      {skillToExecute && (
        <SkillExecutionDialog
          open={executionOpen}
          onOpenChange={setExecutionOpen}
          skill={skillToExecute}
          threadId={threadId}
          projectId={projectId}
        />
      )}

      <ImportSkillsDialog
        isOpen={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={() =>
          queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
        }
      />

      <SkillDetailsPanel
        skill={selectedSkill}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        onRun={handleRunClick}
        onEdit={(s) =>
          navigate({
            to: "/learning/skills/$skillId/edit",
            params: { skillId: s.id.toString() },
          })
        }
        onDelete={handleDelete}
      />

      {/* If SynthesizeSkillDialog is triggered from here or MirrorConsole,
                ensure it has the callback. For now let's assume it's in MirrorConsole
                as well, but if we need a global link, we'd put it here.
             */}
    </div>
  )
}
