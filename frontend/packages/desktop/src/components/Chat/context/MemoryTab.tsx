import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Brain, Loader2, Plus, RefreshCw, Search, Trash2, Edit2, CheckCircle2, XCircle, AlertCircle, Target, ClipboardCheck } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { MemoryService } from "@/client"
import type { ConceptResponse } from "@/client/types.gen"
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
import { useChatStore } from "@/stores/chatStore"
import { MessageContent } from "../MessageContent"

interface MemoryTabProps {
  projectId?: number
}

/**
 * MemoryTab component: Displays project-specific long-term knowledge.
 * Features Search, Add, Edit, Delete, and Detailed History browsing.
 */
export function MemoryTab({ projectId }: MemoryTabProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // --- STATE ---
  const [isAddMemoryOpen, setIsAddMemoryOpen] = useState(false)
  const [newMemoryName, setNewMemoryName] = useState("")
  const [newMemoryDesc, setNewMemoryDesc] = useState("")
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [editingConcept, setEditingConcept] = useState<ConceptResponse | null>(null)
  const [editDesc, setEditDesc] = useState("")

  const activeMemories = useChatStore((s) => s.activeMemories)
  const isActive = (conceptName: string) => {
    return activeMemories.some((m) =>
      m.name?.toLowerCase().includes(conceptName.toLowerCase()),
    )
  }

  // --- DATA FETCHING ---
  const {
    data: concepts,
    isLoading: isLoadingMemory,
    refetch: refetchMemory,
  } = useQuery({
    queryKey: ["projectMemory", projectId],
    queryFn: async () => {
      if (!projectId) return []
      const res = await MemoryService.listConceptsWithCounts({ projectId })
      return res as ConceptResponse[]
    },
    enabled: !!projectId,
  })

  const {
    data: relatedEpisodes,
    isLoading: isLoadingEpisodes,
  } = useQuery({
    queryKey: ["episodesByConcept", projectId, selectedConcept],
    queryFn: async () => {
      if (!projectId || !selectedConcept) return []
      return await MemoryService.getEpisodesByConcept({ projectId, concept: selectedConcept })
    },
    enabled: !!projectId && !!selectedConcept,
  })

  // --- MUTATIONS ---
  const addMemoryMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project selected")
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

  const deleteMemoryMutation = useMutation({
    mutationFn: async (name: string) => {
      if (!projectId) return
      return MemoryService.deleteConcept({ projectId, conceptName: name })
    },
    onSuccess: () => {
      toast.success(t("chat.context.deleteMemory.success") || "Memory deleted")
      queryClient.invalidateQueries({ queryKey: ["projectMemory", projectId] })
    },
    onError: () => toast.error(t("common.error.message"))
  })

  const updateMemoryMutation = useMutation({
    mutationFn: async () => {
      if (!projectId || !editingConcept) return
      return MemoryService.updateConcept({
        projectId,
        conceptName: editingConcept.name,
        requestBody: { description: editDesc }
      })
    },
    onSuccess: () => {
      toast.success(t("chat.context.updateMemory.success") || "Memory updated")
      setEditingConcept(null)
      queryClient.invalidateQueries({ queryKey: ["projectMemory", projectId] })
    },
    onError: () => toast.error(t("common.error.message"))
  })

  // --- HANDLERS ---
  const handleAddMemory = () => {
    if (!newMemoryName.trim()) return
    addMemoryMutation.mutate()
  }

  const filteredConcepts = concepts?.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (!projectId) return null

  return (
    <div className="h-full m-0 flex flex-col bg-background">
      {/* Header */}
      <div className="p-2 border-b flex justify-between items-center bg-muted/20">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-tight ml-1">
          {t("chat.context.memoryTitle")}
        </span>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => refetchMemory()}
          >
            <RefreshCw className={`h-3 w-3 ${isLoadingMemory ? "animate-spin" : ""}`} />
          </Button>

          <Dialog open={isAddMemoryOpen} onOpenChange={setIsAddMemoryOpen}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6">
                <Plus className="h-3 w-3" />
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 italic">
                    <Brain className="h-4 w-4" /> {t("chat.context.addMemory.title")}
                </DialogTitle>
                <DialogDescription />
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">{t("chat.context.addMemory.name")}</Label>
                  <Input id="name" value={newMemoryName} onChange={(e) => setNewMemoryName(e.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="desc">{t("chat.context.addMemory.desc")}</Label>
                  <textarea
                    id="desc"
                    className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={newMemoryDesc}
                    onChange={(e) => setNewMemoryDesc(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsAddMemoryOpen(false)}>{t("common.cancel")}</Button>
                <Button onClick={handleAddMemory} disabled={addMemoryMutation.isPending || !newMemoryName.trim()}>
                  {addMemoryMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("common.save")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      
      {/* Search Bar */}
      <div className="p-2 border-b bg-muted/5">
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={t("chat.context.searchMemory") || "Search memories..."}
            className="pl-8 h-8 text-xs bg-background/50 focus-visible:ring-0 focus-visible:ring-offset-0"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <ScrollArea className="flex-1 p-3">
        <div className="space-y-3">
          {isLoadingMemory ? (
            <div className="flex justify-center p-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground/30" /></div>
          ) : filteredConcepts?.length === 0 ? (
            <div className="text-center text-xs text-muted-foreground py-10 font-medium">
              {searchQuery ? t("chat.context.noMatch") : t("chat.context.noConcepts")}
            </div>
          ) : (
            filteredConcepts?.map((c, i) => {
              const active = isActive(c.name)
              return (
                <div
                  key={i}
                  className={`group relative mb-3 p-3 border rounded-xl transition-all duration-300 ${
                    active
                      ? "bg-primary/5 border-primary/50 shadow-sm"
                      : "bg-muted/5 hover:bg-muted/10 border-muted-foreground/10"
                  }`}
                >
                  <div className="flex items-start justify-between mb-1.5">
                    <div
                      className={`text-sm font-bold flex items-center gap-2 cursor-pointer hover:text-primary transition-colors ${active ? "text-primary" : "text-foreground/90"}`}
                      onClick={() => setSelectedConcept(c.name)}
                    >
                      {active && <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />}
                      {c.name}
                      {(c.episode_count ?? 0) > 0 && (
                        <span className="ml-1 px-1.5 py-0.5 rounded-full bg-primary/10 text-[10px] text-primary/80 font-bold">
                          {c.episode_count} 
                        </span>
                      )}
                    </div>
                    
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-6 w-6 text-muted-foreground hover:text-primary"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingConcept(c);
                          setEditDesc(c.description || "");
                        }}
                      >
                        <Edit2 className="h-3 w-3" />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-6 w-6 text-muted-foreground hover:text-red-500"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(t("chat.context.confirmDelete") || `Delete "${c.name}"?`)) {
                            deleteMemoryMutation.mutate(c.name);
                          }
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  <div 
                    className="text-xs text-muted-foreground line-clamp-2 cursor-pointer hover:text-foreground/80 transition-colors"
                    onClick={() => setSelectedConcept(c.name)}
                  >
                    <MessageContent content={c.description || t("chat.context.noDescription") || "No description"} />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </ScrollArea>

      {/* === EPISODE HISTORY DIALOG (REMASTERED) === */}
      <Dialog open={!!selectedConcept} onOpenChange={(open) => !open && setSelectedConcept(null)}>
        <DialogContent 
           className="sm:max-w-5xl max-h-[90vh] flex flex-col p-0 overflow-hidden border-none shadow-2xl bg-background/95 backdrop-blur-xl"
           style={{ minWidth: "900px" }} // FORCE WIDE VIEW FOR REPORTS
        >
          <DialogHeader className="p-8 border-b bg-muted/20">
            <DialogTitle className="flex items-center gap-4 text-2xl font-black tracking-tight">
              <Brain className="h-8 w-8 text-primary" />
              {t("chat.context.relatedTasksTitle", { concept: selectedConcept })}
              <span className="text-[10px] font-normal bg-primary/10 text-primary px-2 py-0.5 rounded ml-2">V2.1-FULL-VIEW</span>
            </DialogTitle>
            <DialogDescription className="text-base mt-2">
              {t("chat.context.relatedTasksDesc") || "Complete mission history and achieved outcomes for this knowledge concept."}
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full max-h-[calc(90vh-160px)]">
              <div className="p-8 space-y-8">
                {isLoadingEpisodes ? (
                  <div className="flex flex-col items-center justify-center py-32 gap-6">
                    <Loader2 className="h-12 w-12 animate-spin text-primary/30" />
                    <span className="text-sm font-bold text-muted-foreground animate-pulse tracking-widest uppercase">Initializing Log Access...</span>
                  </div>
                ) : relatedEpisodes && relatedEpisodes.length > 0 ? (
                  relatedEpisodes.map((ep: any, i: number) => {
                    const conceptName = selectedConcept?.trim() || "";
                    const goalName = ep.goal?.trim() || "";
                    
                    // Advanced ID masking: If title is just a UID/Session ID, it's boring. Hide it.
                    const isIdTitle = /^[a-f0-9-]{8,}$/i.test(goalName) || goalName.toLowerCase().includes("session summary");
                    const isRedundant = isIdTitle || goalName.toLowerCase() === conceptName.toLowerCase() || conceptName.includes(goalName);

                    let displayResult = ep.result;
                    if (displayResult?.includes("Result:")) {
                        const parts = displayResult.split("Result:");
                        displayResult = parts[1]?.trim() || displayResult;
                    }

                    return (
                      <div key={i} className="group p-8 border rounded-3xl bg-muted/5 hover:bg-white dark:hover:bg-muted/10 transition-all border-muted-foreground/10 hover:border-primary/30 hover:shadow-xl shadow-sm">
                        <div className="flex items-center justify-between mb-8">
                          <div className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-black tracking-tighter border shadow-sm ${
                            ep.error 
                              ? "bg-red-500/10 text-red-600 border-red-500/20" 
                              : "bg-green-500/10 text-green-600 border-green-500/20"
                          }`}>
                            {ep.error ? (
                              <><XCircle className="h-4 w-4" /> CRITICAL FAILURE</>
                            ) : (
                              <><CheckCircle2 className="h-4 w-4" /> MISSION COMPLETE</>
                            )}
                          </div>
                          {ep.timestamp && (
                            <div className="text-xs text-muted-foreground font-mono bg-muted/30 px-3 py-1.5 rounded-lg border border-border/50">
                              {new Date(ep.timestamp).toLocaleString()}
                            </div>
                          )}
                        </div>

                        {!isRedundant && (
                          <div className="mb-8">
                            <div className="flex items-center gap-2 text-muted-foreground mb-3 px-1">
                              <Target className="h-5 w-5" />
                              <span className="text-[10px] uppercase font-black tracking-widest opacity-60">Mission Objective</span>
                            </div>
                            <div className="text-xl font-black text-foreground/90 leading-tight pl-5 border-l-4 border-muted/80">
                              {ep.goal}
                            </div>
                          </div>
                        )}

                        <div className="mt-4">
                          <div className="flex items-center gap-2 text-muted-foreground mb-3 px-1">
                            <ClipboardCheck className="h-5 w-5" />
                            <span className="text-[10px] uppercase font-black tracking-widest opacity-60">Result & Outcome Summary</span>
                          </div>
                          <div className="text-[16px] text-foreground/80 leading-loose pl-6 border-l-4 border-primary/50 py-4 bg-primary/[0.03] rounded-r-2xl">
                            <MessageContent content={displayResult || "No outcome data preserved."} />
                          </div>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-center py-32 bg-muted/2 rounded-3xl border-4 border-dashed border-muted/20">
                    <AlertCircle className="h-20 w-20 text-muted-foreground/10 mx-auto mb-6" />
                    <div className="text-xl font-bold text-muted-foreground/50 tracking-tighter">ARCHIVE EMPTY</div>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>

      {/* === EDIT MEMORY DIALOG === */}
      <Dialog open={!!editingConcept} onOpenChange={(open) => !open && setEditingConcept(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-primary">
              <Edit2 className="h-4 w-4" /> {t("chat.context.editMemory.title")}
            </DialogTitle>
            <DialogDescription>{editingConcept?.name}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-desc">{t("chat.context.addMemory.desc")}</Label>
              <textarea
                id="edit-desc"
                className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingConcept(null)}>{t("common.cancel")}</Button>
            <Button onClick={() => updateMemoryMutation.mutate()} disabled={updateMemoryMutation.isPending}>
              {updateMemoryMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
