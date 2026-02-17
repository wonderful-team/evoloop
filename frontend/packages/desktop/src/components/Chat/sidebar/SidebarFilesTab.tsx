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
import { ChevronDown, ChevronRight, Files, History } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"

interface SidebarFilesTabProps {
  projectId?: number
  activeThreadId?: string
  onSelectDiff?: (path: string, diff: string) => void
  onQuoteFile?: (file: any) => void
}

export function SidebarFilesTab({ projectId, activeThreadId, onSelectDiff, onQuoteFile }: SidebarFilesTabProps) {
  const { t } = useTranslation()
  const [isProjectOpen, setIsProjectOpen] = useState(true)
  const [isChangesOpen, setIsChangesOpen] = useState(false)

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
            <Files className="h-3.5 w-3.5 text-primary/70" />
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex-1">
              {t("chat.sidebar.projectFiles", "Project Files")}
            </span>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent className="flex-1 overflow-y-auto">
          <div className="p-2">
            {projectId ? (
              <FileTree
                projectId={projectId}
                onSelectFile={(file) => {
                  navigator.clipboard.writeText(file.path)
                  toast.success(`Copied path: ${file.path}`)
                }}
                onQuoteFile={onQuoteFile}
              />
            ) : (
              <div className="p-4 text-center text-xs text-muted-foreground italic">
                {t("chat.sidebar.noProject", "No project selected")}
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
                {t("chat.sidebar.agentChanges", "Agent Changes")}
              </span>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex-1 overflow-y-auto bg-background/30">
            <ChangesetTreeSection
              activeThreadId={activeThreadId}
              onSelectFile={onSelectDiff || (() => { })}
            />
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
