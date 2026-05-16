import { memo } from "react"
import { useTranslation } from "react-i18next"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { SidebarChatList, type Thread } from "./sidebar/SidebarChatList"
export type { Thread }

import { SidebarFilesTab } from "./sidebar/SidebarFilesTab"
import { useChatStore } from "@/stores/chatStore"

interface ChatSidebarProps {
  threads: Thread[]
  activeThreadId: string
  setActiveThreadId: (id: string) => void
  projectId: number | undefined
  onDeleteThread: (id: string) => void
  onStopThread: (id: string) => void
  onNewChat: () => void
  onSelectDiff?: (path: string, diff: string) => void
  onQuoteFile?: (file: any) => void
  activeTab?: string
  onTabChange?: (tab: string) => void
  expandAgentChanges?: boolean
}

export const ChatSidebar = memo(
  ({
    threads,
    activeThreadId,
    setActiveThreadId,
    projectId,
    onDeleteThread,
    onStopThread,
    onNewChat,
    onSelectDiff,
    onQuoteFile,
    activeTab,
    onTabChange,
    expandAgentChanges = false,
  }: ChatSidebarProps) => {
    const { t } = useTranslation()
    
    // Get changeset state for badge
    const changeset = useChatStore((s) => s.changeset)
    const viewedChanges = useChatStore((s) => s.viewedChanges)
    const unviewedCount = changeset.filter(f => !viewedChanges.has(f.path)).length

    return (
      <div
        className="flex flex-col h-full w-full min-w-0 bg-muted/5 overflow-hidden"
        data-tour="chat-sidebar"
      >
        <div className="p-2 border-b bg-background shrink-0 w-full min-w-0 overflow-hidden">
          <ProjectSwitcher />
        </div>

        <Tabs 
          value={activeTab || "chats"} 
          onValueChange={onTabChange}
          className="flex flex-col flex-1 min-h-0 min-w-0 w-full overflow-hidden"
        >
          <div className="p-2 border-b bg-muted/10 shrink-0 w-full">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="chats">
                {t("chat.sidebar.tabChats")}
              </TabsTrigger>
              <TabsTrigger value="files" className="relative">
                {t("chat.sidebar.tabFiles")}
                {unviewedCount > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center 
                                   rounded-full bg-red-500 px-1 text-[10px] font-medium text-white 
                                   animate-in zoom-in duration-200">
                    {unviewedCount > 99 ? '99+' : unviewedCount}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value="chats"
            className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0"
          >
            <SidebarChatList
              threads={threads}
              activeThreadId={activeThreadId}
              setActiveThreadId={setActiveThreadId}
              onDeleteThread={onDeleteThread}
              onStopThread={onStopThread}
              onNewChat={onNewChat}
            />
          </TabsContent>

          <TabsContent
            value="files"
            className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0"
          >
            <SidebarFilesTab
              projectId={projectId}
              activeThreadId={activeThreadId}
              onSelectDiff={onSelectDiff}
              onQuoteFile={onQuoteFile}
              expandChanges={expandAgentChanges}
            />
          </TabsContent>
        </Tabs>
      </div>
    )
  },
)

ChatSidebar.displayName = "ChatSidebar"
