
import { ArrowLeft, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"
import { MobileProjectSwitcher } from "../../components/MobileProjectSwitcher"
import { useMobileStore } from "../../stores/useMobileStore"

interface ChatHeaderProps {
    device: any
    statusText: string
    statusColor: string
    statusShadow: string
    deviceId: string
    onClear: () => void
}

export function ChatHeader({
    device,
    statusText,
    statusColor,
    statusShadow,
    deviceId,
    onClear
}: ChatHeaderProps) {
    const navigate = useNavigate()
    const { setCurrentProject, currentProject, setProjectInitialized } = useMobileStore()

    return (
        <div className="bg-background/80 backdrop-blur-md border-b px-4 py-3 flex items-center gap-3 sticky top-0 z-10 shrink-0">
            <Button variant="ghost" size="icon" className="-ml-2 hover:bg-muted" onClick={() => window.history.back()}>
                <ArrowLeft className="w-5 h-5" />
            </Button>
            <div className="flex-1 overflow-hidden">
                <div className="flex items-center gap-1.5 mb-0.5">
                    <h1 className="font-semibold text-sm truncate max-w-[120px]">
                        {device?.device_name || `Device #${deviceId}`}
                    </h1>
                    <span className="text-muted-foreground/30">|</span>
                    <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${statusColor} ${statusShadow} transition-colors duration-300`} />
                        <span className="text-xs text-muted-foreground transition-all duration-300 truncate">{statusText}</span>
                    </div>
                </div>
                <div className="-ml-1">
                    <MobileProjectSwitcher
                        project={currentProject}
                        onProjectChange={setCurrentProject}
                        onLoaded={(val) => {
                            setCurrentProject(val)
                            setProjectInitialized(true)
                        }}
                    />
                </div>
            </div>
            <Button variant="ghost" size="sm" className="text-muted-foreground text-xs h-8" onClick={onClear}>
                Clear
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => navigate({ to: '/search', search: { deviceId, projectId: currentProject?.project_id } } as any)}>
                <Search className="w-5 h-5" />
            </Button>
        </div>
    )
}
