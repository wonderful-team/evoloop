import { useQuery } from "@tanstack/react-query"
import { TrendingUp, FileText, Eye } from "lucide-react"
import { KnowledgeService } from "@/services/knowledgeService"
import { Skeleton } from "@evoloop/shared/components/ui/skeleton"
import { Badge } from "@evoloop/shared/components/ui/badge"
import type { DocumentInfo } from "./types"

interface PopularDocumentsProps {
  onSelect: (doc: DocumentInfo) => void
}

export function PopularDocuments({ onSelect }: PopularDocumentsProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["knowledge-popular"],
    queryFn: () => KnowledgeService.getPopularDocuments({ days: 30, limit: 20 }),
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-muted-foreground">
        <TrendingUp className="mb-4 h-12 w-12 opacity-20" />
        <p>暂无热门文档</p>
        <p className="text-sm">使用知识库后，这里会显示最常用的文档</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground mb-4">
        基于引用次数排序 (最近 30 天)
      </p>
      
      {data.map((doc, index) => (
        <button
          key={doc.path}
          onClick={() => onSelect({
            path: doc.path,
            title: doc.path.split("/").pop(),
            size_bytes: 0,
            modified_at: doc.last_accessed || new Date().toISOString(),
            has_metadata: true,
          })}
          className="w-full flex items-center justify-between rounded-lg border p-3 text-left transition-colors hover:bg-muted/50"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-medium">
              {index + 1}
            </div>
            <FileText className="h-5 w-5 text-gray-500" />
            <div>
              <p className="font-medium text-sm">{doc.path.split("/").pop()}</p>
              <p className="text-xs text-muted-foreground">{doc.path}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="flex items-center gap-1">
              <Eye className="h-3 w-3" />
              {doc.citations}
            </Badge>
          </div>
        </button>
      ))}
    </div>
  )
}
