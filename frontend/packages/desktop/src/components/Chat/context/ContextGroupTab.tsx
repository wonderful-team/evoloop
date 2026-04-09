import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
    Brain,
    ExternalLink,
    FileText,
    Layers,
    Loader2,
    Plus,
    X,
    CheckCircle2,
    XCircle,
    AlertCircle,
    Target,
    ClipboardCheck
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
    const [isViewAllMemoriesOpen, setIsViewAllMemoriesOpen] = useState(false)
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
            return await MemoryService.listConceptsWithCounts({ projectId })
        },
        enabled: !!projectId,
    })

    const {
        data: episodes,
        isLoading: isLoadingEpisodes,
    } = useQuery({
        queryKey: ["episodesByConcept", projectId, selectedConcept],
        queryFn: async () => {
            if (!projectId || !selectedConcept) return []
            return await MemoryService.getEpisodesByConcept({ projectId, concept: selectedConcept })
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

    return (
        <div className="h-full flex flex-col overflow-hidden">
            <ScrollArea className="flex-1 bg-muted/5">
                <div className="p-3 space-y-4 pb-10">

                {/* === CARD 1: RESOURCES === */}
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
                    <div className="p-3 border-b flex items-center justify-between bg-muted/20">
                        <div className="flex items-center gap-2 font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                            <Layers className="h-3.5 w-3.5" />
                            {t("chat.context.resourcesTitle")}
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
                                    <div className="text-[10px] text-muted-foreground italic pl-1">{t("chat.noLinks")}</div>
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
                            {t("chat.context.memoryTitle")}
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
                                            role="button"
                                            tabIndex={0}
                                            className={`p-2 rounded-lg border text-xs transition-all cursor-pointer select-none ${active ? "bg-primary/10 border-primary/50 ring-1 ring-primary/20" : "bg-muted/10 border-transparent hover:bg-muted/30 hover:border-muted-foreground/20"}`}
                                            onClick={() => setSelectedConcept(c.name)}
                                            onKeyDown={(e) => e.key === 'Enter' && setSelectedConcept(c.name)}
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
                                                <MessageContent content={c.description || t("context.noDescription")} />
                                            </div>
                                        </div>
                                    )
                                })}
                                {concepts.length > 8 && (
                                    <div className="text-center pt-1">
                                        <span 
                                            className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground transition-colors"
                                            onClick={() => setIsViewAllMemoriesOpen(true)}
                                        >
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
                    <DialogContent className="sm:max-w-4xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
                        <DialogHeader className="p-6 border-b">
                            <DialogTitle className="flex items-center gap-2">
                                <Brain className="h-5 w-5 text-primary" />
                                {t("chat.context.relatedTasksTitle", { concept: selectedConcept })}
                            </DialogTitle>
                            <DialogDescription>{t("chat.context.relatedTasksDesc")}</DialogDescription>
                        </DialogHeader>
                        
                        <div className="flex-1 overflow-hidden">
                            <ScrollArea className="h-[calc(85vh-130px)]">
                                <div className="p-6 space-y-6">
                                    {isLoadingEpisodes ? (
                                        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-primary/40" /></div>
                                    ) : episodes && episodes.length > 0 ? (
                                        episodes.map((ep: any, i: number) => {
                                            const conceptName = selectedConcept?.trim() || "";
                                            const goalName = ep.goal?.trim() || "";
                                            const isIdTitle = /^[a-f0-9-]{8,}$/i.test(goalName) || goalName.toLowerCase().includes("session summary");
                                            const isRedundant = isIdTitle || goalName.toLowerCase() === conceptName.toLowerCase() || conceptName.includes(goalName);

                                            let displayResult = ep.result;
                                            if (displayResult?.includes("Result:")) {
                                                const parts = displayResult.split("Result:");
                                                displayResult = parts[1]?.trim() || displayResult;
                                            }

                                            return (
                                                <div key={i} className="p-5 border rounded-xl bg-muted/5 hover:bg-muted/10 transition-all group">
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border ${
                                                            ep.error 
                                                                ? "bg-red-500/10 text-red-600 border-red-500/20" 
                                                                : "bg-green-500/10 text-green-600 border-green-500/20"
                                                        }`}>
                                                            {ep.error ? (
                                                                <><XCircle className="h-3 w-3" /> FAILED</>
                                                            ) : (
                                                                <><CheckCircle2 className="h-3 w-3" /> SUCCESS</>
                                                            )}
                                                        </div>
                                                        {ep.timestamp && (
                                                            <span className="text-[10px] text-muted-foreground font-mono">
                                                                {new Date(ep.timestamp).toLocaleString()}
                                                            </span>
                                                        )}
                                                    </div>

                                                    {!isRedundant && (
                                                        <div className="mb-4">
                                                            <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5 font-semibold text-[10px] uppercase tracking-wider">
                                                                <Target className="h-3 w-3" />
                                                                Objective
                                                            </div>
                                                            <div className="font-semibold text-sm text-foreground/90 leading-relaxed pl-4 border-l-2 border-muted/50">
                                                                {ep.goal}
                                                            </div>
                                                        </div>
                                                    )}

                                                    <div className="mt-2">
                                                        <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5 font-semibold text-[10px] uppercase tracking-wider">
                                                            <ClipboardCheck className="h-3 w-3" />
                                                            {isRedundant ? "Execution Summary" : "Result & Outcome"}
                                                        </div>
                                                        <div className="text-sm text-foreground/80 leading-relaxed pl-4 border-l-2 border-primary py-2 bg-primary/5 rounded-r-md">
                                                            <MessageContent content={displayResult || "No details preserved."} />
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })
                                    ) : (
                                        <div className="text-center text-muted-foreground py-12">{t("chat.context.noEpisodesFound")}</div>
                                    )}
                                </div>
                            </ScrollArea>
                        </div>
                    </DialogContent>
                </Dialog>
  
                {/* === VIEW ALL MEMORIES DIALOG === */}
                <Dialog open={isViewAllMemoriesOpen} onOpenChange={setIsViewAllMemoriesOpen}>
                    <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Brain className="h-5 w-5 text-primary" />
                                {t("chat.context.memoryTitle")}
                                <span className="text-xs font-normal text-muted-foreground ml-2">
                                    ({concepts?.length || 0})
                                </span>
                            </DialogTitle>
                            <DialogDescription>
                                {t("chat.context.allMemoriesDesc")}
                            </DialogDescription>
                        </DialogHeader>
                        
                        <ScrollArea className="flex-1 mt-4 pr-4 h-[60vh]">
                            <div className="flex flex-col gap-3 pb-4">
                                {concepts?.map((c: any, i: number) => {
                                    const active = isActiveMemory(c.name)
                                    const hasEpisodes = (c.episode_count ?? 0) > 0
                                    return (
                                        <div
                                            key={i}
                                            className={`p-4 rounded-xl border transition-all cursor-pointer group ${active ? "bg-primary/5 border-primary/30 ring-1 ring-primary/20" : "bg-muted/10 border-border hover:bg-muted/20"}`}
                                            onClick={() => {
                                                setIsViewAllMemoriesOpen(false);
                                                setTimeout(() => setSelectedConcept(c.name), 100);
                                            }}
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div className={`font-bold flex items-center gap-1.5 ${active ? "text-primary" : ""}`}>
                                                    {active && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
                                                    {c.name}
                                                </div>
                                                {hasEpisodes && (
                                                    <Button 
                                                        variant="ghost" 
                                                        size="sm" 
                                                        className="h-6 px-2 text-[10px] bg-muted/50 hover:bg-muted"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setSelectedConcept(c.name);
                                                        }}
                                                    >
                                                        {t("chat.context.taskCount", { count: c.episode_count })}
                                                    </Button>
                                                )}
                                            </div>
                                            <div className="text-xs text-muted-foreground leading-relaxed">
                                                <MessageContent content={c.description || t("context.noDescription")} />
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </ScrollArea>
                        
                        <DialogFooter className="mt-4 pt-4 border-t">
                            <Button variant="outline" onClick={() => setIsViewAllMemoriesOpen(false)}>
                                {t("common.close")}
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
                </div>
            </ScrollArea>
        </div>
    )
}
