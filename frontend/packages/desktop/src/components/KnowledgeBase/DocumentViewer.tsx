import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { X, ChevronLeft, ChevronRight, FileText, TrendingUp, Link2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Skeleton } from "@evoloop/shared/components/ui/skeleton"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { KnowledgeService } from "@/services/knowledgeService"
import type { DocumentInfo } from "./types"

interface DocumentViewerProps {
  document: DocumentInfo
  onClose: () => void
  onSelect?: (doc: DocumentInfo) => void
}

const LINES_PER_PAGE = 100

export function DocumentViewer({ document, onClose, onSelect }: DocumentViewerProps) {
  const { t } = useTranslation()
  const [offset, setOffset] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ["knowledge-document", document.path, offset],
    queryFn: () =>
      KnowledgeService.getDocument(document.path, offset, LINES_PER_PAGE),
  })

  // Fetch document stats
  const { data: stats } = useQuery({
    queryKey: ["knowledge-document-stats", document.path],
    queryFn: () => KnowledgeService.getDocumentStats(document.path),
    enabled: !!document.path,
  })

  // Fetch recommendations
  const { data: recommendations } = useQuery({
    queryKey: ["knowledge-recommendations", document.path],
    queryFn: () => KnowledgeService.getRecommendations(document.path),
    enabled: !!document.path,
  })

  const totalLines = data?.total_lines || 0
  const hasMore = data?.has_more || false
  const currentPage = Math.floor(offset / LINES_PER_PAGE) + 1
  const totalPages = Math.ceil(totalLines / LINES_PER_PAGE)

  const handlePrevPage = () => {
    if (offset >= LINES_PER_PAGE) {
      setOffset(offset - LINES_PER_PAGE)
    }
  }

  const handleNextPage = () => {
    if (hasMore) {
      setOffset(offset + LINES_PER_PAGE)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-5 w-5 flex-shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <h3 className="truncate font-medium">
              {document.title || document.path.split("/").pop()}
            </h3>
            <p className="text-xs text-muted-foreground">
              {totalLines} {t("knowledge.lines")}
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Document Stats */}
      {stats?.found && (
        <div className="border-b px-4 py-2 bg-muted/30">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <TrendingUp className="h-3 w-3" />
              {t("knowledge.status.citations", { count: stats.total_citations })}
            </span>
            {stats.unique_sessions > 0 && (
              <span>{t("knowledge.status.sessions", { count: stats.unique_sessions })}</span>
            )}
            {stats.last_accessed && (
              <span>{t("knowledge.status.lastAccessed", { date: new Date(stats.last_accessed).toLocaleDateString() })}</span>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 20 }).map((_, i) => (
                <Skeleton key={i} className="h-4 w-full" />
              ))}
            </div>
          ) : (
            <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
              {data?.content}
            </pre>
          )}
        </div>

        {/* Recommendations */}
        {recommendations && recommendations.recommendations.length > 0 && (
          <div className="border-t px-4 py-3">
            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
              <Link2 className="h-4 w-4" />
              {t("knowledge.relatedDocs")}
            </h4>
            <div className="space-y-1">
              {recommendations.recommendations.map((rec) => (
                <button
                  key={rec.path}
                  className="w-full text-left text-sm p-2 rounded hover:bg-muted flex items-center justify-between"
                  onClick={() => {
                    if (onSelect) {
                      onSelect({
                        path: rec.path,
                        title: rec.path.split("/").pop() || rec.path,
                        size_bytes: 0,
                        modified_at: new Date().toISOString(),
                        has_metadata: true,
                        collection: rec.collection || document.collection,
                      })
                    }
                  }}
                >
                  <span className="truncate">{rec.path}</span>
                  {rec.relevance && (
                    <Badge variant="secondary" className="text-xs">
                      {(rec.relevance * 100).toFixed(0)}%
                    </Badge>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Footer with pagination */}
      <div className="flex items-center justify-between border-t px-4 py-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={handlePrevPage}
          disabled={offset === 0}
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          {t("knowledge.prev")}
        </Button>

        <span className="text-sm text-muted-foreground">
          {currentPage} / {totalPages || 1}
        </span>

        <Button
          variant="ghost"
          size="sm"
          onClick={handleNextPage}
          disabled={!hasMore}
        >
          {t("knowledge.next")}
          <ChevronRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
