import { useQuery } from "@tanstack/react-query"
import { Check, ChevronsUpDown, FolderOpen, Search } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectsService } from "../client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@evoloop/shared/components/ui/sheet"
import { cn } from "@evoloop/shared"

interface MobileProjectSwitcherProps {
  project?: any
  onProjectChange?: (project: any) => void
  onLoaded?: (project: any) => void
}

export function MobileProjectSwitcher({
  project,
  onProjectChange,
  onLoaded,
}: MobileProjectSwitcherProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [internalProject, setInternalProject] = useState<any>(null)
  const [searchQuery, setSearchQuery] = useState("")

  const displayProject = project || internalProject

  // Use useQuery for Projects List (Consistent with ProjectsScreen)
  const { data: projectsData, isLoading } = useQuery({
    queryKey: ["evoloop", "projects"],
    queryFn: async () => {
      const res = await ProjectsService.getProjects()
      // Cloud returns { code: 0, data: { list: [...] } }
      if (res.code >= 0) return res.data ?? { list: [] }
      throw new Error(res.message || t("projects.failedToLoad"))
    },
    staleTime: 30000,
  })

  const projects = (projectsData as any)?.list || []

  // Initialize current project if not provided via props
  useEffect(() => {
    if (!project && !internalProject) {
      const fetchCurrent = async () => {
        try {
          const currentRes = await ProjectsService.getCurrentProject()
          if (currentRes.code >= 0 && currentRes.data?.project_id) {
            const current = currentRes.data
            setInternalProject(current)
            onLoaded?.(current)
          } else if (projects.length > 0) {
            // Fallback to first project in list if no "current" set on cloud
            const first = projects[0]
            setInternalProject(first)
            onLoaded?.(first)
          }
        } catch (e) {
          // If getCurrentProject fails, fallback to first in list
          if (projects.length > 0) {
            const first = projects[0]
            setInternalProject(first)
            onLoaded?.(first)
          }
        }
      }
      fetchCurrent()
    }
  }, [project, projects, onLoaded, internalProject])

  // Sync internal if prop changes
  useEffect(() => {
    if (project) {
      setInternalProject(project)
    }
  }, [project])

  const handleSelect = async (selected: any) => {
    if (displayProject?.project_id === selected.project_id) {
      setOpen(false)
      return
    }

    // Optimistic update
    setInternalProject(selected) // Update internal immediately
    onProjectChange?.(selected) // Notify parent
    setOpen(false)

    toast.info(t("projectSwitcher.switching", { name: selected.project_name }))

    try {
      toast.info(
        t("projectSwitcher.switching", { name: selected.project_name }),
      )

      // Deprecated: Switch logic is now client-side or implicit.
      // await EvoLoopApi.switchCloudProject(selected.project_id)
      // Just notify success
      setTimeout(() => {
        toast.success(
          t("projectSwitcher.switched", { name: selected.project_name }),
        )
      }, 300)
    } catch (_e: any) {
      // Logic removed
    }
  }

  const filteredProjects = projects.filter((p: any) =>
    p.project_name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          className="h-auto p-0 hover:bg-transparent gap-1.5"
        >
          <div className="flex flex-col items-center">
            <div className="flex items-center gap-1">
              <span className="font-extrabold text-sm text-foreground tracking-tight truncate max-w-[160px]">
                {displayProject?.project_name || t("projectSwitcher.select")}
              </span>
              <ChevronsUpDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
            </div>
          </div>
        </Button>
      </SheetTrigger>
      <SheetContent
        side="bottom"
        className="h-[80vh] flex flex-col p-4 rounded-t-[10px]"
      >
        <SheetHeader className="mb-4">
          <SheetTitle>{t("projectSwitcher.title")}</SheetTitle>
        </SheetHeader>

        <div className="relative mb-4">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t("projectSwitcher.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
        </div>

        <div className="flex-1 overflow-y-auto -mx-4 px-4">
          <div className="space-y-1 pb-6">
            {isLoading ? (
              <div className="flex justify-center p-8">
                <span className="animate-spin mr-2">◌</span> {t("common.loading")}
              </div>
            ) : filteredProjects.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">
                {t("projectSwitcher.noProjects")}
              </div>
            ) : (
              filteredProjects.map((p: any) => (
                <div
                  key={p.project_id}
                  className={cn(
                    "flex items-center justify-between p-3 rounded-lg border",
                    displayProject?.project_id === p.project_id
                      ? "bg-primary/10 border-primary/50"
                      : "bg-background border-border",
                  )}
                  onClick={() => handleSelect(p)}
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="bg-muted p-2 rounded-md shrink-0">
                      <FolderOpen className="h-4 w-4" />
                    </div>
                    <div className="flex flex-col overflow-hidden">
                      <span className="font-medium text-sm truncate">
                        {p.project_name}
                      </span>
                      <span className="text-xs text-muted-foreground truncate">
                        {p.project_desc || t("projectSwitcher.noDesc")}
                      </span>
                    </div>
                  </div>
                  {displayProject?.project_id === p.project_id && (
                    <Check className="h-4 w-4 text-primary shrink-0" />
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
