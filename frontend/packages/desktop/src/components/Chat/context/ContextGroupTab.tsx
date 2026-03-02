import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
    Brain,
    ExternalLink,
    FileText,
    Layers,
    Loader2,
    Plus,
    X,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { MemoryService, ResourcesService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { MessageContent } from "../MessageContent"
import { useChatStore } from "@/stores/chatStore"

interface ContextGroupTabProps {
    projectId?: number
}

export function ContextGroupTab({ projectId }: ContextGroupTabProps) {
    const { t } = useTranslation()
    const queryClient = useQueryClient()

    // --- STATE & DATA ---

    // 1. RESOURCES
    const [newLinkName, setNewLinkName] = useState("")
    const [newLinkUrl, setNewLinkUrl] = useState("")
    const {
        data: resources,
        isLoading: isLoadingResources,
        refetch: refetchResources,
    } = useQuery({
        queryKey: ["projectResources", projectId],
        queryFn: async () => {
            if (!projectId) return []
            return ResourcesService.listResources({ projectId })
        },
        enabled: !!projectId,
    })

    const addLinkMutation = useMutation({
        mutationFn: async () => {
            if (!projectId) throw new Error("No project")
            return ResourcesService.createResource({
                projectId,
                requestBody: { type: "link", name: newLinkName, content: newLinkUrl },
            })
        },
        onSuccess: () => {
            toast.success(t("chat.linkAdded"))
            setNewLinkName("")
            setNewLinkUrl("")
            refetchResources()
        },
        onError: () => toast.error(t("chat.linkFailed")),
    })

    const deleteResourceMutation = useMutation({
        mutationFn: async (id: number) => {
            if (!projectId) throw new Error("No project")
            return ResourcesService.deleteResource({ projectId, resourceId: id })
        },
        onSuccess: () => {
            toast.success(t("chat.resourceRemoved"))
            refetchResources()
        },
    })

    // 2. MEMORY
    const activeMemories = useChatStore((s) => s.activeMemories)
    const isActiveMemory = (conceptName: string) => {
        return activeMemories.some((m) =>
            m.name?.toLowerCase().includes(conceptName.toLowerCase())
        )
    }
    const [isAddMemoryOpen, setIsAddMemoryOpen] = useState(false)
    const [newMemoryName, setNewMemoryName] = useState("")
    const [newMemoryDesc, setNewMemoryDesc] = useState("")
    const [selectedConcept, setSelectedConcept] = useState<string | null>(null)
    const {
        data: concepts,
        isLoading: isLoadingMemory,
    } = useQuery({
        queryKey: ["projectMemory", projectId],
        queryFn: async () => {
            if (!projectId) return []
            // Use the new endpoint that includes episode counts
            const res = await MemoryService.listConceptsWithCounts({ projectId })
            return res
        },
        enabled: !!projectId,
    })

    // Episodes by concept (for drill-down)
    const {
        data: episodes,
        isLoading: isLoadingEpisodes,
    } = useQuery({
        queryKey: ["episodesByConcept", projectId, selectedConcept],
        queryFn: async () => {
            if (!projectId || !selectedConcept) return []
            const res = await MemoryService.getEpisodesByConcept({ projectId, concept: selectedConcept })
            return res
        },
        enabled: !!projectId && !!selectedConcept,
    })

    const addMemoryMutation = useMutation({
        mutationFn: async () => {
            if (!projectId) throw new Error("No project")
            return MemoryService.addConcept({
                projectId,
                requestBody: {
                    name: newMemoryName,
                    description: newMemoryDesc,
                    related_files: [],
                },
            })
        },
        onSuccess: () => {
            toast.success(t("chat.context.addMemory.success"))
            setIsAddMemoryOpen(false)
            setNewMemoryName("")
            setNewMemoryDesc("")
            queryClient.invalidateQueries({ queryKey: ["projectMemory", projectId] })
        },
        onError: () => toast.error(t("common.error.message")),
    })


    if (!projectId) return null

    // --- RENDER ---
    return (
        <ScrollArea className="h-full bg-muted/5">
            <div className="p-3 space-y-4">

                {/* === CARD 1: RESOURCES === */}
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
                    <div className="p-3 border-b flex items-center justify-between bg-muted/20">
                        <div className="flex items-center gap-2 font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                            <Layers className="h-3.5 w-3.5" />
                            {t("chat.context.resourcesTitle", "Resources")}
                        </div>
                        <div className="flex gap-1">
                            <Dialog>
                                <DialogTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-6 w-6 hover:bg-background">
                                        <Plus className="h-3.5 w-3.5" />
                                    </Button>
                                </DialogTrigger>
                                <DialogContent>
                                    <DialogHeader>
                                        <DialogTitle>{t("chat.addLinkTitle")}</DialogTitle>
                                    </DialogHeader>
                                    <div className="grid gap-4 py-4">
                                        <div className="grid gap-2">
                                            <Label>{t("common.name")}</Label>
                                            <Input value={newLinkName} onChange={(e) => setNewLinkName(e.target.value)} placeholder={t("chat.linkNamePlaceholder")} />
                                        </div>
                                        <div className="grid gap-2">
                                            <Label>{t("common.url")}</Label>
                                            <Input value={newLinkUrl} onChange={(e) => setNewLinkUrl(e.target.value)} placeholder={t("chat.linkUrlPlaceholder")} />
                                        </div>
                                    </div>
                                    <DialogFooter>
                                        <Button onClick={() => addLinkMutation.mutate()} disabled={!newLinkName || !newLinkUrl}>
                                            {t("common.add")}
                                        </Button>
                                    </DialogFooter>
                                </DialogContent>
                            </Dialog>
                        </div>
                    </div>
                    <div className="p-3 space-y-3">
                        {/* Pinned Files */}
                        <div>
                            <div className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                                <FileText className="h-3 w-3" /> {t("chat.pinnedFiles")}
                            </div>
                            {isLoadingResources ? (
                                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                            ) : resources && resources.filter(r => r.type === "file").length > 0 ? (
                                <div className="space-y-1">
                                    {resources.filter(r => r.type === "file").slice(0, 5).map(res => (
                                        <div key={res.id} className="flex items-center gap-2 text-xs p-1.5 bg-muted/30 rounded group relative">
                                            <FileText className="h-3 w-3 text-blue-500 shrink-0" />
                                            <span className="truncate flex-1 font-mono" title={res.content}>{res.name}</span>
                                            <Button variant="ghost" size="icon" className="h-4 w-4 opacity-0 group-hover:opacity-100 absolute right-1" onClick={() => deleteResourceMutation.mutate(res.id)}>
                                                <X className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-[10px] text-muted-foreground italic pl-1">{t("chat.noPinnedFiles")}</div>
                            )}
                        </div>

                        {/* Links */}
                        <div>
                            <div className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                                <ExternalLink className="h-3 w-3" /> {t("chat.externalLinks")}
                            </div>
                            <div className="space-y-1">
                                {resources?.filter(r => r.type === "link").map(res => (
                                    <div key={res.id} className="flex items-center gap-2 text-xs p-1.5 bg-muted/30 rounded group relative">
                                        <ExternalLink className="h-3 w-3 text-green-500 shrink-0" />
                                        <a href={res.content} target="_blank" rel="noreferrer" className="truncate flex-1 hover:underline">{res.name}</a>
                                        <Button variant="ghost" size="icon" className="h-4 w-4 opacity-0 group-hover:opacity-100 absolute right-1" onClick={() => deleteResourceMutation.mutate(res.id)}>
                                            <X className="h-3 w-3" />
                                        </Button>
                                    </div>
                                ))}
                                {(!resources || resources.filter(r => r.type === "link").length === 0) && (
                                    <div className="text-[10px] text-muted-foreground italic pl-1">{t("chat.noLinks", "No links added")}</div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* === CARD 2: MEMORY === */}
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
                    <div className="p-3 border-b flex items-center justify-between bg-muted/20">
                        <div className="flex items-center gap-2 font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                            <Brain className="h-3.5 w-3.5" />
                            {t("chat.context.memoryTitle", "Project Memory")}
                        </div>
                        <Dialog open={isAddMemoryOpen} onOpenChange={setIsAddMemoryOpen}>
                            <DialogTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-6 w-6 hover:bg-background">
                                    <Plus className="h-3.5 w-3.5" />
                                </Button>
                            </DialogTrigger>
                            <DialogContent>
                                <DialogHeader><DialogTitle>{t("chat.context.addMemory.title")}</DialogTitle></DialogHeader>
                                <div className="grid gap-4 py-4">
                                    <div className="grid gap-2">
                                        <Label>{t("chat.context.addMemory.name")}</Label>
                                        <Input value={newMemoryName} onChange={e => setNewMemoryName(e.target.value)} />
                                    </div>
                                    <div className="grid gap-2">
                                        <Label>{t("chat.context.addMemory.desc")}</Label>
                                        <textarea className="flex min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm" value={newMemoryDesc} onChange={e => setNewMemoryDesc(e.target.value)} />
                                    </div>
                                </div>
                                <DialogFooter>
                                    <Button onClick={() => addMemoryMutation.mutate()} disabled={!newMemoryName.trim()}>{t("common.save")}</Button>
                                </DialogFooter>
                            </DialogContent>
                        </Dialog>
                    </div>
                    <div className="p-3">
                        {isLoadingMemory ? (
                            <div className="flex justify-center"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
                        ) : concepts && concepts.length > 0 ? (
                            <div className="space-y-2">
                                {concepts.slice(0, 8).map((c: any, i: number) => {
                                    const active = isActiveMemory(c.name)
                                    const hasEpisodes = (c.episode_count ?? 0) > 0
                                    return (
                                        <div
                                            key={i}
                                            className={`p-2 rounded border text-xs transition-colors cursor-pointer ${active ? "bg-primary/10 border-primary/50" : "bg-muted/10 border-transparent hover:bg-muted/20"}`}
                                            onClick={() => hasEpisodes && setSelectedConcept(c.name)}
                                        >
                                            <div className={`font-medium mb-0.5 flex items-center justify-between ${active ? "text-primary" : ""}`}>
                                                <span className="flex items-center gap-1.5">
                                                    {active && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
                                                    {c.name}
                                                </span>
                                                {hasEpisodes && (
                                                    <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                                        {t("chat.context.taskCount", { count: c.episode_count })}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="text-muted-foreground line-clamp-2 leading-relaxed">
                                                <MessageContent content={c.description} />
                                            </div>
                                        </div>
                                    )
                                })}
                                {concepts.length > 8 && (
                                    <div className="text-center pt-1">
                                        <span className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground">
                                            {t("chat.context.viewAllMemories", { count: concepts.length })}
                                        </span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="text-xs text-muted-foreground italic text-center py-2">{t("chat.context.noConcepts")}</div>
                        )}
                    </div>
                </div>

                {/* === EPISODE HISTORY DIALOG === */}
                <Dialog open={!!selectedConcept} onOpenChange={(open) => !open && setSelectedConcept(null)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Brain className="h-4 w-4" />
                                {t("chat.context.relatedTasksTitle", { concept: selectedConcept })}
                            </DialogTitle>
                            <DialogDescription>{t("chat.context.relatedTasksDesc")}</DialogDescription>
                        </DialogHeader>
                        <div className="max-h-[300px] overflow-y-auto space-y-2 py-2">
                            {isLoadingEpisodes ? (
                                <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin" /></div>
                            ) : episodes && episodes.length > 0 ? (
                                episodes.map((ep: any, i: number) => (
                                    <div key={i} className="p-2 border rounded text-xs bg-muted/10">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${ep.error ? "bg-red-500/20 text-red-600" : "bg-green-500/20 text-green-600"}`}>
                                                {ep.error ? "FAILED" : "SUCCESS"}
                                            </span>
                                        </div>
                                        <div className="font-medium line-clamp-2">{ep.goal}</div>
                                        {ep.result && <div className="text-muted-foreground mt-1 line-clamp-2">{ep.result}</div>}
                                    </div>
                                ))
                            ) : (
                                <div className="text-center text-muted-foreground py-4">{t("chat.context.noEpisodesFound")}</div>
                            )}
                        </div>
                    </DialogContent>
                </Dialog>


            </div>
        </ScrollArea>
    )
}
