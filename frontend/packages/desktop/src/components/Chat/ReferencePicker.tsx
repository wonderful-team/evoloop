import { Card } from "@evoloop/shared/components/ui/card"
import {
  ScrollArea,
  ScrollBar,
} from "@evoloop/shared/components/ui/scroll-area"
import { Tabs } from "@evoloop/shared/components/ui/tabs"
import { cn } from "@evoloop/shared/lib/utils"
import { File, Folder, Loader2, MessageSquare } from "lucide-react"
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { ConversationsService, FilesService } from "@/client/sdk.gen"

export interface ReferenceItem {
  type: "file" | "message" | "directory"
  id: string
  name: string
  detail?: string
}

interface ReferencePickerProps {
  projectId: number
  searchQuery: string
  onSelect: (item: ReferenceItem) => void
  onClose: () => void
  className?: string
}

export interface ReferencePickerHandle {
  moveUp: () => void
  moveDown: () => void
  selectCurrent: () => void
}

export const ReferencePicker = forwardRef<
  ReferencePickerHandle,
  ReferencePickerProps
>(({ projectId, searchQuery, onSelect, onClose, className }, ref) => {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<"files" | "messages">("files")
  const [items, setItems] = useState<ReferenceItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Reset highlight on item changes
  useEffect(() => {
    setHighlightedIndex(0)
  }, [items])

  // Debounced search trigger when searchQuery or activeTab changes
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchResults()
    }, 200)

    return () => clearTimeout(timer)
  }, [searchQuery, activeTab, projectId])

  const fetchResults = async () => {
    setIsLoading(true)
    setItems([])
    try {
      if (activeTab === "files") {
        if (!searchQuery.trim()) {
          // Default recommendations: list workspace root items
          const res = await FilesService.listFiles({
            projectId,
            path: "",
          })
          const mapped: ReferenceItem[] = res.map((f: any) => ({
            type: (f.is_dir ? "directory" : "file") as any,
            id: f.path,
            name: f.name,
            detail: f.path || t("chat.reference.projectRoot"),
          }))
          setItems(mapped.slice(0, 20))
        } else {
          const res = await FilesService.searchFilesByName({
            projectId,
            q: searchQuery,
          })
          const mapped: ReferenceItem[] = res.map((f: any) => ({
            type: (f.type === "directory" ? "directory" : "file") as any,
            id: f.path,
            name: f.name,
            detail: f.path,
          }))
          setItems(mapped)
        }
      } else {
        if (!searchQuery.trim()) {
          // If message search query is empty, show empty list or placeholder
          setItems([])
        } else {
          const res = await ConversationsService.searchConversations({
            projectId,
            q: searchQuery,
          })
          const mapped: ReferenceItem[] = res.map((c: any) => ({
            type: "message",
            id: String(c.id),
            name: c.content
              ? `${c.content.slice(0, 50)}...`
              : t("chat.reference.messageFallback"),
            detail: t("chat.reference.threadLabel", {
              id: `${c.thread_id.slice(0, 8)}...`,
            }),
          }))
          setItems(mapped)
        }
      }
    } catch (error) {
      console.error("Search failed", error)
    } finally {
      setIsLoading(false)
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const activeBtn = itemRefs.current[highlightedIndex]
    if (activeBtn) {
      activeBtn.scrollIntoView({ block: "nearest" })
    }
  }, [highlightedIndex])

  useImperativeHandle(ref, () => ({
    moveUp: () => {
      if (items.length === 0) return
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : items.length - 1))
    },
    moveDown: () => {
      if (items.length === 0) return
      setHighlightedIndex((prev) => (prev < items.length - 1 ? prev + 1 : 0))
    },
    selectCurrent: () => {
      if (items.length > 0 && items[highlightedIndex]) {
        onSelect(items[highlightedIndex])
      }
    },
  }))

  // Highlight matched substring helper
  const highlightText = (text: string, highlight: string) => {
    if (!highlight.trim()) return <span>{text}</span>
    try {
      const escapedHighlight = highlight.replace(
        /[-/\\^$*+?.()|[\]{}]/g,
        "\\$&",
      )
      const regex = new RegExp(`(${escapedHighlight})`, "gi")
      const parts = text.split(regex)
      return (
        <span>
          {parts.map((part, i) =>
            regex.test(part) ? (
              <span
                key={i}
                className="font-extrabold text-amber-300 underline underline-offset-2"
              >
                {part}
              </span>
            ) : (
              <span key={i}>{part}</span>
            ),
          )}
        </span>
      )
    } catch (_e) {
      return <span>{text}</span>
    }
  }

  return (
    <Card
      className={cn(
        "w-full flex flex-col overflow-hidden shadow-2xl border border-primary/20 bg-background/98 backdrop-blur-md rounded-xl transition-all duration-200 ease-out animate-in fade-in slide-in-from-bottom-2",
        className,
      )}
    >
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as any)}
        className="flex-1 flex flex-col"
      >
        {/* <TabsList className="w-full justify-start rounded-none border-b h-9 p-0 px-3 bg-muted/40">
          <TabsTrigger
            value="files"
            className="h-full px-4 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent text-xs font-semibold"
          >
            {t("chat.reference.files")}
          </TabsTrigger>
          <TabsTrigger
            value="messages"
            className="h-full px-4 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent text-xs font-semibold"
          >
            {t("chat.reference.messages")}
          </TabsTrigger>
        </TabsList> */}

        <div className="flex-1 overflow-hidden relative min-h-[160px] max-h-[300px]">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          )}

          <ScrollArea className="h-[240px] w-full">
            {items.length === 0 && !isLoading && (
              <div className="p-8 text-center text-xs text-muted-foreground">
                {searchQuery
                  ? t("chat.reference.noResults")
                  : t("chat.reference.typeToSearch")}
              </div>
            )}

            <div className="p-1.5 space-y-0.5">
              {items.map((item, idx) => {
                const isHighlighted = idx === highlightedIndex
                return (
                  <button
                    ref={(el) => {
                      itemRefs.current[idx] = el
                    }}
                    key={`${item.type}-${item.id}`}
                    onClick={() => onSelect(item)}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={cn(
                      "w-full text-left px-3 py-2 text-xs rounded-lg flex items-center gap-2.5 transition-all duration-150",
                      isHighlighted
                        ? "bg-primary text-primary-foreground font-medium shadow-md shadow-primary/10"
                        : "hover:bg-accent hover:text-accent-foreground text-foreground/80",
                    )}
                  >
                    {item.type === "file" ? (
                      <File
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          isHighlighted
                            ? "text-primary-foreground"
                            : "text-blue-500",
                        )}
                      />
                    ) : item.type === "directory" ? (
                      <Folder
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          isHighlighted
                            ? "text-primary-foreground"
                            : "text-amber-500",
                        )}
                      />
                    ) : (
                      <MessageSquare
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          isHighlighted
                            ? "text-primary-foreground"
                            : "text-green-500",
                        )}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="truncate">
                        {highlightText(item.name, searchQuery)}
                      </div>
                      {item.detail && (
                        <div
                          className={cn(
                            "text-[10px] truncate mt-0.5",
                            isHighlighted
                              ? "text-primary-foreground/75"
                              : "text-muted-foreground",
                          )}
                        >
                          {highlightText(item.detail, searchQuery)}
                        </div>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
            <ScrollBar className="w-1.5" />
          </ScrollArea>
        </div>
      </Tabs>
    </Card>
  )
})

ReferencePicker.displayName = "ReferencePicker"
