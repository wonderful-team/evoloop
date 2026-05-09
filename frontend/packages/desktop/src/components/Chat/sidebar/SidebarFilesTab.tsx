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
import { ChevronDown, ChevronRight, Files, History, Globe, Wand2, Rocket, BookOpen } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"
import { isGlobalProject } from "@/stores/projectStore"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@evoloop/shared/components/ui/tooltip"
import { ProjectProfilesService, WikiService } from "@/client"

interface SidebarFilesTabProps {
  projectId?: number
  activeThreadId?: string
  onSelectDiff?: (path: string, diff: string) => void
  onQuoteFile?: (file: any) => void
  expandChanges?: boolean // Whether to expand Agent Changes panel by default
}

export function SidebarFilesTab({ projectId, activeThreadId, onSelectDiff, onQuoteFile, expandChanges = false }: SidebarFilesTabProps) {
  const { t } = useTranslation()
  const [isProjectOpen, setIsProjectOpen] = useState(true)
  const [isChangesOpen, setIsChangesOpen] = useState(expandChanges)

  // Check for global mode (projectId is 0)
  const isGlobal = isGlobalProject(projectId ? { id: projectId } as any : null)

  const handleDeploy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isGlobal || !projectId) return

    try {
      await ProjectProfilesService.discoverProfile({
        projectId,
        requestBody: { record_secrets: false }
      })
      toast.success(t("chat.sidebar.deployStarted"))
    } catch (error) {
      console.error("Failed to start deployment task:", error)
      toast.error("Failed to start deployment task")
    }
  }

  const handleGenerateWiki = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isGlobal || !projectId) return

    try {
      await WikiService.generateWiki({
        requestBody: { project_id: projectId, topic: "Comprehensive Project Documentation" }
      })
      toast.success(t("chat.sidebar.wikiStarted"))
    } catch (error) {
      console.error("Failed to start wiki generation task:", error)
      toast.error("Failed to start wiki generation task")
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
          <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b bg-muted/20">
            {isProjectOpen ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            {isGlobal ? (
              <Globe className="h-3.5 w-3.5 text-blue-500" />
            ) : (
              <Files className="h-3.5 w-3.5 text-primary/70" />
            )}
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
              {isGlobal
                ? t("chat.sidebar.workspaceFiles")
                : t("chat.sidebar.projectFiles")}
            </span>

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
                    {t("chat.sidebar.projectOnly")}
                  </TooltipContent>
                )}
              </Tooltip>
              
              <DropdownMenuContent align="end" className="w-56" onClick={(e) => e.stopPropagation()}>
                <DropdownMenuLabel className="text-[11px] font-bold uppercase tracking-tight text-muted-foreground/80">
                  {t("chat.sidebar.actions")}
                  {isGlobal && <span className="ml-2 text-[10px] font-normal lowercase opacity-60">({t("chat.sidebar.projectOnly")})</span>}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                
                <DropdownMenuItem 
                  disabled={isGlobal}
                  onClick={handleDeploy}
                  className="gap-2 text-xs py-2 cursor-pointer"
                >
                  <Rocket className="h-3.5 w-3.5 text-blue-500" />
                  <span>{t("chat.sidebar.deploy")}</span>
                </DropdownMenuItem>
                
                <DropdownMenuItem 
                  disabled={isGlobal}
                  onClick={handleGenerateWiki}
                  className="gap-2 text-xs py-2 cursor-pointer"
                >
                  <BookOpen className="h-3.5 w-3.5 text-green-500" />
                  <span>{t("chat.sidebar.wiki")}</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent className="flex-1 overflow-y-auto">
          <div className="p-2">
            {projectId !== undefined ? (
              <FileTree
                projectId={projectId}
                onSelectFile={(file) => {
                  navigator.clipboard.writeText(file.path)
                  toast.success(t("chat.sidebar.copiedPath", { path: file.path }))
                }}
                onQuoteFile={onQuoteFile}
              />
            ) : (
              <div className="p-4 text-center text-xs text-muted-foreground italic">
                {t("chat.sidebar.noProject")}
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
            "flex flex-col min-h-0 border-t transition-all duration-200 bg-background/50",
            isChangesOpen ? "h-[40%] shrink-0" : "flex-none"
          )}
        >
          <CollapsibleTrigger asChild>
            <div className="flex items-center gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors border-b bg-muted/20">
              {isChangesOpen ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
              <History className="h-3.5 w-3.5 text-amber-500/70" />
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
                {t("chat.sidebar.agentChanges")}
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
    </div>
  )
}
