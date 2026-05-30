import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FileTree } from "@/components/Files/FileTree"
import { ChangesetTreeSection } from "./ChangesetTreeSection"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { ChevronDown, ChevronRight, Files, History, Globe, Wand2, Rocket, BookOpen, Edit, RefreshCw } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@evoloop/shared/components/ui/tooltip"
import { WikiService } from "@/client"
import { useQueryClient, useQuery } from "@tanstack/react-query"
import { FilesService } from "@/client"
import { useProjectStore, isGlobalProject } from "@/stores/projectStore"
import { DiscoverDialog } from "@/components/Projects/Modules/Overview/DiscoverDialog"
import { Link } from "@tanstack/react-router"
import { FilePreviewModal } from "@/components/Files/FilePreviewModal"
import { Button } from "@evoloop/shared/components/ui/button"

import { ProjectProfileDrawer } from "@/components/Files/ProjectProfileDrawer"
import { FolderPlus, Upload } from "lucide-react"

interface SidebarFilesTabProps {
  projectId?: number
  activeThreadId?: string
  onSelectDiff?: (path: string, diff: string) => void
  onQuoteFile?: (file: any) => void
  expandChanges?: boolean // Whether to expand Agent Changes panel by default
}

export function SidebarFilesTab({ projectId, activeThreadId, onSelectDiff, onQuoteFile, expandChanges = false }: SidebarFilesTabProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const currentProject = useProjectStore(s => s.currentProject)
  const fetchProjects = useProjectStore(s => s.fetchProjects)
  const [isProjectOpen, setIsProjectOpen] = useState(true)
  const [isChangesOpen, setIsChangesOpen] = useState(expandChanges)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ path: string; name: string } | null>(null)
  const [isCreatingRootFolder, setIsCreatingRootFolder] = useState(false)

  // Check for global mode (projectId is 0)
  const isGlobal = isGlobalProject(projectId ? { id: projectId } as any : null)

  const { data: rootFiles } = useQuery({
    queryKey: ["files", projectId || 0, ""],
    queryFn: () => FilesService.listFiles({ projectId: projectId || 0, path: "" }),
    enabled: projectId !== undefined,
  })

  const hasProjectProfile = Array.isArray(rootFiles) && rootFiles.some((f: any) => f.name === "PROJECT.md")

  const handleGenerateWiki = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isGlobal || !projectId) return

    try {
      await WikiService.generateWiki({
        requestBody: {
          project_id: projectId,
          topic: t("wiki.topic.full_documentation", { defaultValue: "完整项目百科" }),
          force_regenerate: true
        }
      })
      toast.success(t("wiki.toast.start", { defaultValue: "百科生成已开始！将在后台运行。" }))
      queryClient.invalidateQueries({ queryKey: ["wiki"] })
      fetchProjects()
    } catch (error) {
      console.error("Failed to start wiki generation task:", error)
      toast.error(t("wiki.toast.error", { defaultValue: "启动百科生成任务失败" }))
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/5">
      {/* Project Files Section - Flexible to fill space */}
      <Collapsible
        open={isProjectOpen}
        onOpenChange={setIsProjectOpen}
        className="flex-1 flex flex-col min-h-0 overflow-hidden"
      >
        <CollapsibleTrigger asChild>
          <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b border-border bg-muted/20">
            {isProjectOpen ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            {isGlobal ? (
              <Globe className="h-3.5 w-3.5 text-blue-500" />
            ) : (
              <Files className="h-3.5 w-3.5 text-primary/70" />
            )}
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
              {isGlobal
                ? t("chat.sidebar.workspaceFiles", { defaultValue: "工作区文件" })
                : t("chat.sidebar.projectFiles", { defaultValue: "项目文件" })}
            </span>

            <div className="flex items-center gap-0.5">
              {projectId !== undefined && (
                <>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-primary" onClick={(e) => {
                        e.stopPropagation()
                        setIsProjectOpen(true)
                        setIsCreatingRootFolder(true)
                      }}>
                        <FolderPlus className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{t("files.newFolder", { defaultValue: "新建文件夹" })}</TooltipContent>
                  </Tooltip>
                  
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="relative h-6 w-6">
                        <Button variant="ghost" size="icon" className="h-6 w-6 absolute inset-0 text-muted-foreground hover:text-primary" onClick={(e) => e.stopPropagation()}>
                          <Upload className="h-3.5 w-3.5" />
                        </Button>
                        <input
                          type="file"
                          multiple
                          className="absolute inset-0 opacity-0 cursor-pointer"
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            if (!e.target.files?.length) return
                            const dt = new DataTransfer()
                            for (let i = 0; i < e.target.files.length; i++) {
                              dt.items.add(e.target.files[i])
                            }
                            FilesService.workspaceUpload({ projectId, formData: { target_dir: "", file: e.target.files[0] as any } }) // Note: simplistic upload for root, better handled in FileTree
                              .then(() => queryClient.invalidateQueries({ queryKey: ["files", projectId] }))
                              .catch(() => toast.error(t("files.uploadError", { defaultValue: "上传失败" })))
                          }}
                        />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top">{t("files.uploadFile", { defaultValue: "上传文件" })}</TooltipContent>
                  </Tooltip>
                </>
              )}

              {/* Project Actions Dropdown */}
              <DropdownMenu>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <div className="p-1 hover:bg-muted rounded-md transition-colors group/trigger">
                        <Wand2 className={cn("h-3.5 w-3.5 text-muted-foreground/60 group-hover/trigger:text-primary transition-colors", isGlobal && "opacity-40")} />
                      </div>
                    </DropdownMenuTrigger>
                  </TooltipTrigger>
                  {isGlobal && (
                    <TooltipContent side="top">
                      {t("chat.sidebar.projectOnly", { defaultValue: "仅项目内可用" })}
                    </TooltipContent>
                  )}
                </Tooltip>
                
                <DropdownMenuContent align="end" className="w-56" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenuLabel className="text-[11px] font-bold uppercase tracking-tight text-muted-foreground/80">
                    {t("chat.sidebar.actions", { defaultValue: "项目操作" })}
                    {isGlobal && <span className="ml-2 text-[10px] font-normal lowercase opacity-60">({t("chat.sidebar.projectOnly", { defaultValue: "仅项目内可用" })})</span>}
                  </DropdownMenuLabel>
                <DropdownMenuSeparator />
                

                
                <DropdownMenuItem 
                  disabled={isGlobal || currentProject?.wiki_status === "running"}
                  onClick={handleGenerateWiki}
                  className="gap-2 text-xs py-2 cursor-pointer"
                >
                  <BookOpen className="h-3.5 w-3.5 text-green-500" />
                  <span>{currentProject?.has_wiki ? t("wiki.regenerate_action", { defaultValue: "重新生成百科" }) : t("chat.sidebar.wiki", { defaultValue: "生成项目百科" })}</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        </CollapsibleTrigger>
        <CollapsibleContent className="flex-1 overflow-y-auto">
          <div className="p-2 h-full flex flex-col">
            {projectId !== undefined ? (
              <>
                <div className="mb-2">
                  {hasProjectProfile ? (
                    <div 
                      className="px-3 py-2 border border-muted/50 rounded-md bg-muted/10 hover:bg-muted/30 transition-colors flex items-center justify-between group cursor-pointer" 
                      onClick={() => setPreviewFile({ path: "PROJECT.md", name: "PROJECT.md" })}
                    >
                      <div className="flex items-center gap-2 text-sm text-primary">
                        <BookOpen className="h-4 w-4" />
                        <span className="font-medium">PROJECT.md</span>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={(e) => {
                              e.stopPropagation()
                              setDiscoverOpen(true)
                            }}>
                              <RefreshCw className="h-3 w-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="top">{t("projects.profile.reanalyze", { defaultValue: "重新分析项目" })}</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={(e) => {
                              e.stopPropagation()
                              setPreviewFile({ path: "PROJECT.md", name: "PROJECT.md" })
                            }}>
                              <Edit className="h-3 w-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="top">{t("common.edit", { defaultValue: "编辑" })}</TooltipContent>
                        </Tooltip>
                      </div>
                    </div>
                  ) : (
                    <div className="px-3 py-3 border border-dashed border-muted-foreground/30 rounded-md bg-muted/5 flex flex-col items-center justify-center gap-2 text-center">
                      <p className="text-[11px] text-muted-foreground leading-tight">
                        {t("projects.profile.missing", { defaultValue: "缺少项目资料，这会影响 Agent 的理解。" })}
                      </p>
                      <Button variant="outline" size="sm" className="h-7 text-xs w-full bg-background" onClick={() => setDiscoverOpen(true)}>
                        <Wand2 className="h-3 w-3 mr-1.5 text-primary" />
                        {t("projects.profile.discoverTitle", { defaultValue: "分析与初始化" })}
                      </Button>
                    </div>
                  )}
                </div>
                <div className="flex-1 overflow-auto">
                  <FileTree
                    projectId={projectId}
                    onSelectFile={(file) => setPreviewFile({ path: file.path, name: file.name })}
                    onQuoteFile={onQuoteFile}
                    isCreatingRootFolder={isCreatingRootFolder}
                    onCancelCreateRootFolder={() => setIsCreatingRootFolder(false)}
                    onCreateRootFolder={async (name) => {
                      try {
                        await FilesService.createDirectory({ projectId, requestBody: { path: name } })
                        queryClient.invalidateQueries({ queryKey: ["files", projectId] })
                        setIsCreatingRootFolder(false)
                      } catch (error) {
                        toast.error(t("files.createFolderError", { defaultValue: "创建文件夹失败" }))
                      }
                    }}
                  />
                </div>
              </>
            ) : (
              <div className="p-4 text-center text-xs text-muted-foreground italic">
                {t("chat.sidebar.noProject", { defaultValue: "未选择项目" })}
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Agent Changes Section - Sticky to bottom */}
      {activeThreadId && (
        <Collapsible
          open={isChangesOpen}
          onOpenChange={setIsChangesOpen}
          className={cn(
            "flex flex-col min-h-0 border-t border-border transition-all duration-200 bg-background/50",
            isChangesOpen ? "h-[40%] shrink-0" : "flex-none"
          )}
        >
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b border-border bg-muted/20">
              {isChangesOpen ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
              <History className="h-3.5 w-3.5 text-amber-500/70" />
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
                {t("chat.sidebar.agentChanges", { defaultValue: "Agent 改动记录" })}
              </span>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex-1 overflow-y-auto bg-background/30">
            <ChangesetTreeSection
              activeThreadId={activeThreadId}
              onSelectFile={onSelectDiff || (() => { })}
              defaultExpanded={expandChanges}
            />
          </CollapsibleContent>
        </Collapsible>
      )}

      <DiscoverDialog
        projectId={projectId || 0}
        open={discoverOpen}
        onOpenChange={setDiscoverOpen}
        onDiscovered={() => fetchProjects()}
      />

      <FilePreviewModal
        projectId={projectId || 0}
        file={previewFile?.name !== "PROJECT.md" ? previewFile : null}
        open={!!previewFile && previewFile.name !== "PROJECT.md"}
        onOpenChange={(open) => !open && setPreviewFile(null)}
      />
      
      <ProjectProfileDrawer
        projectId={projectId || 0}
        open={!!previewFile && previewFile.name === "PROJECT.md"}
        onOpenChange={(open) => !open && setPreviewFile(null)}
      />
    </div>
  )
}
