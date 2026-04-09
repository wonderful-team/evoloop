import { useState } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { FileText } from "lucide-react"
import { useChatStore } from "@/stores/chatStore"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { UploadButton } from "@/components/Projects/Requirements/UploadButton"
import { DocumentList } from "@/components/Projects/Requirements/DocumentList"
import { DocumentDetailDrawer } from "@/components/Projects/Requirements/DocumentDetailDrawer"
import { useRequirementStore } from "@/stores/requirementStore"

export const Route = createFileRoute("/_layout/projects/$projectId/requirements")({
  component: ProjectRequirementsPage,
})

function ProjectRequirementsPage() {
  const { projectId } = Route.useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isUploading, uploadDocument } = useRequirementStore()
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [isDrawerOpen, setIsDrawerOpen] = useState(false)

  const handleUpload = async (file: File) => {
    const threadId = await uploadDocument(Number(projectId), file)
    if (threadId) {
      // Set thread in store first, then navigate
      await useChatStore.getState().setThread(threadId, Number(projectId))
      navigate({ to: "/chat" })
    }
  }

  const handleViewDetail = (docId: string) => {
    setSelectedDocId(docId)
    setIsDrawerOpen(true)
  }

  return (
    <div className="h-full p-6 overflow-auto">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="h-6 w-6" />
              {t("projects.requirements.title")}
            </h1>
            <p className="text-muted-foreground">
              {t("projects.requirements.subtitle")}
            </p>
          </div>
        </div>

        {/* Upload Section */}
        <UploadButton onUpload={handleUpload} isUploading={isUploading} />

        {/* Documents List */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              {t("requirements.list.title")}
            </CardTitle>
            <CardDescription>
              {t("requirements.list.description")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DocumentList
              projectId={Number(projectId)}
              onViewDetail={handleViewDetail}
            />
          </CardContent>
        </Card>
      </div>

      {/* Document Detail Drawer */}
      <DocumentDetailDrawer
        projectId={Number(projectId)}
        docId={selectedDocId}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  )
}
