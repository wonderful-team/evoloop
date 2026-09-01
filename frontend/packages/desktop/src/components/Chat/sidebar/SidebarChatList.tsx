import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import i18n from "@evoloop/shared/i18n"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Check,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ConversationsService } from "@/client"
import { useUnreadCompletionsStore } from "@/stores/unreadCompletionsStore"

export interface Thread {
  thread_id: string
  title: string
  updated_at: string
  status?: string
  is_pinned?: boolean
  goal?: string | null
}

interface SidebarChatListProps {
  threads: Thread[]
  activeThreadId: string
  setActiveThreadId: (id: string) => void
  onDeleteThread: (id: string) => void
  onStopThread: (id: string) => void
  onNewChat: () => void
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onTogglePin?: (id: string, isPinned: boolean) => void
}

function formatRelativeTime(dateString: string) {
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) {
      return i18n.t("common.time.justNow")
    }
    if (diffMins < 60) {
      return i18n.t("common.time.minutesAgo", { count: diffMins })
    }
    if (diffHours < 24) {
      return i18n.t("common.time.hoursAgo", { count: diffHours })
    }
    if (diffDays < 7) {
      return i18n.t("common.time.daysAgo", { count: diffDays })
    }

    const mm = String(date.getMonth() + 1).padStart(2, "0")
    const dd = String(date.getDate()).padStart(2, "0")
    const hh = String(date.getHours()).padStart(2, "0")
    const min = String(date.getMinutes()).padStart(2, "0")
    return `${mm}-${dd} ${hh}:${min}`
  } catch (_e) {
    return ""
  }
}
interface GroupedThreads {
  pinned: Thread[]
  today: Thread[]
  yesterday: Thread[]
  recent: Thread[]
  earlier: Thread[]
}

function groupThreads(threads: Thread[]): GroupedThreads {
  const groups: GroupedThreads = {
    pinned: [],
    today: [],
    yesterday: [],
    recent: [],
    earlier: [],
  }

  const now = new Date()
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime()
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000
  const startOf7DaysAgo = startOfToday - 6 * 24 * 60 * 60 * 1000

  for (const thread of threads) {
    if (thread.is_pinned) {
      groups.pinned.push(thread)
      continue
    }

    const updatedTime = new Date(thread.updated_at).getTime()
    if (updatedTime >= startOfToday) {
      groups.today.push(thread)
    } else if (updatedTime >= startOfYesterday) {
      groups.yesterday.push(thread)
    } else if (updatedTime >= startOf7DaysAgo) {
      groups.recent.push(thread)
    } else {
      groups.earlier.push(thread)
    }
  }

  return groups
}

