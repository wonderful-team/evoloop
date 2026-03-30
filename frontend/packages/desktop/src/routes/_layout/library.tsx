import { createFileRoute } from "@tanstack/react-router"
import {
    Database, Search, Loader2, Brain, FileText,
    ExternalLink, Upload, Trash2, File,
    Clock, RefreshCw, Layers
} from "lucide-react"
import { useState, useRef } from "react"
import { useTranslation } from "react-i18next"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { MemoryService, LibraryService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@evoloop/shared/components/ui/card"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@evoloop/shared/components/ui/table"
import { toast } from "sonner"

export const Route = createFileRoute("/_layout/library")({
    component: LibraryPage,
})

function LibraryPage() {
    const { t } = useTranslation()
    const queryClient = useQueryClient()
    const [searchQuery, setSearchQuery] = useState("")
    const [activeTab, setActiveTab] = useState("search")
    const fileInputRef = useRef<HTMLInputElement>(null)

    // --- SEARCH QUERIES ---
    const { data: searchResults, isLoading: isSearching, refetch: runSearch, isFetched } = useQuery({
        queryKey: ["globalMemorySearch", searchQuery],
        queryFn: async () => {
            if (!searchQuery) return []
            const res = await (MemoryService as any).searchMemory({ q: searchQuery })
            return res as any[]
        },
        enabled: false,
    })

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault()
        if (searchQuery.trim().length >= 1) {
            runSearch()
        }
    }

    // --- MANAGEMENT QUERIES ---
    const { data: libraryFiles, isLoading: isLoadingFiles, refetch: refreshFiles } = useQuery({
        queryKey: ["libraryFiles"],
        queryFn: () => LibraryService.listLibraryFiles({}),
    })

    const uploadMutation = useMutation({
        mutationFn: (file: File) => LibraryService.uploadLibraryFile({ formData: { file } }),
        onSuccess: () => {
            toast.success(t("common.success", "Upload successful"))
            refreshFiles()
            queryClient.invalidateQueries({ queryKey: ["globalMemorySearch"] })
        },
        onError: (err: any) => {
            toast.error(t("common.error.message", "Upload failed") + `: ${err.message}`)
        }
    })

    const deleteMutation = useMutation({
        mutationFn: (id: number) => LibraryService.deleteLibraryFile({ fileId: id }),
        onSuccess: () => {
            toast.success(t("common.success", "File deleted"))
            refreshFiles()
            queryClient.invalidateQueries({ queryKey: ["globalMemorySearch"] })
        },
        onError: (err: any) => {
            toast.error(t("common.error.message", "Delete failed") + `: ${err.message}`)
        }
    })

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) {
            uploadMutation.mutate(file)
        }
    }

    return (
        <div className="flex flex-col h-full bg-background/50 overflow-y-auto">
            <div className="p-6 max-w-6xl mx-auto w-full flex flex-col gap-6 pb-20">
                {/* Header Section */}
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                    <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-3">
                            <Database className="h-6 w-6 text-primary" />
                            <h1 className="text-2xl font-bold tracking-tight text-foreground">
                                {t("library.title", "Library")}
                            </h1>
                        </div>
                        <p className="text-muted-foreground text-sm max-w-2xl">
                            {t("library.subtitle", "Global knowledge hub for memories, documents, and media assets.")}
                        </p>
                    </div>

                    <Tabs value={activeTab} onValueChange={setActiveTab} className="bg-muted/30 p-1 rounded-lg border self-start md:self-auto">
                        <TabsList className="bg-transparent border-none h-8">
                            <TabsTrigger value="search" className="rounded-md px-4 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all">
                                <Search className="h-3.5 w-3.5" />
                                {t("common.search", "Search")}
                            </TabsTrigger>
                            <TabsTrigger value="manage" className="rounded-md px-4 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all">
                                <Layers className="h-3.5 w-3.5" />
                                {t("common.manage", "Manage")}
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>
                </div>

                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsContent value="search" className="mt-0 flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                        {/* Search Bar */}
                        <Card className="border shadow-sm bg-card overflow-hidden rounded-xl">
                            <CardContent className="p-6">
                                <form onSubmit={handleSearch} className="flex gap-3">
                                    <div className="relative flex-1 group">
                                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                                        <input
                                            className="w-full pl-10 pr-4 h-10 text-sm border-2 border-transparent bg-muted/50 focus:bg-background focus:border-primary/20 rounded-lg transition-all outline-none"
                                            placeholder={t("library.searchPlaceholder", "Ask anything about your projects...")}
                                            value={searchQuery}
                                            onChange={(e) => setSearchQuery(e.target.value)}
                                        />
                                    </div>
                                    <Button type="submit" size="sm" className="h-10 px-6 font-semibold rounded-lg shadow-sm">
                                        {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : t("common.search", "Search")}
                                    </Button>
                                </form>
                            </CardContent>
                        </Card>

                        {/* Search Content */}
                        <div className="flex-1 min-h-[400px]">
                            {isSearching ? (
                                <div className="flex flex-col items-center justify-center py-32 gap-4">
                                    <Loader2 className="h-10 w-10 animate-spin text-primary opacity-50" />
                                    <p className="text-muted-foreground text-sm font-medium animate-pulse">{t("common.scanning", "Scanning knowledge base...")}</p>
                                </div>
                            ) : isFetched && searchResults && searchResults.length > 0 ? (
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {searchResults.map((result: any, i: number) => (
                                        <Card key={i} className="group hover:border-primary/30 transition-all border bg-card shadow-sm rounded-xl overflow-hidden">
                                            <CardHeader className="p-4 pb-2">
                                                <div className="flex items-start justify-between">
                                                    <div className="flex gap-3">
                                                        <div className="p-2 bg-purple-500/10 rounded-lg group-hover:bg-purple-500/15 transition-all">
                                                            <Brain className="h-4 w-4 text-purple-400" />
                                                        </div>
                                                        <div>
                                                            <CardTitle className="text-base font-semibold leading-tight mb-1">{result.name}</CardTitle>
                                                            <div className="flex items-center gap-2">
                                                                <Badge variant="outline" className="text-[10px] py-0 px-1.5 border-primary/20 bg-primary/5 text-primary">
                                                                    {result.project_name || t("common.global", "Global")}
                                                                </Badge>
                                                                <span className="text-[10px] text-muted-foreground/60 flex items-center gap-1 font-medium">
                                                                    <Clock className="h-3 w-3" />
                                                                    {new Date(result.created_at || Date.now()).toLocaleDateString()}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </CardHeader>
                                            <CardContent className="p-4 pt-0">
                                                <p className="text-sm text-muted-foreground/80 line-clamp-3 leading-relaxed mb-4">
                                                    {result.description}
                                                </p>
                                                <div className="flex flex-wrap gap-2 pt-3 border-t border-muted/30">
                                                    {result.sources?.slice(0, 3).map((source: any, j: number) => (
                                                        <div key={j} className="flex items-center gap-1.5 text-[10px] bg-muted/50 px-2 py-1 rounded-md text-muted-foreground/80 border border-transparent">
                                                            <FileText className="h-3 w-3 text-blue-400/70" />
                                                            <span className="truncate max-w-[120px]">{source.file.split('/').pop()}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </CardContent>
                                        </Card>
                                    ))}
                                </div>
                            ) : isFetched ? (
                                <div className="flex flex-col items-center justify-center py-24 bg-muted/10 rounded-2xl border-2 border-dashed border-muted/20">
                                    <div className="p-6 bg-muted/20 rounded-full mb-4">
                                        <Search className="h-10 w-10 text-muted-foreground/40" />
                                    </div>
                                    <p className="text-muted-foreground font-semibold">{t("library.emptyTitle", "No knowledge matches found.")}</p>
                                    <p className="text-muted-foreground/40 text-sm mt-1">{t("library.emptySubtitle", "Try broadening your search terms.")}</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    <Card className="flex flex-col gap-4 p-6 rounded-xl bg-card border shadow-sm hover:border-primary/20 transition-all group">
                                        <div className="h-10 w-10 rounded-lg bg-indigo-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                                            <Brain className="h-5 w-5 text-indigo-400" />
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-sm mb-1">{t("library.memoryTitle", "Unified Memory")}</h3>
                                            <p className="text-xs text-muted-foreground leading-relaxed">{t("library.memoryDesc", "Search through all concepts learned during chat sessions across all projects.")}</p>
                                        </div>
                                    </Card>
                                    <Card className="flex flex-col gap-4 p-6 rounded-xl bg-card border shadow-sm hover:border-primary/20 transition-all group">
                                        <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                                            <FileText className="h-5 w-5 text-purple-400" />
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-sm mb-1">{t("library.docsTitle", "Documentation")}</h3>
                                            <p className="text-xs text-muted-foreground leading-relaxed">{t("library.docsDesc", "Quickly find relevant snippets from your project documentation and wiki pages.")}</p>
                                        </div>
                                    </Card>
                                    <Card className="flex flex-col gap-4 p-6 rounded-xl bg-card border shadow-sm hover:border-primary/20 transition-all group">
                                        <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                                            <ExternalLink className="h-5 w-5 text-primary" />
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-sm mb-1">{t("library.crossTitle", "Cross-Project")}</h3>
                                            <p className="text-xs text-muted-foreground leading-relaxed">{t("library.crossDesc", "Leverage solutions from previous projects to solve current technical challenges.")}</p>
                                        </div>
                                    </Card>
                                </div>
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="manage" className="mt-0 animate-in fade-in duration-300 flex flex-col gap-6">
                        {/* Management Controls */}
                        <div className="flex flex-col md:flex-row items-center justify-between bg-card p-6 rounded-xl border shadow-sm">
                            <div className="flex flex-col gap-0.5">
                                <h2 className="text-lg font-bold">{t("library.manageTitle", "Knowledge Management")}</h2>
                                <p className="text-muted-foreground text-xs">{t("library.manageSubtitle", "Upload documents, project reports, and visual assets for global retrieval.")}</p>
                            </div>
                            <div className="flex gap-2 mt-4 md:mt-0">
                                <input
                                    type="file"
                                    className="hidden"
                                    ref={fileInputRef}
                                    onChange={handleFileUpload}
                                    accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.mp3,.wav,.mp4"
                                />
                                <Button
                                    onClick={() => fileInputRef.current?.click()}
                                    size="sm"
                                    className="gap-2 h-9 px-4 font-semibold rounded-lg shadow-sm"
                                    disabled={uploadMutation.isPending}
                                >
                                    {uploadMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                                    {t("library.uploadFile", "Upload Asset")}
                                </Button>
                                <Button
                                    variant="outline"
                                    size="icon"
                                    onClick={() => refreshFiles()}
                                    className="h-9 w-9 rounded-lg hover:bg-muted"
                                    title={t("common.refresh", "Refresh")}
                                >
                                    <RefreshCw className={`h-4 w-4 text-muted-foreground ${isLoadingFiles ? 'animate-spin' : ''}`} />
                                </Button>
                            </div>
                        </div>

                        {/* Assets Table */}
                        <Card className="border shadow-sm bg-card rounded-xl overflow-hidden">
                            <Table>
                                <TableHeader className="bg-muted/30">
                                    <TableRow className="border-b transition-none">
                                        <TableHead className="font-semibold text-xs py-3 pl-6">{t("library.fileName", "Asset Name")}</TableHead>
                                        <TableHead className="font-semibold text-xs">{t("library.fileStatus", "Indexing Status")}</TableHead>
                                        <TableHead className="font-semibold text-xs">{t("library.fileDate", "Added On")}</TableHead>
                                        <TableHead className="text-right pr-6 font-semibold text-xs">{t("common.actions", "Actions")}</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {isLoadingFiles ? (
                                        Array(4).fill(0).map((_, i) => (
                                            <TableRow key={i} className="border-b h-16 animate-pulse">
                                                <TableCell colSpan={4} className="py-4">
                                                    <div className="flex items-center justify-center gap-3 opacity-20">
                                                        <div className="h-4 w-4 bg-muted rounded" />
                                                        <div className="h-3 w-40 bg-muted rounded" />
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    ) : libraryFiles?.length === 0 ? (
                                        <TableRow className="hover:bg-transparent">
                                            <TableCell colSpan={4} className="py-20 text-center">
                                                <div className="flex flex-col items-center opacity-30">
                                                    <File className="h-10 w-10 mb-2" />
                                                    <p className="text-sm font-medium">{t("library.noFiles", "No assets uploaded yet.")}</p>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        libraryFiles?.map((file) => (
                                            <TableRow key={file.id} className="border-b hover:bg-muted/20 transition-colors group h-16">
                                                <TableCell className="pl-6">
                                                    <div className="flex items-center gap-3 text-sm">
                                                        <FileText className="h-5 w-5 text-primary/40 group-hover:text-primary transition-colors" />
                                                        <div className="flex flex-col">
                                                            <span className="font-medium">{file.name}</span>
                                                            <span className="text-[10px] text-muted-foreground font-mono opacity-50 uppercase tracking-tighter">ID: {file.checksum.slice(0, 8)}</span>
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="secondary" className="bg-green-500/10 text-green-600 hover:bg-green-500/10 border-none px-2 py-0.5 rounded-md text-[10px] font-bold">
                                                        {t("library.indexed", "SYNCED")}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-xs font-medium">
                                                    {new Date(file.last_indexed_at).toLocaleDateString()}
                                                </TableCell>
                                                <TableCell className="text-right pr-6">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded-md"
                                                        onClick={() => deleteMutation.mutate(file.id)}
                                                        disabled={deleteMutation.isPending}
                                                    >
                                                        {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </Card>
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    )
}
