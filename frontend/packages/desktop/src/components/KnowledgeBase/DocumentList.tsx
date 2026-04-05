import { useState } from "react"
import { FileText, MoreVertical, Trash2, Eye, FileCode, FileImage, File, Hash, Sparkles } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useQueryClient, useMutation } from "@tanstack/react-query"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Button } from "@evoloop/shared/components/ui/button"
import { Skeleton } from "@evoloop/shared/components/ui/skeleton"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { KnowledgeService } from "@/services/knowledgeService"
import type { DocumentInfo } from "./types"

interface DocumentListProps {
  documents: DocumentInfo[]
  isLoading: boolean
  onSelect: (doc: DocumentInfo) => void
  searchQuery?: string
  selectedTags?: string[]
  onTagClick?: (tag: string) => void
}

export function DocumentList({ documents, isLoading, onSelect, searchQuery, selectedTags = [], onTagClick }: DocumentListProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (path: string) => KnowledgeService.deleteDocument(path),
    onSuccess: () => {
      toast.success(t("knowledge.deleteSuccess", "文档已删除"))
      queryClient.invalidateQueries({ queryKey: ["knowledge-documents"] })
    },
    onError: () => {
      toast.error(t("knowledge.deleteError", "删除失败"))
    },
  })

  const getFileIcon = (path: string) => {
    const ext = path.split(".").pop()?.toLowerCase()
    if (["py", "js", "ts", "java", "go", "rs", "cpp", "c"].includes(ext || "")) {
      return <FileCode className="h-5 w-5 text-blue-500" />
    }
    if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext || "")) {
      return <FileImage className="h-5 w-5 text-purple-500" />
    }
    return <FileText className="h-5 w-5 text-gray-500" />
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString()
    } catch {
      return dateStr
    }
  }

  // Highlight search terms in text
  const highlightText = (text: string, query?: string) => {
    if (!query) return text
    const parts = text.split(new RegExp(`(${query})`, 'gi'))
    return parts.map((part, i) => 
      part.toLowerCase() === query.toLowerCase() ? 
        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">{part}</mark> : part
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-muted-foreground">
        <File className="mb-4 h-12 w-12 opacity-20" />
        <p>{t("knowledge.noDocuments", "暂无文档")}</p>
        <p className="text-sm">{t("knowledge.uploadPrompt", "点击右上角上传按钮添加文档")}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.path}
          className="group flex items-start justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50"
        >
          <button
            onClick={() => onSelect(doc)}
            className="flex flex-1 items-start gap-3 text-left"
          >
            {getFileIcon(doc.path)}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {highlightText(doc.title || doc.path.split("/").pop() || "", searchQuery)}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {doc.path} • {formatSize(doc.size_bytes)} • {formatDate(doc.modified_at)}
              </p>
              
              {/* Tags */}
              {doc.tags && doc.tags.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {doc.tags.slice(0, 3).map((tag) => (
                    <button
                      key={tag}
                      onClick={(e) => {
                        e.stopPropagation()
                        onTagClick?.(tag)
                      }}
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs transition-colors ${
                        selectedTags?.includes(tag)
                          ? "bg-primary text-primary-foreground"
                          : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                      }`}
                    >
                      <Hash className="mr-0.5 h-2.5 w-2.5" />
                      {tag}
                    </button>
                  ))}
                  {doc.tags.length > 3 && (
                    <span className="text-xs text-muted-foreground">+{doc.tags.length - 3}</span>
                  )}
                </div>
              )}
              
              {/* Auto-tagged indicator */}
              {doc.tags && doc.tags.length > 0 && (
                <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Sparkles className="h-2.5 w-2.5" />
                  自动标签
                </div>
              )}
            </div>
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect(doc)}>
                <Eye className="mr-2 h-4 w-4" />
                {t("knowledge.view", "查看")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => deleteMutation.mutate(doc.path)} className="text-destructive">
                <Trash2 className="mr-2 h-4 w-4" />
                {t("knowledge.delete", "删除")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ))}
    </div>
  )
}
