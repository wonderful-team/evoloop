import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { FileTree } from "@/components/Files/FileTree"
import { MessageSquare, Plus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"

export interface Thread {
    thread_id: string
    title: string
    updated_at: string
}

interface ChatSidebarProps {
    threads: Thread[]
    activeThreadId: string
    setActiveThreadId: (id: string) => void
    projectId: number | undefined
    onDeleteThread: (id: string) => void
    onNewChat: () => void
}

export function ChatSidebar({
    threads,
    activeThreadId,
    setActiveThreadId,
    projectId,
    onDeleteThread,
    onNewChat
}: ChatSidebarProps) {
    const { t } = useTranslation()
    return (
        <div className="flex flex-col h-full border-r bg-muted/5">
            <div className="p-2 border-b bg-background shrink-0">
                <ProjectSwitcher />
            </div>

            <Tabs defaultValue="chats" className="flex flex-col flex-1 min-h-0">
                <div className="p-2 border-b bg-muted/10 shrink-0">
                    <TabsList className="w-full grid grid-cols-2">
                        <TabsTrigger value="chats">{t('chat.sidebar.tabChats')}</TabsTrigger>
                        <TabsTrigger value="files">{t('chat.sidebar.tabFiles')}</TabsTrigger>
                    </TabsList>
                </div>

                <TabsContent value="chats" className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0">
                    {/* Chat List */}
                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {threads.map((thread: Thread) => (
                            <div
                                key={thread.thread_id}
                                className={`group flex items-center justify-between text-sm p-2 rounded-md cursor-pointer hover:bg-muted ${activeThreadId === thread.thread_id ? "bg-muted font-medium" : ""}`}
                                onClick={() => setActiveThreadId(thread.thread_id)}
                            >
                                <div className="flex items-center gap-2 truncate max-w-[160px]">
                                    <MessageSquare size={14} className="shrink-0 text-muted-foreground" />
                                    <span className="truncate">{thread.title || t('chat.sidebar.untitled')}</span>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        if (confirm(t('chat.sidebar.deleteConfirm'))) onDeleteThread(thread.thread_id)
                                    }}
                                >
                                    <Trash2 size={12} className="text-muted-foreground hover:text-destructive" />
                                </Button>
                            </div>
                        ))}
                        {threads.length === 0 && (
                            <div className="p-4 text-xs text-muted-foreground text-center">
                                {t('chat.sidebar.noHistory')}
                            </div>
                        )}
                    </div>

                    {/* Bottom Action */}
                    <div className="p-4 border-t mt-auto shrink-0">
                        <Button onClick={onNewChat} className="w-full justify-start gap-2" variant="outline">
                            <Plus size={16} /> {t('chat.sidebar.newChat')}
                        </Button>
                    </div>
                </TabsContent>

                <TabsContent value="files" className="flex-1 overflow-y-auto min-h-0 data-[state=inactive]:hidden mt-0">
                    <div className="p-2">
                        {projectId && <FileTree projectId={projectId} onSelectFile={(file) => console.log(file)} />}
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    )
}
