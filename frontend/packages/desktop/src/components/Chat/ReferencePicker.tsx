import { useState, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { File, MessageSquare, Loader2 } from "lucide-react"
import { FilesService, ConversationsService } from "@/client/sdk.gen"
import { Card } from "@evoloop/shared/components/ui/card"
import { Input } from "@evoloop/shared/components/ui/input"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Tabs, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { cn } from "@evoloop/shared/lib/utils"

export interface ReferenceItem {
    type: "file" | "message"
    id: string
    name: string
    detail?: string
}

interface ReferencePickerProps {
    projectId: number
    onSelect: (item: ReferenceItem) => void
    onClose: () => void
    className?: string
}

export function ReferencePicker({ projectId, onSelect, onClose, className }: ReferencePickerProps) {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState<"files" | "messages">("files")
    const [searchQuery, setSearchQuery] = useState("")
    const [items, setItems] = useState<ReferenceItem[]>([])
    const [isLoading, setIsLoading] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)

    // Auto-focus input on mount
    useEffect(() => {
        inputRef.current?.focus()
    }, [])

    // Debounced search
    useEffect(() => {
        const timer = setTimeout(() => {
            if (searchQuery.trim()) {
                fetchResults()
            } else {
                setItems([])
            }
        }, 300)

        return () => clearTimeout(timer)
    }, [searchQuery, activeTab, projectId])

    const fetchResults = async () => {
        setIsLoading(true)
        setItems([])
        try {
            if (activeTab === "files") {
                const res = await FilesService.searchFilesByName({
                    projectId,
                    q: searchQuery
                })
                const mapped: ReferenceItem[] = res.map((f: any) => ({
                    type: "file",
                    id: f.path, // Use path as ID for files
                    name: f.name,
                    detail: f.path
                }))
                setItems(mapped)
            } else {
                const res = await ConversationsService.searchConversations({
                    projectId,
                    q: searchQuery
                })
                const mapped: ReferenceItem[] = res.map((c: any) => ({
                    type: "message",
                    id: c.thread_id, // Use thread_id for now, or match_snippet ID if available? 
                    // The search result has thread_id, role, content, created_at. 
                    // Ideally we want to reference a specific message, but thread ref is also ok.
                    // Let's assume we reference the thread or specific content.
                    name: c.content ? c.content.slice(0, 50) + "..." : "Message",
                    detail: `Thread: ${c.thread_id.slice(0, 8)}...`
                }))
                setItems(mapped)
            }
        } catch (error) {
            console.error("Search failed", error)
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <Card className={cn("w-[400px] flex flex-col overflow-hidden shadow-xl border-primary/20", className)}>
            <div className="p-2 border-b">
                <Input
                    ref={inputRef}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t("chat.reference.searchPlaceholder", "Search...")}
                    className="h-9 border-none focus-visible:ring-0 bg-secondary/50"
                    onKeyDown={(e) => {
                        if (e.key === "Escape") onClose()
                    }}
                />
            </div>

            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="flex-1 flex flex-col">
                <TabsList className="w-full justify-start rounded-none border-b h-9 p-0 px-2 bg-transparent">
                    <TabsTrigger value="files" className="h-full px-4 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent">
                        {t("chat.reference.files", "Files")}
                    </TabsTrigger>
                    <TabsTrigger value="messages" className="h-full px-4 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent">
                        {t("chat.reference.messages", "Messages")}
                    </TabsTrigger>
                </TabsList>

                <div className="flex-1 overflow-hidden relative">
                    {isLoading && (
                        <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                    )}

                    <ScrollArea className="h-[250px]">
                        {items.length === 0 && !isLoading && (
                            <div className="p-4 text-center text-sm text-muted-foreground">
                                {searchQuery ? t("chat.reference.noResults", "No results found") : t("chat.reference.typeToSearch", "Type to search...")}
                            </div>
                        )}

                        <div className="p-1 space-y-0.5">
                            {items.map((item) => (
                                <button
                                    key={`${item.type}-${item.id}`}
                                    onClick={() => onSelect(item)}
                                    className="w-full text-left px-3 py-2 text-sm rounded-sm hover:bg-accent hover:text-accent-foreground flex items-center gap-2 group transition-colors"
                                >
                                    {item.type === "file" ? (
                                        <File className="h-4 w-4 shrink-0 text-blue-500" />
                                    ) : (
                                        <MessageSquare className="h-4 w-4 shrink-0 text-green-500" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium truncate">{item.name}</div>
                                        {item.detail && <div className="text-xs text-muted-foreground truncate">{item.detail}</div>}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </ScrollArea>
                </div>
            </Tabs>
        </Card>
    )
}
