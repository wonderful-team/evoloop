import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { SidebarChatList, type Thread } from "./sidebar/SidebarChatList"
export type { Thread }

import { useProjectStore } from "@/stores/projectStore"
import { useChangesetStore } from "@/stores/changesetStore"
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
  onQuoteFile?: (file: any) => void
  activeTab?: string
  onTabChange?: (tab: string) => void
  expandAgentChanges?: boolean
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onTogglePin?: (id: string, isPinned: boolean) => void
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
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    onTogglePin,
  }: ChatSidebarProps) => {
    const { t } = useTranslation()

    // Get changeset state for badge
    const changeset = useChangesetStore((s) => s.changeset)
    const viewedChanges = useChangesetStore((s) => s.viewedChanges)
    const unviewedCount = changeset.filter(
      (f) => !viewedChanges.has(f.path),
    ).length

    return (
      <div
        className="flex flex-col h-full w-full min-w-0 bg-muted/5 overflow-hidden"
        data-tour="chat-sidebar"
      >
        <div className="p-2 border-b border-border bg-background shrink-0 w-full min-w-0 overflow-hidden">
          <ProjectSwitcher
            open={useProjectStore((s) => s.projectSwitcherOpen || undefined)}
            onOpenChange={(v) => {
              if (!v) useProjectStore.getState().closeProjectSwitcher()
            }}
          />
        </div>

        <Tabs
          value={activeTab || "chats"}
          onValueChange={onTabChange}
          className="flex flex-col flex-1 min-h-0 min-w-0 w-full overflow-hidden"
        >
          <div className="p-2 border-b border-border bg-muted/10 shrink-0 w-full">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="chats">
                {t("chat.sidebar.tabChats")}
              </TabsTrigger>
              <TabsTrigger value="files" className="relative">
                {t("chat.sidebar.tabFiles")}
                {unviewedCount > 0 && (
                  <span
                    className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center 
                                   rounded-full bg-red-500 px-1 text-[10px] font-medium text-white 
                                   animate-in zoom-in duration-200"
                  >
                    {unviewedCount > 99 ? "99+" : unviewedCount}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value="chats"
            className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0"
          >
            {activeTab === "chats" && (
              <SidebarChatList
                threads={threads}
                activeThreadId={activeThreadId}
                setActiveThreadId={setActiveThreadId}
                onDeleteThread={onDeleteThread}
                onStopThread={onStopThread}
                onNewChat={onNewChat}
                fetchNextPage={fetchNextPage}
                hasNextPage={hasNextPage}
                isFetchingNextPage={isFetchingNextPage}
                onTogglePin={onTogglePin}
              />
            )}
          </TabsContent>

          <TabsContent
            value="files"
            className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0"
          >
            {activeTab === "files" && (
              <SidebarFilesTab
                projectId={projectId}
                activeThreadId={activeThreadId}
                onSelectDiff={onSelectDiff}
                onQuoteFile={onQuoteFile}
                expandChanges={expandAgentChanges}
              />
            )}
          </TabsContent>
        </Tabs>
      </div>
    )
  },
)

ChatSidebar.displayName = "ChatSidebar"
