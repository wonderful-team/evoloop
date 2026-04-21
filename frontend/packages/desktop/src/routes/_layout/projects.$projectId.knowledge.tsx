import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Skeleton } from "@evoloop/shared/components/ui/skeleton"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { BookOpen, FileText, Search } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { KnowledgeBaseAPI } from "@/services/knowledgeService"

export const Route = createFileRoute("/_layout/projects/$projectId/knowledge")({
  component: ProjectKnowledgePage,
})

function ProjectKnowledgePage() {
  const { projectId } = Route.useParams()
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["project-knowledge", projectId],
    queryFn: () => KnowledgeBaseAPI.listDocuments(undefined, Number(projectId)),
  })

  const { data: searchData, isLoading: isSearching } = useQuery({
    queryKey: ["project-knowledge-search", projectId, searchQuery],
    queryFn: () =>
      KnowledgeBaseAPI.ftsSearch(searchQuery, {
        collection: undefined,
        tags: undefined,
      }),
    enabled: searchQuery.trim().length > 0,
  })

  const documents = data?.documents || []
  const searchResults = searchData?.results || []
  const displayDocs =
    searchQuery.trim().length > 0
      ? searchResults.map((r) => ({
          path: r.path,
          title: r.title,
          size_bytes: 0,
          modified_at: "",
          has_metadata: true,
        }))
      : documents

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BookOpen className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">
              {t("knowledge.projectDocs")}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t("knowledge.search")}
                className="w-64 pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          {t("knowledge.projectDocsDescription")}
        </p>
      </div>

      {/* Document List */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading || isSearching ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : displayDocs.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center text-muted-foreground">
            <FileText className="mb-4 h-12 w-12 opacity-20" />
            <p>
              {searchQuery.trim().length > 0
                ? t("knowledge.noSearchResults")
                : t("knowledge.noProjectDocs")}
            </p>
            <p className="text-sm">
              {searchQuery.trim().length > 0
                ? t("knowledge.noSearchResultsHint")
                : t("knowledge.noProjectDocsHint")}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {displayDocs.map((doc) => (
              <div
                key={doc.path}
                className="flex items-center justify-between rounded-lg border p-3 hover:bg-muted/50"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-gray-500" />
                  <div>
                    <p className="font-medium">{doc.title || doc.path}</p>
                    <p className="text-xs text-muted-foreground">{doc.path}</p>
                  </div>
                </div>
                <Button variant="ghost" size="sm">
                  {t("knowledge.view")}
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
