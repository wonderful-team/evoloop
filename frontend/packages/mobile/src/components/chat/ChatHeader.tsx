import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, History, MoreVertical, Search, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { MobileProjectSwitcher } from "../../components/MobileProjectSwitcher"
import { useMobileStore } from "../../stores/useMobileStore"
import { LocalSessionDrawer } from "./LocalSessionDrawer"

interface ChatHeaderProps {
  device: any
  statusText: string
  statusColor: string
  statusShadow: string
  deviceId: string
  activeThreadId?: string
  onThreadSelect: (id: string) => void
  onClear: () => void
}

export function ChatHeader({
  device,
  statusText,
  statusColor,
  statusShadow,
  deviceId,
  activeThreadId,
  onThreadSelect,
  onClear,
}: ChatHeaderProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { setCurrentProject, currentProject, setProjectInitialized } =
    useMobileStore()

  return (
    <div className="bg-background/90 backdrop-blur-md border-b sticky top-0 z-20 shrink-0 pt-safe-top pt-4">
      <div className="px-4 h-[56px] flex items-center justify-between">
        {/* Left Area: Back - Fixed Width */}
        <div className="flex items-center w-[60px]">
          <Button
            variant="ghost"
            size="icon"
            className="-ml-2 hover:bg-muted rounded-full transition-colors"
            onClick={() => navigate({ to: "/devices" as any })}
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </div>

        {/* Middle Area: Title & Status - Absolutely Centered */}
        <div className="flex-1 flex flex-col items-center justify-center overflow-hidden">
          <MobileProjectSwitcher
            project={currentProject}
            onProjectChange={setCurrentProject}
            onLoaded={(val) => {
              setCurrentProject(val)
              setProjectInitialized(true)
            }}
          />
          <div className="flex items-center gap-1.5 mt-0.5 pointer-events-none select-none opacity-60">
            <span
              className={`w-1.5 h-1.5 rounded-full ${statusColor} ${statusShadow} transition-colors duration-300`}
            />
            <span className="text-[9px] font-medium text-muted-foreground transition-all duration-300 truncate max-w-[150px]">
              {device?.device_name || t("chat.header.deviceFallback", { id: deviceId })}
              <span className="mx-1 opacity-20">•</span>
              {statusText}
            </span>
          </div>
        </div>

        {/* Right Area: Actions - Fixed Width (Matches Left) */}
        <div className="flex items-center justify-end gap-1 w-[60px]">
          <LocalSessionDrawer
            deviceId={Number(deviceId)}
            projectId={currentProject?.project_id}
            activeThreadId={activeThreadId}
            onSelect={onThreadSelect}
            trigger={
              <Button variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground hover:bg-muted rounded-full transition-colors">
                <History className="w-4.5 h-4.5" />
              </Button>
            }
          />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground hover:bg-muted rounded-full transition-colors">
                <MoreVertical className="w-4.5 h-4.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40 rounded-xl mt-1">
              <DropdownMenuItem
                className="gap-2 py-2.5"
                onClick={() =>
                  navigate({
                    to: "/search",
                    search: { deviceId, projectId: currentProject?.project_id },
                  } as any)
                }
              >
                <Search className="w-4 h-4 text-muted-foreground" />
                <span>{t("chat.header.search", "Search")}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="gap-2 py-2.5 text-destructive focus:text-destructive focus:bg-destructive/10"
                onClick={onClear}
              >
                <Trash2 className="w-4 h-4" />
                <span>{t("chat.header.clear")}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
