import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Brain, Map, Layers, Database, ExternalLink, X, Plus, RefreshCw, Loader2, Search, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { MemoryService, PlanningService, FilesService } from "@/client"
import { ConceptResponse } from "@/client/types.gen"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"

interface ContextPanelProps {
    projectId?: number
    activeThreadId?: string
    onClose?: () => void
}

interface PlanStep {
    id: string
    title: string
    status: 'pending' | 'in_progress' | 'completed' | 'failed'
    result?: string
}

interface Plan {
    id: string
    title: string
    steps: PlanStep[]
    current_step_id?: string
}

interface FileSearchResult {
    file: string
    line: number
    content: string
}

export function ContextPanel({ projectId, activeThreadId, onClose }: ContextPanelProps) {
    const { t } = useTranslation()
    const queryClient = useQueryClient()
    const [activeTab, setActiveTab] = useState("memory")
    const [searchQuery, setSearchQuery] = useState("")

    // Add Memory State
    const [isAddMemoryOpen, setIsAddMemoryOpen] = useState(false)
    const [newMemoryName, setNewMemoryName] = useState("")
    const [newMemoryDesc, setNewMemoryDesc] = useState("")

    // --- Queries ---

    // 1. Memory Concepts
    const { data: concepts, isLoading: isLoadingMemory, refetch: refetchMemory } = useQuery({
        queryKey: ["projectMemory", projectId],
        queryFn: async () => {
            if (!projectId) return []
            // Using search with empty string to get all (as per backend impl)
            const res = await MemoryService.listConcepts({ projectId })
            return res as ConceptResponse[]
        },
        enabled: !!projectId && activeTab === 'memory'
    })

    // Add Memory Mutation
    const addMemoryMutation = useMutation({
        mutationFn: async () => {
            if (!projectId) throw new Error("No project selected")
            return MemoryService.addConcept({
                projectId,
                requestBody: {
                    name: newMemoryName,
                    description: newMemoryDesc,
                    related_files: []
                }
            })
        },
        onSuccess: () => {
            toast.success(t('chat.context.addMemory.success'))
            setIsAddMemoryOpen(false)
            setNewMemoryName("")
            setNewMemoryDesc("")
            queryClient.invalidateQueries({ queryKey: ["projectMemory", projectId] })
        },
        onError: (err) => {
            console.error(err)
            toast.error(t('common.error.message'))
        }
    })

    const handleAddMemory = () => {
        if (!newMemoryName.trim()) return
        addMemoryMutation.mutate()
    }

    // 2. Active Plan
    const { data: planData, isLoading: isLoadingPlan } = useQuery({
        queryKey: ["threadPlan", activeThreadId],
        queryFn: async () => {
            if (!activeThreadId) return null
            return PlanningService.getPlan({ threadId: activeThreadId })
        },
        enabled: !!activeThreadId && activeTab === 'plan',
        refetchInterval: activeTab === 'plan' ? 3000 : false // Poll when plan tab is open
    })

    // Safety check for plan structure
    // The SDK returns 'unknown' for this endpoint, so we cast it relative to our known backend response structure
    const typedPlanData = planData as any
    const plan = typedPlanData?.plan as Plan | null
    const planStatus = typedPlanData?.status

    // 3. Knowledge Search
    const { data: searchResults, isLoading: isLoadingSearch, refetch: searchFiles } = useQuery({
        queryKey: ["fileSearch", projectId, searchQuery],
        queryFn: async () => {
            if (!projectId || !searchQuery) return []
            const res = await FilesService.searchFiles({ projectId, q: searchQuery })
            return res as any as FileSearchResult[] // Cast strict unknown from SDK to known search result shape
        },
        enabled: false // Trigger manually
    })

    if (!projectId) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4 text-center">
                <Brain className="h-10 w-10 mb-2 opacity-20" />
                <p>{t('chat.context.selectProject')}</p>
            </div>
        )
    }

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault()
        if (searchQuery.trim().length >= 2) {
            searchFiles()
        }
    }

    return (
        <div className="flex flex-col h-full bg-background border-l">
            <div className="flex items-center justify-between p-3 border-b h-14 shrink-0">
                <span className="font-semibold text-sm flex items-center gap-2">
                    <Brain className="h-4 w-4 text-primary" />
                    {t('chat.context.title')}
                </span>
                {onClose && (
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
                        <X className="h-4 w-4" />
                    </Button>
                )}
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                <div className="px-3 pt-2 shrink-0">
                    <TabsList className="grid w-full grid-cols-4">
                        <TabsTrigger value="memory" title={t('chat.context.tabMemory')}><Brain className="h-4 w-4" /></TabsTrigger>
                        <TabsTrigger value="plan" title={t('chat.context.tabPlan')}><Map className="h-4 w-4" /></TabsTrigger>
                        <TabsTrigger value="knowledge" title={t('chat.context.tabKnowledge')}><Database className="h-4 w-4" /></TabsTrigger>
                        <TabsTrigger value="resources" title={t('chat.context.tabResources')}><Layers className="h-4 w-4" /></TabsTrigger>
                    </TabsList>
                </div>

                <div className="flex-1 overflow-hidden relative">
                    {/* Memory Tab */}
                    <TabsContent value="memory" className="h-full m-0 flex flex-col">
                        <div className="p-2 border-b flex justify-between items-center bg-muted/20">
                            <span className="text-xs font-medium text-muted-foreground">{t('chat.context.memoryTitle')}</span>
                            <div className="flex gap-1">
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => refetchMemory()}>
                                    <RefreshCw className={`h-3 w-3 ${isLoadingMemory ? 'animate-spin' : ''}`} />
                                </Button>

                                <Dialog open={isAddMemoryOpen} onOpenChange={setIsAddMemoryOpen}>
                                    <DialogTrigger asChild>
                                        <Button variant="ghost" size="icon" className="h-6 w-6">
                                            <Plus className="h-3 w-3" />
                                        </Button>
                                    </DialogTrigger>
                                    <DialogContent>
                                        <DialogHeader>
                                            <DialogTitle>{t('chat.context.addMemory.title')}</DialogTitle>
                                            <DialogDescription>
                                            </DialogDescription>
                                        </DialogHeader>
                                        <div className="grid gap-4 py-4">
                                            <div className="grid gap-2">
                                                <Label htmlFor="name">{t('chat.context.addMemory.name')}</Label>
                                                <Input
                                                    id="name"
                                                    value={newMemoryName}
                                                    onChange={(e) => setNewMemoryName(e.target.value)}
                                                />
                                            </div>
                                            <div className="grid gap-2">
                                                <Label htmlFor="desc">{t('chat.context.addMemory.desc')}</Label>
                                                <textarea
                                                    id="desc"
                                                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                                    value={newMemoryDesc}
                                                    onChange={(e) => setNewMemoryDesc(e.target.value)}
                                                />
                                            </div>
                                        </div>
                                        <DialogFooter>
                                            <Button variant="outline" onClick={() => setIsAddMemoryOpen(false)}>{t('common.cancel')}</Button>
                                            <Button onClick={handleAddMemory} disabled={addMemoryMutation.isPending || !newMemoryName.trim()}>
                                                {addMemoryMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                                {t('common.save')}
                                            </Button>
                                        </DialogFooter>
                                    </DialogContent>
                                </Dialog>
                            </div>
                        </div>
                        <ScrollArea className="flex-1 p-3">
                            <div className="space-y-3">
                                {isLoadingMemory ? (
                                    <div className="flex justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                                ) : concepts?.length === 0 ? (
                                    <div className="text-center text-xs text-muted-foreground py-8">
                                        {t('chat.context.noConcepts')}
                                    </div>
                                ) : (
                                    concepts?.map((c, i) => (
                                        <Card key={i} className="shadow-sm">
                                            <CardHeader className="p-3 pb-1">
                                                <CardTitle className="text-sm font-medium">{c.name}</CardTitle>
                                            </CardHeader>
                                            <CardContent className="p-3 pt-1 text-xs text-muted-foreground">
                                                {c.description}
                                            </CardContent>
                                        </Card>
                                    ))
                                )}
                            </div>
                        </ScrollArea>
                    </TabsContent>

                    {/* Plan Tab */}
                    <TabsContent value="plan" className="h-full m-0 flex flex-col">
                        <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
                            <span className="text-xs font-medium text-muted-foreground">{t('chat.context.planTitle')}</span>
                            <span className="text-[10px] uppercase font-bold text-muted-foreground/50">
                                {planStatus === 'no_graph' ? t('chat.context.statusOffline') : planStatus === 'no_state' ? t('chat.context.statusIdle') : t('chat.context.statusActive')}
                            </span>
                        </div>
                        <ScrollArea className="flex-1 p-3">
                            {isLoadingPlan ? (
                                <div className="flex justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                            ) : !plan ? (
                                <div className="text-center text-xs text-muted-foreground py-8 border-2 border-dashed rounded-md">
                                    {t('chat.context.noPlan')}
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="font-medium text-sm border-b pb-2">
                                        {plan.title}
                                    </div>
                                    <div className="space-y-3">
                                        {plan.steps.map((step, idx) => (
                                            <div key={step.id} className={`relative pl-4 border-l-2 ${step.status === 'completed' ? 'border-primary' :
                                                step.status === 'in_progress' ? 'border-yellow-500' : 'border-muted'
                                                }`}>
                                                <div className="text-xs font-medium flex items-center gap-2">
                                                    <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${step.status === 'completed' ? 'bg-primary text-primary-foreground' :
                                                        step.status === 'in_progress' ? 'bg-yellow-500 text-white' : 'bg-muted text-muted-foreground'
                                                        }`}>
                                                        {idx + 1}
                                                    </span>
                                                    {step.title}
                                                </div>
                                                {step.result && (
                                                    <div className="mt-1 text-[10px] text-muted-foreground bg-muted/30 p-1.5 rounded">
                                                        {step.result}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </ScrollArea>
                    </TabsContent>

                    {/* Knowledge Tab */}
                    <TabsContent value="knowledge" className="h-full m-0 flex flex-col">
                        <div className="p-2 border-b bg-muted/20 space-y-2">
                            <form onSubmit={handleSearch} className="flex gap-2">
                                <Input
                                    className="h-8 text-xs"
                                    placeholder={t('chat.context.searchPlaceholder')}
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                                <Button size="icon" variant="secondary" className="h-8 w-8" type="submit">
                                    <Search className="h-4 w-4" />
                                </Button>
                            </form>
                        </div>
                        <ScrollArea className="flex-1 p-3">
                            {isLoadingSearch ? (
                                <div className="flex justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                            ) : searchResults && searchResults.length > 0 ? (
                                <div className="space-y-2">
                                    {searchResults.map((result, i) => (
                                        <div key={i} className="border rounded p-2 text-xs bg-card hover:bg-accent/50 transition-colors cursor-pointer group">
                                            <div className="font-medium flex items-center gap-1.5 text-primary mb-1">
                                                <FileText className="h-3 w-3" />
                                                {result.file}:{result.line}
                                            </div>
                                            <div className="font-mono text-muted-foreground truncate opacity-80 group-hover:opacity-100">
                                                {result.content}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center text-xs text-muted-foreground py-8">
                                    {searchResults ? t('chat.context.noMatches') : t('chat.context.searchPrompt')}
                                </div>
                            )}
                        </ScrollArea>
                    </TabsContent>

                    {/* Resources Tab */}
                    <TabsContent value="resources" className="h-full m-0 flex flex-col">
                        <ScrollArea className="flex-1 p-3">
                            <div className="space-y-4">
                                <h4 className="text-sm font-medium leading-none">{t('chat.context.resourcesTitle')}</h4>
                                <Button variant="outline" className="w-full justify-start gap-2 h-9" onClick={() => window.open("about:blank", "_blank")}>
                                    <ExternalLink className="h-4 w-4" />
                                    {t('chat.context.openImagicBox')}
                                </Button>
                            </div>
                        </ScrollArea>
                    </TabsContent>
                </div>
            </Tabs>
        </div>
    )
}
