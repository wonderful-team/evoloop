import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Input } from "@evoloop/shared/components/ui/input"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { createFileRoute, useParams } from "@tanstack/react-router"
import {
  AlertCircle,
  Cpu,
  Edit,
  FileText,
  Globe,
  Loader2,
  RefreshCw,
  Rocket,
  Save,
  Server,
  Tag,
  X,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectProfilesService } from "@/client/sdk.gen"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import { DiscoverDialog } from "@/components/Projects/Modules/Overview/DiscoverDialog"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/profile")(
  {
    component: ProfilePage,
  },
)

interface ProfileData {
  content: string | null
  exists: boolean
  name: string | null
  url: string | null
  frameworkProfile: Record<string, unknown> | null
}

function ProfilePage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [editName, setEditName] = useState("")
  const [editUrl, setEditUrl] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  const fetchProfile = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await ProjectProfilesService.projectsGetProfile({
        projectId: Number(projectId),
      })
      setProfile({
        content: data.content ?? null,
        exists: data.exists ?? false,
        name: data.name ?? null,
        url: data.url ?? null,
        frameworkProfile: (data.framework_profile as Record<string, unknown>) ?? null,
      })
    } catch (err) {
      console.error("Failed to fetch profile", err)
      setProfile({ content: null, exists: false, name: null, url: null, frameworkProfile: null })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!projectId) return
    setIsSaving(true)
    try {
      const data = await ProjectProfilesService.projectsUpdateProfile({
        projectId: Number(projectId),
        requestBody: {
          content: editContent,
          name: editName || undefined,
          url: editUrl || undefined,
        },
      })
      setProfile({
        content: data.content ?? null,
        exists: true,
        name: data.name ?? null,
        url: data.url ?? null,
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
    setEditName(profile?.name || "")
    setEditUrl(profile?.url || "")
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
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsEditing(false)}
                disabled={isSaving}
              >
                <X className="h-4 w-4 mr-1" />
                {t("common.cancel")}
              </Button>
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Save className="h-4 w-4 mr-1" />
                )}
                {t("common.save")}
              </Button>
            </>
          )}
        </div>
      </div>

      {hasProfile || isEditing ? (
        <>
          {isEditing ? (
            <Card>
              <CardContent className="pt-6 space-y-4">
                <div className="flex items-center gap-2">
                  <Tag className="h-4 w-4 text-muted-foreground" />
                  <label className="text-sm font-medium w-20">
                    {t("projects.profile.projectName")}
                  </label>
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="my-project"
                    className="flex-1"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Globe className="h-4 w-4 text-muted-foreground" />
                  <label className="text-sm font-medium w-20">
                    {t("projects.profile.deployUrl")}
                  </label>
                  <Input
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                    placeholder="http://localhost:8080"
                    className="flex-1 font-mono text-sm"
                  />
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              {(profile?.name || profile?.url) && (
                <Card>
                  <CardContent className="pt-6 space-y-2">
                    {profile?.name && (
                      <div className="flex items-center gap-2 text-sm">
                        <Tag className="h-4 w-4 text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {t("projects.profile.projectName")}:
                        </span>
                        <span>{profile.name}</span>
                      </div>
                    )}
                    {profile?.url && (
                      <div className="flex items-center gap-2 text-sm">
                        <Globe className="h-4 w-4 text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {t("projects.profile.deployUrl")}:
                        </span>
                        <code className="text-xs">{profile.url}</code>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {profile?.frameworkProfile && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Cpu className="h-4 w-4" />
                  Framework Profile
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2 mb-3">
                  {[
                    ["language", profile.frameworkProfile.language as string],
                    ["framework", profile.frameworkProfile.framework as string],
                    ["build", profile.frameworkProfile.build_tool as string],
                    ["arch", profile.frameworkProfile.architecture as string],
                  ].filter(([, v]) => v).map(([label, val]) => (
                    <span key={label} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-secondary text-xs font-medium">
                      <Server className="h-3 w-3" />
                      {val}
                    </span>
                  ))}
                </div>
                {profile.frameworkProfile.domain_vocabulary && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-xs text-muted-foreground mr-1">词汇:</span>
                    {(profile.frameworkProfile.domain_vocabulary as string[]).map((v: string) => (
                      <span key={v} className="px-1.5 py-0.5 rounded bg-muted text-xs">{v}</span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
          </>
          )
          }

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {t("projects.profile.documentTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isEditing ? (
                <Textarea
                  className="min-h-[500px] font-mono text-sm"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  placeholder={t("projects.profile.editPlaceholder")}
                />
              ) : (
                <div>
                  <MarkdownRenderer content={profile?.content || ""} />
                </div>
              )}
            </CardContent>
          </Card>
        </>
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
