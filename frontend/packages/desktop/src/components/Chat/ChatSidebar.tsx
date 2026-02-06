import { memo } from "react"
import { useTranslation } from "react-i18next"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { SidebarChatList, type Thread } from "./sidebar/SidebarChatList"
export type { Thread }

import { SidebarFilesTab } from "./sidebar/SidebarFilesTab"

interface ChatSidebarProps {
  threads: Thread[]
  activeThreadId: string
  setActiveThreadId: (id: string) => void
  projectId: number | undefined
  onDeleteThread: (id: string) => void
  onStopThread: (id: string) => void
  onNewChat: () => void
  onSelectDiff?: (path: string, diff: string) => void
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
  }: ChatSidebarProps) => {
    const { t } = useTranslation()

    return (
      <div
        className="flex flex-col h-full border-r bg-muted/5"
        data-tour="chat-sidebar"
      >
        <div className="p-2 border-b bg-background shrink-0">
          <ProjectSwitcher />
        </div>

        <Tabs defaultValue="chats" className="flex flex-col flex-1 min-h-0">
          <div className="p-2 border-b bg-muted/10 shrink-0">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="chats">
                {t("chat.sidebar.tabChats")}
              </TabsTrigger>
              <TabsTrigger value="files">
                {t("chat.sidebar.tabFiles")}
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
            />
          </TabsContent>
        </Tabs>
      </div>
    )
  },
)

ChatSidebar.displayName = "ChatSidebar"
