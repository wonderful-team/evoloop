import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BookOpen,
  FileText,
  Folder,
  Hash,
  Search,
  TrendingUp,
  Upload,
  X,
} from "lucide-react"
import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { KnowledgeBaseAPI } from "@/services/knowledgeService"
import { DocumentList } from "./DocumentList"
import { DocumentUploadDialog } from "./DocumentUploadDialog"
import { DocumentViewer } from "./DocumentViewer"
import { PopularDocuments } from "./PopularDocuments"
import type { DocumentInfo } from "./types"

export function KnowledgeBasePage() {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedCollection, setSelectedCollection] = useState<string | null>(
    null,
  )
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [selectedDocument, setSelectedDocument] = useState<DocumentInfo | null>(
    null,
  )
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [activeTab, setActiveTab] = useState("all")
  const queryClient = useQueryClient()
  const [newCollectionName, setNewCollectionName] = useState("")
  const [isCreatingCollection, setIsCreatingCollection] = useState(false)

  // Fetch collections and documents
  const { data: collectionsData } = useQuery({
    queryKey: ["knowledge-collections"],
    queryFn: () => KnowledgeBaseAPI.getCollections(),
  })

  // Fetch tags
  const { data: tagsData, isLoading: isLoadingTags } = useQuery({
    queryKey: ["knowledge-tags", selectedCollection],
    queryFn: () => KnowledgeBaseAPI.listTags(selectedCollection || undefined),
  })

  // Fetch documents with tag filter
  const { data: documentsData, isLoading: isLoadingDocs } = useQuery({
    queryKey: ["knowledge-documents", selectedCollection],
    queryFn: () =>
      KnowledgeBaseAPI.listDocuments(selectedCollection || undefined),
  })

  // FTS Search
  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: [
      "knowledge-fts-search",
      searchQuery,
      selectedCollection,
      selectedTags,
    ],
    queryFn: () =>
      KnowledgeBaseAPI.ftsSearch(searchQuery, {
        collection: selectedCollection || undefined,
        tags: selectedTags.length > 0 ? selectedTags : undefined,
      }),
    enabled: searchQuery.length > 0,
  })

  const collections = collectionsData?.collections || []
  const documents = documentsData?.documents || []
  const stats = collectionsData?.stats
  const tags = tagsData?.tags || []

  // Toggle tag selection
  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }, [])

  // Clear all filters
  const clearFilters = useCallback(() => {
    setSelectedTags([])
    setSelectedCollection(null)
    setSearchQuery("")
  }, [])

  // Transform search results to DocumentInfo format
  const searchDocuments: DocumentInfo[] =
    searchResults?.results.map((r) => ({
      path: r.path,
      title: r.title,
      size_bytes: 0,
      modified_at: new Date().toISOString(),
      has_metadata: true,
      collection: r.collection ?? undefined,
    })) || []

  // Filter documents by search if no FTS results
  const filteredDocuments =
    searchQuery && !searchResults
      ? documents.filter(
          (d) =>
            d.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
            d.title?.toLowerCase().includes(searchQuery.toLowerCase()),
        )
      : documents

  const displayDocuments = searchResults ? searchDocuments : filteredDocuments

  // Check if any filter is active
  const hasActiveFilters =
    selectedCollection !== null ||
    selectedTags.length > 0 ||
    searchQuery.length > 0

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
              <Badge
                variant="secondary"
                className="absolute right-2 top-1/2 -translate-y-1/2"
              >
                {searchResults.total} {t("knowledge.results")}
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
              <strong>{stats.total_documents}</strong>{" "}
              {t("knowledge.documents")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Folder className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <strong>{collections.length}</strong> {t("knowledge.collections")}
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
              {t("knowledge.totalSize")}:{" "}
              {(stats.total_size_bytes / 1024 / 1024).toFixed(2)} MB
            </span>
          </div>
        </div>
      )}

      {/* Active Filters Bar */}
      {hasActiveFilters && (
        <div className="flex items-center gap-2 border-b bg-muted/30 px-6 py-2">
          <span className="text-sm text-muted-foreground">
            {t("knowledge.filters")}:
          </span>
          {selectedCollection && (
            <Badge variant="secondary" className="gap-1">
              <Folder className="h-3 w-3" />
              {selectedCollection}
              <button
                type="button"
                onClick={() => setSelectedCollection(null)}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {selectedTags.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1">
              <Hash className="h-3 w-3" />
              {tag}
              <button
                type="button"
                onClick={() => toggleTag(tag)}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {searchQuery && (
            <Badge variant="secondary" className="gap-1">
              <Search className="h-3 w-3" />
              {searchQuery}
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            className="h-6 text-xs"
          >
            {t("knowledge.clearFilters")}
          </Button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar - Collections & Tags */}
        <div className="w-64 border-r bg-muted/30 overflow-auto">
          {/* Collections Section */}
          <div className="p-4 border-b">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              {t("knowledge.collections")}
            </h3>
            <button
              type="button"
              onClick={() => setSelectedCollection(null)}
              className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                selectedCollection === null
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
            >
              {t("knowledge.allProjects")}
            </button>
            {collections.map((collection) => (
              <button
                type="button"
                key={collection}
                onClick={() => setSelectedCollection(collection)}
                className={`mt-1 w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  selectedCollection === collection
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
              >
                {collection}
              </button>
            ))}
            {/* Create Collection */}
            {isCreatingCollection ? (
              <div className="mt-2 flex gap-2">
                <Input
                  value={newCollectionName}
                  onChange={(e) => setNewCollectionName(e.target.value)}
                  placeholder={t("knowledge.newCollectionPlaceholder")}
                  className="h-8 text-sm"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newCollectionName.trim()) {
                      KnowledgeBaseAPI.createCollection(
                        newCollectionName.trim(),
                      ).then(() => {
                        setNewCollectionName("")
                        setIsCreatingCollection(false)
                        queryClient.invalidateQueries({
                          queryKey: ["knowledge-collections"],
                        })
                        queryClient.invalidateQueries({
                          queryKey: ["knowledge-documents"],
                        })
                      })
                    }
                  }}
                />
                <Button
                  size="sm"
                  className="h-8 px-2"
                  onClick={() => {
                    if (newCollectionName.trim()) {
                      KnowledgeBaseAPI.createCollection(
                        newCollectionName.trim(),
                      ).then(() => {
                        setNewCollectionName("")
                        setIsCreatingCollection(false)
                        queryClient.invalidateQueries({
                          queryKey: ["knowledge-collections"],
                        })
                        queryClient.invalidateQueries({
                          queryKey: ["knowledge-documents"],
                        })
                      })
                    }
                  }}
                >
                  +
                </Button>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2 w-full justify-start text-muted-foreground"
                onClick={() => setIsCreatingCollection(true)}
              >
                {t("knowledge.createCollection")}
              </Button>
            )}
          </div>

          {/* Tags Section */}
          <div className="p-4">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              {t("knowledge.tags")}
            </h3>
            {isLoadingTags ? (
              <div className="text-sm text-muted-foreground">
                {t("common.loading")}
              </div>
            ) : tags.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                {t("knowledge.noTags")}
              </div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {tags.map(({ name, count }) => (
                  <button
                    type="button"
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
              onClose={() => setSelectedDocument(null)}
              onSelect={setSelectedDocument}
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
        collections={collections}
      />
    </div>
  )
}
