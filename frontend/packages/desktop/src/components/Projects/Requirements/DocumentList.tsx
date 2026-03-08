import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { FileText, Trash2, Loader2, AlertCircle } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Skeleton } from "@evoloop/shared/components/ui/skeleton"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@evoloop/shared/components/ui/alert-dialog"
import { useRequirementStore } from "@/stores/requirementStore"
import { cn } from "@evoloop/shared/lib/utils"

interface DocumentListProps {
  projectId: number
  onViewDetail?: (docId: string) => void
}

export function DocumentList({ projectId, onViewDetail }: DocumentListProps) {
  const { t } = useTranslation()
  const {
    documents,
    isLoading,
    fetchDocuments,
    deleteDocument,
    formatFileSize,
    getStatusColor,
  } = useRequirementStore()

  useEffect(() => {
    fetchDocuments(projectId)
  }, [projectId, fetchDocuments])

  const handleDelete = async (docId: string) => {
    await deleteDocument(projectId, docId)
  }

  const formatDate = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleDateString()
  }

  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      pending: t("requirements.status.pending"),
      analyzed: t("requirements.status.analyzed"),
      confirmed: t("requirements.status.confirmed"),
      breakdown_completed: t("requirements.status.breakdown_completed"),
    }
    return statusMap[status] || status
  }

  const getFileIconColor = (fileType: string) => {
    if (fileType.includes("pdf")) return "text-red-500"
    if (fileType.includes("word") || fileType.includes("doc"))
      return "text-blue-500"
    if (fileType.includes("excel") || fileType.includes("sheet"))
      return "text-green-500"
    if (fileType.includes("markdown") || fileType.includes("text"))
      return "text-gray-500"
    return "text-primary"
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-3 w-1/4" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-12 text-center">
          <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground/30" />
          <h3 className="text-sm font-medium text-muted-foreground mb-1">
            {t("requirements.list.empty")}
          </h3>
          <p className="text-xs text-muted-foreground/70">
            {t("requirements.list.emptyDesc")}
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <ScrollArea className="h-[calc(100vh-300px)]">
      <div className="space-y-3 pr-4">
        {documents.map((doc) => (
          <Card
            key={doc.id}
            className={cn(
              "hover:border-primary/50 transition-colors cursor-pointer",
              onViewDetail && "hover:bg-muted/50"
            )}
            onClick={() => onViewDetail?.(doc.id)}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div
                    className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 bg-muted",
                      getFileIconColor(doc.file_type)
                    )}
                  >
                    <FileText className="h-5 w-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-medium text-sm truncate">
                        {doc.file_name}
                      </h4>
                      <Badge
                        variant="secondary"
                        className={cn("text-xs", getStatusColor(doc.status))}
                      >
                        {getStatusText(doc.status)}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{formatFileSize(doc.file_size)}</span>
                      <span>•</span>
                      <span>{formatDate(doc.created_at)}</span>
                      {doc.analysis_count > 0 && (
                        <>
                          <span>•</span>
                          <span>
                            {t("requirements.list.analysisCount", { count: doc.analysis_count })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {doc.status === "pending" && (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}

                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle className="flex items-center gap-2">
                          <AlertCircle className="h-5 w-5 text-destructive" />
                          {t("requirements.list.deleteTitle")}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("requirements.list.deleteConfirm", { file: doc.file_name })}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          {t("common.cancel")}
                        </AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => handleDelete(doc.id)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {t("common.delete")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  )
}
