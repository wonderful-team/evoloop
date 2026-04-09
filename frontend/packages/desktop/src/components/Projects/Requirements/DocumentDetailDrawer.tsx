import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  FileText,
  Loader2,
  Clock,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  RefreshCw,
  Layers,
} from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { cn } from "@evoloop/shared/lib/utils"
import { useRequirementStore, type AnalysisResult } from "@/stores/requirementStore"
import { TaskVisualization } from "./TaskVisualization"

interface DocumentDetailDrawerProps {
  projectId: number
  docId: string | null
  isOpen: boolean
  onClose: () => void
}

export function DocumentDetailDrawer({
  projectId,
  docId,
  isOpen,
  onClose,
}: DocumentDetailDrawerProps) {
  const { t } = useTranslation()
  const { currentDocument, isLoadingDetail, fetchDocumentDetail, formatFileSize } =
    useRequirementStore()
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("overview")

  useEffect(() => {
    if (docId && isOpen) {
      fetchDocumentDetail(projectId, docId)
      setSelectedAnalysisId(null)
    }
  }, [docId, isOpen, projectId, fetchDocumentDetail])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock className="h-4 w-4 text-yellow-500" />
      case "analyzed":
        return <CheckCircle2 className="h-4 w-4 text-blue-500" />
      case "confirmed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case "breakdown_completed":
        return <Layers className="h-4 w-4 text-purple-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-gray-500" />
    }
  }

  const getAnalysisStatusIcon = (status: string) => {
    switch (status) {
      case "draft":
        return <Clock className="h-4 w-4 text-yellow-500" />
      case "pending_confirmation":
        return <AlertCircle className="h-4 w-4 text-orange-500" />
      case "confirmed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case "breakdown_completed":
        return <Layers className="h-4 w-4 text-purple-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: "bg-yellow-100 text-yellow-800",
      analyzed: "bg-blue-100 text-blue-800",
      confirmed: "bg-green-100 text-green-800",
      breakdown_completed: "bg-purple-100 text-purple-800",
      draft: "bg-gray-100 text-gray-800",
      pending_confirmation: "bg-orange-100 text-orange-800",
    }
    return colors[status] || "bg-gray-100 text-gray-800"
  }

  const formatDate = (dateValue: number | string | null) => {
    if (!dateValue) return "-"
    const date = new Date(dateValue)
    return date.toLocaleString()
  }

  const renderAnalysisCard = (analysis: AnalysisResult) => (
    <div
      key={analysis.id}
      className={cn(
        "p-4 border rounded-lg cursor-pointer transition-all",
        selectedAnalysisId === analysis.id
          ? "border-primary bg-primary/5"
          : "hover:border-primary/50 hover:bg-muted/50"
      )}
      onClick={() => setSelectedAnalysisId(analysis.id)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {getAnalysisStatusIcon(analysis.status)}
          <span className="font-medium">{t("requirements.analysis.version")} {analysis.version}</span>
        </div>
        <Badge className={cn("text-xs", getStatusColor(analysis.status))}>
          {analysis.status}
        </Badge>
      </div>

      <div className="mt-3 space-y-2 text-sm">
        {analysis.data.title && (
          <p className="font-medium">{analysis.data.title}</p>
        )}

        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {analysis.data.functional_requirements && (
            <span>
              {analysis.data.functional_requirements.length} {t("requirements.analysis.functionalRequirements")}
            </span>
          )}
          {analysis.data.user_stories && (
            <span>
              • {analysis.data.user_stories.length} {t("requirements.analysis.userStories")}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
          <span>{formatDate(analysis.confirmed_at || analysis.created_at)}</span>
          {analysis.user_edited && (
            <Badge variant="outline" className="text-xs">
              {t("requirements.analysis.edited")}
            </Badge>
          )}
        </div>

        {analysis.tasks_count > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <Layers className="h-3 w-3" />
            <span>
              {analysis.synced_tasks}/{analysis.tasks_count} {t("requirements.analysis.tasksSynced")}
            </span>
          </div>
        )}
      </div>
    </div>
  )

  const renderSelectedAnalysis = () => {
    if (!selectedAnalysisId || !currentDocument) return null

    const analysis = currentDocument.analyses.find((a) => a.id === selectedAnalysisId)
    if (!analysis) return null

    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setSelectedAnalysisId(null)}>
            <ChevronRight className="h-4 w-4 rotate-180" />
            {t("common.back")}
          </Button>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="overview">
              {t("requirements.detail.overview")}
            </TabsTrigger>
            <TabsTrigger value="tasks">
              {t("requirements.detail.tasks")}
              {analysis.tasks_count > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">
                  ({analysis.tasks_count})
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4 mt-4">
            {analysis.data.title && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">
                  {t("requirements.analysis.title")}
                </h4>
                <p className="text-lg font-semibold">{analysis.data.title}</p>
              </div>
            )}

            {analysis.data.summary && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">
                  {t("requirements.analysis.summary")}
                </h4>
                <p className="text-sm">{analysis.data.summary}</p>
              </div>
            )}

            {analysis.data.functional_requirements && analysis.data.functional_requirements.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  {t("requirements.analysis.functionalRequirements")}
              </h4>
              <ul className="space-y-2">
                {analysis.data.functional_requirements.map((req, idx) => (
                  <li key={idx} className="text-sm p-2 bg-muted rounded">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{req.id}</span>
                      <Badge variant="outline" className="text-xs">{req.priority}</Badge>
                    </div>
                    <p className="mt-1">{req.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.data.user_stories && analysis.data.user_stories.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-2">
                {t("requirements.analysis.userStories")}
              </h4>
              <ul className="space-y-2">
                {analysis.data.user_stories.map((story, idx) => (
                  <li key={idx} className="text-sm p-2 bg-muted rounded">
                    <span className="font-medium">{story.id}</span>
                    <p className="mt-1">
                      {t("requirements.analysis.asA")} {story.role}，
                      {t("requirements.analysis.iWant")} {story.action}，
                      {t("requirements.analysis.soThat")} {story.benefit}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.data.technical_suggestions && analysis.data.technical_suggestions.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-2">
                {t("requirements.analysis.technicalSuggestions")}
              </h4>
              <ul className="space-y-2">
                {analysis.data.technical_suggestions.map((suggestion, idx) => (
                  <li key={idx} className="text-sm p-2 bg-muted rounded">
                    <Badge variant="outline" className="mb-1">{suggestion.area}</Badge>
                    <p className="font-medium">{suggestion.suggestion}</p>
                    <p className="text-muted-foreground text-xs mt-1">{suggestion.rationale}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.data.risks && analysis.data.risks.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-2">
                {t("requirements.analysis.risks")}
              </h4>
              <ul className="space-y-2">
                {analysis.data.risks.map((risk, idx) => (
                  <li key={idx} className="text-sm p-2 bg-muted rounded">
                    <div className="flex items-center gap-2">
                      <Badge className={cn("text-xs", getStatusColor(risk.impact))}>
                        {risk.impact}
                      </Badge>
                    </div>
                    <p className="mt-1">{risk.description}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t("requirements.analysis.mitigation")}: {risk.mitigation}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          </TabsContent>

          <TabsContent value="tasks" className="mt-4">
            <TaskVisualization
              projectId={projectId}
              docId={docId || ""}
              analysisId={selectedAnalysisId}
            />
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {t("requirements.detail.title")}
          </SheetTitle>
        </SheetHeader>

        {isLoadingDetail ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !currentDocument ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            {t("requirements.detail.notFound")}
          </div>
        ) : (
          <ScrollArea className="h-[calc(100vh-8rem)] mt-6 pr-4">
            {!selectedAnalysisId ? (
              <div className="space-y-6">
                {/* Document Info */}
                <div className="space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-lg">{currentDocument.file_name}</h3>
                      <p className="text-sm text-muted-foreground">
                        {formatFileSize(currentDocument.file_size || 0)} • {formatDate(currentDocument.created_at)}
                      </p>
                    </div>
                    <Badge className={cn("text-xs", getStatusColor(currentDocument.status))}>
                      <span className="flex items-center gap-1">
                        {getStatusIcon(currentDocument.status)}
                        {currentDocument.status}
                      </span>
                    </Badge>
                  </div>

                  {currentDocument.raw_content_preview && (
                    <div className="p-3 bg-muted rounded-lg">
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">
                        {t("requirements.detail.contentPreview")}
                      </h4>
                      <p className="text-sm text-muted-foreground line-clamp-6">
                        {currentDocument.raw_content_preview}
                      </p>
                    </div>
                  )}
                </div>

                <Separator />

                {/* Analysis History */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="font-medium">
                      {t("requirements.detail.analysisHistory")}
                    </h4>
                    <span className="text-sm text-muted-foreground">
                      {currentDocument.analyses.length} {t("requirements.detail.versions")}
                    </span>
                  </div>

                  {currentDocument.analyses.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <RefreshCw className="h-8 w-8 mx-auto mb-2 opacity-30" />
                      <p>{t("requirements.detail.noAnalysis")}</p>
                      <p className="text-xs mt-1">
                        {t("requirements.detail.analysisInProgress")}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {currentDocument.analyses.map(renderAnalysisCard)}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              renderSelectedAnalysis()
            )}
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  )
}
