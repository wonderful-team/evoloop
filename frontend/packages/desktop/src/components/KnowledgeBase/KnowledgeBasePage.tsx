import { useState, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, Upload, Folder, Search, FileText, TrendingUp, Hash, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { KnowledgeService } from "@/services/knowledgeService"
import { DocumentList } from "./DocumentList"
import { DocumentUploadDialog } from "./DocumentUploadDialog"
import { DocumentViewer } from "./DocumentViewer"
import { PopularDocuments } from "./PopularDocuments"
import type { DocumentInfo } from "./types"

export function KnowledgeBasePage() {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedProject, setSelectedProject] = useState<string | null>(null)
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [selectedDocument, setSelectedDocument] = useState<DocumentInfo | null>(null)
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [activeTab, setActiveTab] = useState("all")

  // Fetch projects and documents
  const { data: projectsData, isLoading: isLoadingProjects } = useQuery({
    queryKey: ["knowledge-projects"],
    queryFn: () => KnowledgeService.getProjects(),
  })

  // Fetch tags
  const { data: tagsData, isLoading: isLoadingTags } = useQuery({
    queryKey: ["knowledge-tags", selectedProject],
    queryFn: () => KnowledgeService.listTags(selectedProject || undefined),
  })

  // Fetch documents with tag filter
  const { data: documentsData, isLoading: isLoadingDocs } = useQuery({
    queryKey: ["knowledge-documents", selectedProject, selectedTags],
    queryFn: () => KnowledgeService.listDocuments(
      selectedProject || undefined,
      selectedTags.length > 0 ? selectedTags : undefined
    ),
  })

  // FTS Search
  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ["knowledge-fts-search", searchQuery, selectedProject, selectedTags],
    queryFn: () => KnowledgeService.ftsSearch(searchQuery, { 
      project: selectedProject || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined
    }),
    enabled: searchQuery.length > 0,
  })

  const projects = projectsData?.projects || []
  const documents = documentsData?.documents || []
  const stats = projectsData?.stats
  const tags = tagsData?.tags || []

  // Toggle tag selection
  const toggleTag = useCallback((tag: string) => {
    setSelectedTags(prev => 
      prev.includes(tag) 
        ? prev.filter(t => t !== tag)
        : [...prev, tag]
    )
  }, [])

  // Clear all filters
  const clearFilters = useCallback(() => {
    setSelectedTags([])
    setSelectedProject(null)
    setSearchQuery("")
  }, [])

  // Transform search results to DocumentInfo format
  const searchDocuments: DocumentInfo[] = searchResults?.results.map(r => ({
    path: r.path,
    title: r.title,
    size_bytes: 0,
    modified_at: new Date().toISOString(),
    has_metadata: true,
    project: r.project,
  })) || []

  // Filter documents by search if no FTS results
  const filteredDocuments = searchQuery && !searchResults
    ? documents.filter(d => 
        d.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.title?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : documents

  const displayDocuments = searchResults ? searchDocuments : filteredDocuments

  // Check if any filter is active
  const hasActiveFilters = selectedProject !== null || selectedTags.length > 0 || searchQuery.length > 0

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-xl font-semibold">{t("knowledge.title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("knowledge.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t("knowledge.search")}
              className="w-80 pl-9"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchResults && (
              <Badge variant="secondary" className="absolute right-2 top-1/2 -translate-y-1/2">
                {searchResults.total} 结果
              </Badge>
            )}
          </div>
          <Button onClick={() => setIsUploadOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            {t("knowledge.upload")}
          </Button>
        </div>
      </div>

      {/* Stats & Active Filters */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 border-b bg-muted/50 px-6 py-3">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <strong>{stats.total_documents}</strong> {t("knowledge.documents")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Folder className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <strong>{projects.length}</strong> {t("knowledge.projects")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <strong>{tags.length}</strong> {t("knowledge.tags")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t("knowledge.totalSize")}: {(stats.total_size_bytes / 1024 / 1024).toFixed(2)} MB
            </span>
          </div>
        </div>
      )}

      {/* Active Filters Bar */}
      {hasActiveFilters && (
        <div className="flex items-center gap-2 border-b bg-muted/30 px-6 py-2">
          <span className="text-sm text-muted-foreground">{t("knowledge.filters")}:</span>
          {selectedProject && (
            <Badge variant="secondary" className="gap-1">
              <Folder className="h-3 w-3" />
              {selectedProject}
              <button onClick={() => setSelectedProject(null)} className="ml-1 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {selectedTags.map(tag => (
            <Badge key={tag} variant="secondary" className="gap-1">
              <Hash className="h-3 w-3" />
              {tag}
              <button onClick={() => toggleTag(tag)} className="ml-1 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {searchQuery && (
            <Badge variant="secondary" className="gap-1">
              <Search className="h-3 w-3" />
              {searchQuery}
              <button onClick={() => setSearchQuery("")} className="ml-1 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          <Button variant="ghost" size="sm" onClick={clearFilters} className="h-6 text-xs">
            {t("knowledge.clearFilters")}
          </Button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar - Projects & Tags */}
        <div className="w-64 border-r bg-muted/30 overflow-auto">
          {/* Projects Section */}
          <div className="p-4 border-b">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              {t("knowledge.projects")}
            </h3>
            <button
              onClick={() => setSelectedProject(null)}
              className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                selectedProject === null ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
            >
              {t("knowledge.allProjects")}
            </button>
            {projects.map((project) => (
              <button
                key={project}
                onClick={() => setSelectedProject(project)}
                className={`mt-1 w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  selectedProject === project ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                }`}
              >
                {project}
              </button>
            ))}
          </div>

          {/* Tags Section */}
          <div className="p-4">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              {t("knowledge.tags")}
            </h3>
            {isLoadingTags ? (
              <div className="text-sm text-muted-foreground">{t("common.loading")}</div>
            ) : tags.length === 0 ? (
              <div className="text-sm text-muted-foreground">{t("knowledge.noTags")}</div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {tags.map(({ name, count }) => (
                  <button
                    key={name}
                    onClick={() => toggleTag(name)}
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs transition-colors ${
                      selectedTags.includes(name)
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted hover:bg-muted/80 text-muted-foreground"
                    }`}
                  >
                    <Hash className="h-3 w-3" />
                    {name}
                    <span className="opacity-60">({count})</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Document List */}
        <div className="flex-1 overflow-auto p-6">
          {selectedDocument ? (
            <DocumentViewer
              document={selectedDocument}
              onBack={() => setSelectedDocument(null)}
            />
          ) : (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="mb-4">
                <TabsTrigger value="all">
                  {t("knowledge.allDocuments")}
                </TabsTrigger>
                <TabsTrigger value="popular">
                  <TrendingUp className="mr-1 h-4 w-4" />
                  {t("knowledge.popular")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="all">
                <DocumentList
                  documents={displayDocuments}
                  isLoading={isLoadingDocs || isSearching}
                  onSelect={setSelectedDocument}
                  searchQuery={searchQuery}
                  selectedTags={selectedTags}
                  onTagClick={toggleTag}
                />
              </TabsContent>

              <TabsContent value="popular">
                <PopularDocuments onSelect={setSelectedDocument} />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>

      <DocumentUploadDialog
        open={isUploadOpen}
        onOpenChange={setIsUploadOpen}
        currentProject={selectedProject || undefined}
      />
    </div>
  )
}
