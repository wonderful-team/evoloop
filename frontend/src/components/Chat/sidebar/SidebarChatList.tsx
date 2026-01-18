import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Check,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ConversationsService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export interface Thread {
  thread_id: string
  title: string
  updated_at: string
  status?: string
}

interface SidebarChatListProps {
  threads: Thread[]
  activeThreadId: string
  setActiveThreadId: (id: string) => void
  onDeleteThread: (id: string) => void
  onStopThread: (id: string) => void
  onNewChat: () => void
}

export function SidebarChatList({
  threads,
  activeThreadId,
  setActiveThreadId,
  onDeleteThread,
  onStopThread,
  onNewChat,
}: SidebarChatListProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Search state
  const [searchQuery, setSearchQuery] = useState("")

  // Rename state
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState("")

  // Rename mutation
  const renameMutation = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      ConversationsService.renameConversation({
        threadId,
        requestBody: { title },
      }),
    onSuccess: () => {
      setEditingThreadId(null)
      queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
    },
  })

  // Filtered threads
  const filteredThreads = threads.filter(
    (thread) =>
      !searchQuery ||
      thread.title?.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  return (
    <div className="flex flex-col h-full bg-background border-r">
      {/* Search Input */}
      <div className="p-3 sticky top-0 bg-background/95 backdrop-blur z-10 border-b">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder={t(
              "chat.sidebar.searchPlaceholder",
              "Search conversations...",
            )}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-9 text-sm bg-muted/50 border-muted-foreground/20 focus:bg-background transition-colors shadow-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5 rounded-full hover:bg-muted"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredThreads.map((thread: Thread) => (
          // biome-ignore lint/a11y/useSemanticElements: Cannot use button due to nested interactive elements
          <div
            key={thread.thread_id}
            role="button"
            tabIndex={0}
            className={`group flex items-center justify-between text-sm p-2 rounded-md cursor-pointer hover:bg-muted ${activeThreadId === thread.thread_id ? "bg-muted font-medium" : ""}`}
            onClick={() => setActiveThreadId(thread.thread_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                setActiveThreadId(thread.thread_id)
              }
            }}
          >
            <div className="flex items-center gap-2 truncate flex-1">
              {/* Icon: Show Loading/Stop if running */}
              {thread.status === "running" ? (
                <div className="shrink-0 relative flex h-3.5 w-3.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-primary" />
                </div>
              ) : (
                <MessageSquare
                  size={14}
                  className="shrink-0 text-muted-foreground"
                />
              )}

              {/* Inline Rename Mode */}
              {editingThreadId === thread.thread_id ? (
                // biome-ignore lint/a11y/noStaticElementInteractions: Stop propagation wrapper
                <div
                  className="flex items-center gap-1 flex-1"
                  role="presentation"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                >
                  <Input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    className="h-6 text-xs flex-1"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        renameMutation.mutate({
                          threadId: thread.thread_id,
                          title: editingTitle,
                        })
                      } else if (e.key === "Escape") {
                        setEditingThreadId(null)
                      }
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() =>
                      renameMutation.mutate({
                        threadId: thread.thread_id,
                        title: editingTitle,
                      })
                    }
                  >
                    <Check size={12} className="text-green-500" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => setEditingThreadId(null)}
                  >
                    <X size={12} className="text-muted-foreground" />
                  </Button>
                </div>
              ) : (
                <span className="truncate">
                  {thread.title || t("chat.sidebar.untitled")}
                </span>
              )}
            </div>

            <div className="flex items-center shrink-0">
              {/* Rename Button */}
              {editingThreadId !== thread.thread_id &&
                thread.status !== "running" && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditingThreadId(thread.thread_id)
                      setEditingTitle(thread.title || "")
                    }}
                  >
                    <Pencil size={12} className="text-muted-foreground" />
                  </Button>
                )}

              {/* Stop Button if running */}
              {thread.status === "running" && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-destructive hover:bg-destructive/10"
                  onClick={(e) => {
                    e.stopPropagation()
                    onStopThread(thread.thread_id)
                  }}
                  title={t("chat.interface.stop", "Stop Generation")}
                >
                  <div className="h-2 w-2 bg-current rounded-[1px]" />
                </Button>
              )}

              <Button
                variant="ghost"
                size="icon"
                className={`h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity ${thread.status === "running" ? "hidden" : ""}`}
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirm(t("chat.sidebar.deleteConfirm")))
                    onDeleteThread(thread.thread_id)
                }}
              >
                <Trash2
                  size={12}
                  className="text-muted-foreground hover:text-destructive"
                />
              </Button>
            </div>
          </div>
        ))}
        {threads.length === 0 && (
          <div className="p-4 text-xs text-muted-foreground text-center">
            {t("chat.sidebar.noHistory")}
          </div>
        )}
      </div>

      {/* Bottom Action */}
      <div className="p-4 border-t mt-auto shrink-0">
        <Button
          onClick={onNewChat}
          className="w-full justify-start gap-2"
          variant="outline"
        >
          <Plus size={16} /> {t("chat.sidebar.newChat")}
        </Button>
      </div>
    </div>
  )
}
