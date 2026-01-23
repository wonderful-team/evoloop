import { History, Plus } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { LogsService } from "@/mobile/client"
import { Button } from "@/components/ui/button"
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from "@/components/ui/sheet"

interface LocalSessionDrawerProps {
    deviceId: number
    projectId?: number
    activeThreadId?: string
    trigger?: React.ReactNode
    onSelect: (threadId: string) => void
}

export function LocalSessionDrawer({
    deviceId,
    projectId,
    activeThreadId,
    trigger,
    onSelect,
}: LocalSessionDrawerProps) {
    const { t } = useTranslation()
    const [sessions, setSessions] = useState<any[]>([])
    const [isOpen, setIsOpen] = useState(false)

    const fetchSessions = async () => {
        try {
            const res = await LogsService.getRecentThreads({
                device_id: deviceId,
                project_id: projectId,
            })
            if (res.code >= 0 && Array.isArray(res.data)) {
                setSessions(res.data)
            }
        } catch (e) {
            console.error("Failed to fetch sessions", e)
        }
    }

    useEffect(() => {
        if (isOpen) {
            fetchSessions()
        }
    }, [isOpen])

    const handleSelect = (threadId: string) => {
        onSelect(threadId)
        setIsOpen(false)
    }

    const handleNewSession = () => {
        // Navigate to local chat with no threadId (it will use current system state or ask device for new)
        // Actually in local chat, 'new' might just mean clearing messages and starting fresh.
        onSelect("") // Empty threadId means new session
        setIsOpen(false)
    }

    return (
        <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger asChild>
                {trigger || (
                    <Button variant="ghost" size="icon">
                        <History className="w-5 h-5" />
                    </Button>
                )}
            </SheetTrigger>
            <SheetContent side="left" className="w-[80vw] sm:w-[350px] p-0 rounded-r-xl">
                <SheetHeader className="p-4 border-b">
                    <SheetTitle className="text-left flex items-center justify-between">
                        {t("chat.local.sessions") || "Local Sessions"}
                        <Button variant="ghost" size="sm" onClick={handleNewSession}>
                            <Plus className="w-4 h-4 mr-1" /> {t("conversation.new")}
                        </Button>
                    </SheetTitle>
                </SheetHeader>
                <div className="overflow-y-auto h-full pb-20">
                    {sessions.map((s) => (
                        <div
                            key={s.thread_id}
                            className={`p-3 border-b cursor-pointer hover:bg-muted/50 flex flex-col ${activeThreadId === s.thread_id ? "bg-muted border-l-4 border-l-primary" : ""}`}
                            onClick={() => handleSelect(s.thread_id)}
                        >
                            <div className="font-medium text-sm truncate mb-1">
                                {s.title || t("conversation.untitled")}
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] text-muted-foreground truncate max-w-[180px]">
                                    {s.thread_id}
                                </span>
                                <span className="text-[10px] text-muted-foreground">
                                    {new Date(s.update_time * 1000).toLocaleString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            </div>
                        </div>
                    ))}
                    {sessions.length === 0 && (
                        <div className="p-8 text-center text-muted-foreground text-sm">
                            {t("conversation.empty")}
                        </div>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    )
}
