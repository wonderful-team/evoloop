import {Badge} from "@evoloop/shared/components/ui/badge"
import {Button} from "@evoloop/shared/components/ui/button"
import {Card, CardContent, CardHeader, CardTitle,} from "@evoloop/shared/components/ui/card"
import {Input} from "@evoloop/shared/components/ui/input"
import {Textarea} from "@evoloop/shared/components/ui/textarea"
import {createFileRoute, useParams} from "@tanstack/react-router"
import {
    AlertCircle,
    Edit,
    FileText,
    Folder,
    Globe,
    Loader2,
    RefreshCw,
    Rocket,
    Save,
    Sparkles,
    Tag,
    X,
} from "lucide-react"
import {useEffect, useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {ProjectProfilesService, ProjectsService,} from "@/client/sdk.gen"
import {MarkdownRenderer} from "@/components/Common/MarkdownRenderer"
import {ProjectAnalysisDialog} from "@/components/Projects/Modules/Overview/ProjectAnalysisDialog"
import {useProjectStore} from "@/stores/projectStore"

interface ProfileData {
  content: string | null
  exists: boolean
  name: string | null
  url: string | null
}

function ProjectProfile() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { currentProject } = useProjectStore()
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)

  // Profile state
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [editName, setEditName] = useState("")
  const [editUrl, setEditUrl] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  const [generationItems, setGenerationItems] = useState<
    Array<{ item: string; status: string }>
  >([])

  const fetchProfile = async () => {
    if (!projectId) return
    try {
      const data = await ProjectProfilesService.projectsGetProfile({
        projectId: Number(projectId),
      })
      setProfile({
        content: data.content ?? null,
        exists: data.exists ?? false,
        name: data.name ?? null,
        url: data.url ?? null,
      })
    } catch (err) {
      console.error("Failed to fetch profile", err)
      setProfile({ content: null, exists: false, name: null, url: null })
    }
  }

  useEffect(() => {
    const loadData = async () => {
      if (!projectId) return
      setLoading(true)
      try {
        await Promise.all([
          fetchProfile(),
          ProjectsService.listGenerationStatusEndpoint({
            projectId: Number(projectId),
          })
            .then((res: any) => {
              setGenerationItems(
                (res.items ?? []).filter(
                  (g: any) =>
                    g.status === "completed" ||
                    g.status === "failed" ||
                    g.status === "running",
                ),
              )
            })
            .catch(() => {}),
        ])
      } catch (err) {
        console.error("Failed to load project data", err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [projectId])

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
          <div className="p-2.5 bg-primary/10 rounded-xl text-primary shrink-0">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {currentProject?.name || t("projects.overview.title")}
            </h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              {currentProject?.description || ""}
            </p>
          </div>
          {currentProject?.indexing_status === "indexing" && (
            <Badge
              variant="secondary"
              className="bg-blue-100 text-blue-700 gap-1"
            >
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              {t("projects.status.indexing")}
            </Badge>
          )}
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

      {/* Project Info (only when profile exists or editing) */}
      {(hasProfile || isEditing) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("projects.profile.infoTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isEditing ? (
              <>
                <div className="flex items-center gap-2">
                  <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
                  <label className="text-sm font-medium w-16">
                    {t("projects.profile.projectName")}
                  </label>
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder={currentProject?.name || "my-project"}
                    className="flex-1"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                  <label className="text-sm font-medium w-16">
                    {t("projects.profile.deployUrl")}
                  </label>
                  <Input
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                    placeholder="http://localhost:8080"
                    className="flex-1 font-mono text-sm"
                  />
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 text-sm">
                  <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-16 shrink-0">
                    {t("projects.profile.projectName")}
                  </span>
                  <span className="font-medium">
                    {profile?.name || currentProject?.name || "-"}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Folder className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-16 shrink-0">
                    {t("projects.profile.projectPath")}
                  </span>
                  <code className="text-xs text-muted-foreground">
                    {currentProject?.path || "-"}
                  </code>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-16 shrink-0">
                    {t("projects.profile.deployUrl")}
                  </span>
                  <code className="text-xs">{profile?.url || "-"}</code>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Generation Artifacts */}
      {generationItems.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              {t("generation.title")}
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDiscoverOpen(true)}
            >
              {t("common.preview")}
            </Button>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {generationItems.map((g) => (
                <Badge
                  key={g.item}
                  variant={
                    g.status === "completed"
                      ? "secondary"
                      : g.status === "running"
                        ? "default"
                        : "destructive"
                  }
                >
                  {t(`generation.artifacts.${g.item}`)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* PROJECT.md */}
      {hasProfile && !isEditing && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("projects.profile.documentTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MarkdownRenderer content={profile.content!} />
          </CardContent>
        </Card>
      )}

      {/* Editing mode PROJECT.md */}
      {isEditing && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("projects.profile.documentTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea
              className="min-h-[500px] font-mono text-sm"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              placeholder={t("projects.profile.editPlaceholder")}
            />
          </CardContent>
        </Card>
      )}

      {/* Empty state when no profile and not editing */}
      {!hasProfile && !isEditing && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground border border-dashed rounded-xl bg-muted/5">
          <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
          <h3 className="text-lg font-medium">
            {t("projects.profile.notFound")}
          </h3>
          <p className="text-sm max-w-md text-center mt-2">
            {t("projects.profile.notFoundDescription")}
          </p>
          <Button className="mt-4" onClick={() => setDiscoverOpen(true)}>
            <Rocket className="h-4 w-4 mr-1" />
            {t("projects.profile.discover")}
          </Button>
        </div>
      )}

      <ProjectAnalysisDialog
        projectId={Number(projectId || 0)}
        open={discoverOpen}
        onOpenChange={setDiscoverOpen}
        onDiscovered={fetchProfile}
      />
    </div>
  )
}

export const Route = createFileRoute("/_layout/projects/$projectId/")({
  component: ProjectProfile,
})