export function SidebarChatList({
  threads,
  activeThreadId,
  setActiveThreadId,
  onDeleteThread,
  onStopThread,
  onNewChat,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  onTogglePin,
}: SidebarChatListProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const unreadCompletions = useUnreadCompletionsStore((s) => s.unread)

  // Search state
  const [searchQuery, setSearchQuery] = useState("")

  // Rename state
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState("")

  // Intersection Observer for infinite loading
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!hasNextPage || isFetchingNextPage || !fetchNextPage) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          fetchNextPage()
        }
      },
      { threshold: 0.1 },
    )

    const currentSentinel = sentinelRef.current
    if (currentSentinel) {
      observer.observe(currentSentinel)
    }

    return () => {
      if (currentSentinel) {
        observer.unobserve(currentSentinel)
      }
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Rename mutation
  const renameMutation = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      ConversationsService.updateConversation({
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

  // Memoize groupThreads: only re-runs when filteredThreads changes,
  // not on every re-render caused by editingThreadId or other local state changes.
  const groupedThreads = useMemo(
    () => groupThreads(filteredThreads),
    [filteredThreads],
  )

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Search Input */}
      <div className="pl-3 pr-3 pb-2 sticky top-0 bg-background/95 backdrop-blur z-10 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder={t("chat.sidebar.searchPlaceholder")}
            value={searchQuery}
            onChange={(e: any) => setSearchQuery(e.target.value)}
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
      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {(() => {
          const grouped = groupedThreads
          const sections = [
            {
              key: "pinned",
              label: t("chat.sidebar.sections.pinned"),
              items: grouped.pinned,
            },
            {
              key: "today",
              label: t("chat.sidebar.sections.today"),
              items: grouped.today,
            },
            {
              key: "yesterday",
              label: t("chat.sidebar.sections.yesterday"),
              items: grouped.yesterday,
            },
            {
              key: "recent",
              label: t("chat.sidebar.sections.recent"),
              items: grouped.recent,
            },
            {
              key: "earlier",
              label: t("chat.sidebar.sections.earlier"),
              items: grouped.earlier,
            },
          ]

          const renderThreadItem = (thread: Thread) => (
            <div
              key={thread.thread_id}
              role="button"
              tabIndex={0}
              className={`group flex items-center justify-between text-sm p-2 rounded-md cursor-pointer hover:bg-muted relative ${activeThreadId === thread.thread_id ? "bg-muted font-medium" : ""}`}
              onClick={() => setActiveThreadId(thread.thread_id)}
              onKeyDown={(e: any) => {
                if (e.key === "Enter" || e.key === " ") {
                  setActiveThreadId(thread.thread_id)
                }
              }}
            >
              {/* Main Content Area (no left icon) */}
              <div className="flex items-start min-w-0 flex-1 pt-0.5">
                {/* Inline Rename Mode */}
                {editingThreadId === thread.thread_id ? (
                  // biome-ignore lint/a11y/noStaticElementInteractions: Stop propagation wrapper
                  <div
                    className="flex items-center gap-1 flex-1"
                    role="presentation"
                    onClick={(e: any) => e.stopPropagation()}
                    onKeyDown={(e: any) => e.stopPropagation()}
                  >
                    <Input
                      type="text"
                      value={editingTitle}
                      onChange={(e: any) => setEditingTitle(e.target.value)}
                      className="h-6 text-xs flex-1"
                      autoFocus
                      onKeyDown={(e: any) => {
                        if (e.nativeEvent.isComposing) return
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
                  <div className="flex flex-col min-w-0 flex-1 pr-8">
                    <span
                      className="truncate flex items-center gap-1.5 font-medium text-foreground"
                      title={thread.title || t("chat.sidebar.untitled")}
                    >
                      {thread.is_pinned && (
                        <Pin
                          size={10}
                          className="shrink-0 text-amber-500 fill-amber-500/25"
                        />
                      )}
                      <span className="truncate">
                        {thread.title || t("chat.sidebar.untitled")}
                      </span>
                      {unreadCompletions[thread.thread_id] && (
                        <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0 ml-0.5" />
                      )}
                    </span>
                    {thread.goal && (
                      <span
                        className="text-[11px] text-muted-foreground/80 truncate mt-0.5 block"
                        title={thread.goal}
                      >
                        {thread.goal}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Absolute positioned Relative Time label in bottom right corner */}
              {thread.status !== "running" && (
                <span className="text-[9px] text-muted-foreground absolute right-2 bottom-1.5 whitespace-nowrap group-hover:opacity-0 transition-opacity duration-150 pointer-events-none z-10">
                  {formatRelativeTime(thread.updated_at)}
                </span>
              )}

              {/* Actions Area (Vertically Centered on Right Side) */}
              {editingThreadId !== thread.thread_id && (
                <div className="flex items-center shrink-0 ml-2 relative min-h-[24px] z-20">
                  {/* Actions container: visible on hover */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-background/95 rounded pl-1 absolute right-0 top-1/2 -translate-y-1/2">
                    {/* Pin/Unpin Button */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={(e: any) => {
                        e.stopPropagation()
                        onTogglePin?.(thread.thread_id, !thread.is_pinned)
                      }}
                      title={
                        thread.is_pinned
                          ? t("chat.sidebar.unpinThread")
                          : t("chat.sidebar.pinThread")
                      }
                    >
                      {thread.is_pinned ? (
                        <PinOff
                          size={12}
                          className="text-amber-500 fill-amber-500/25"
                        />
                      ) : (
                        <Pin
                          size={12}
                          className="text-muted-foreground hover:text-foreground"
                        />
                      )}
                    </Button>

                    {/* Rename Button (not for running) */}
                    {thread.status !== "running" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={(e: any) => {
                          e.stopPropagation()
                          setEditingThreadId(thread.thread_id)
                          setEditingTitle(thread.title || "")
                        }}
                        title={t("common.rename")}
                      >
                        <Pencil
                          size={12}
                          className="text-muted-foreground hover:text-foreground"
                        />
                      </Button>
                    )}

                    {/* Stop Button (only for running, inside hover container) */}
                    {thread.status === "running" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-destructive hover:bg-destructive/10"
                        onClick={(e: any) => {
                          e.stopPropagation()
                          onStopThread(thread.thread_id)
                        }}
                        title={t("chat.interface.stop")}
                      >
                        <div className="h-2 w-2 bg-current rounded-[1px]" />
                      </Button>
                    )}

                    {/* Delete Button (not for running) */}
                    {thread.status !== "running" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={(e: any) => {
                          e.stopPropagation()
                          onDeleteThread(thread.thread_id)
                        }}
                        title={t("common.delete")}
                      >
                        <Trash2
                          size={12}
                          className="text-muted-foreground hover:text-destructive"
                        />
                      </Button>
                    )}
                  </div>

                  {/* Standalone Stop Button: permanently visible on the right when running and not hovered */}
                  {thread.status === "running" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-destructive hover:bg-destructive/10 shrink-0 z-10 animate-pulse group-hover:opacity-0 group-hover:pointer-events-none transition-opacity duration-150 absolute right-0 top-1/2 -translate-y-1/2"
                      onClick={(e: any) => {
                        e.stopPropagation()
                        onStopThread(thread.thread_id)
                      }}
                      title={t("chat.interface.stop")}
                    >
                      <div className="h-2 w-2 bg-current rounded-[1px]" />
                    </Button>
                  )}
                </div>
              )}
            </div>
          )

          return (
            <>
              {sections.map(
                (section) =>
                  section.items.length > 0 && (
                    <div key={section.key} className="space-y-1">
                      <div className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider px-2 py-1 select-none">
                        {section.label}
                      </div>
                      <div className="space-y-1">
                        {section.items.map(renderThreadItem)}
                      </div>
                    </div>
                  ),
              )}
            </>
          )
        })()}

        {/* Infinite loading sentinel */}
        {hasNextPage && (
          <div
            ref={sentinelRef}
            className="py-2 text-center text-xs text-muted-foreground"
          >
            {isFetchingNextPage
              ? t("common.loading")
              : t("chat.sidebar.loadMore")}
          </div>
        )}
        {threads.length === 0 && (
          <div className="p-4 text-xs text-muted-foreground text-center">
            {t("chat.sidebar.noHistory")}
          </div>
        )}
      </div>

      {/* Bottom Action */}
      <div className="p-4 border-t border-border mt-auto shrink-0">
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
