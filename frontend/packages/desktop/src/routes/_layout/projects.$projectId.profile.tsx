import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { AlertCircle, FileText, Loader2, RefreshCw, Rocket, Edit, Save, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { ProjectProfilesService } from "@/client/sdk.gen"
import { DiscoverDialog } from "@/components/Projects/Modules/Overview/DiscoverDialog"

export const Route = createFileRoute("/_layout/projects/$projectId/profile")({
  component: ProfilePage,
})

interface ProfileData {
  content: string | null
  exists: boolean
}

function ProfilePage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  const fetchProfile = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await ProjectProfilesService.getProfile({
        projectId: Number(projectId),
      })
      setProfile({
        content: data.content ?? null,
        exists: data.exists ?? false,
      })
    } catch (err) {
      console.error("Failed to fetch profile", err)
      setProfile({ content: null, exists: false })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!projectId) return
    setIsSaving(true)
    try {
      // Manual call to the new endpoint
      const response = await fetch(`${import.meta.env.VITE_API_URL || ""}/api/v1/project-profiles/${projectId}/profile`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content: editContent })
      })
      
      if (!response.ok) throw new Error("Failed to update profile")
      
      const data = await response.json()
      setProfile({
        content: data.content,
        exists: true
      })
      setIsEditing(false)
      toast.success(t("common.saveSuccess"))
    } catch (err) {
      console.error("Failed to save profile", err)
      toast.error(t("common.saveFailed"))
    } finally {
      setIsSaving(false)
    }
  }

  const startEditing = () => {
    setEditContent(profile?.content || "")
    setIsEditing(true)
  }

  useEffect(() => {
    fetchProfile()
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const hasProfile = profile?.exists && profile?.content

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <FileText className="h-6 w-6 text-primary" />
          <h2 className="text-2xl font-bold tracking-tight">
            {t("projects.profile.title")}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {!isEditing ? (
            <>
              <Button variant="outline" size="sm" onClick={startEditing}>
                <Edit className="h-4 w-4 mr-1" />
                {t("common.edit")}
              </Button>
              <Button size="sm" onClick={() => setDiscoverOpen(true)}>
                {hasProfile ? (
                  <RefreshCw className="h-4 w-4 mr-1 text-blue-500" />
                ) : (
                  <Rocket className="h-4 w-4 mr-1 text-primary" />
                )}
                {t("chat.sidebar.deploy")}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={isSaving}>
                <X className="h-4 w-4 mr-1" />
                {t("common.cancel")}
              </Button>
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
                {t("common.save")}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      {hasProfile ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              PROJECT.md
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isEditing ? (
              <Textarea
                className="min-h-[500px] font-mono text-sm"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                placeholder={t("projects.profile.editPlaceholder", "Enter project profile in Markdown...")}
              />
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    code({ node, inline, className, children, ...props }: any) {
                      const match = /language-(\w+)/.exec(className || "")
                      return !inline && match ? (
                        <SyntaxHighlighter
                          style={vscDarkPlus}
                          language={match[1]}
                          PreTag="div"
                          {...props}
                        >
                          {String(children).replace(/\n$/, "")}
                        </SyntaxHighlighter>
                      ) : (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      )
                    },
                  }}
                >
                  {profile.content!}
                </ReactMarkdown>
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
          <h3 className="text-lg font-medium">
            {t("projects.profile.notFound")}
          </h3>
          <p className="text-sm max-w-md text-center mt-2">
            {t("projects.profile.notFoundDescription")}
          </p>
          <Button className="mt-4" onClick={() => setDiscoverOpen(true)}>
            <RefreshCw className="h-4 w-4 mr-1" />
            {t("projects.profile.discover")}
          </Button>
        </div>
      )}

      <DiscoverDialog
        projectId={Number(projectId || 0)}
        open={discoverOpen}
        onOpenChange={setDiscoverOpen}
        onDiscovered={fetchProfile}
      />
    </div>
  )
}
