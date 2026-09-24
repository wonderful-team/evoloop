import {Button} from "@evoloop/shared/components/ui/button"
import {Textarea} from "@evoloop/shared/components/ui/textarea"
import {AlertCircle, Edit, FileText, Loader2, Save, X} from "lucide-react"
import {useEffect, useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {ProjectProfilesService} from "@/client/sdk.gen"
import {AppSheet} from "@/components/Common/AppSheet"
import {MarkdownRenderer} from "@/components/Common/MarkdownRenderer"

interface ProfileData {
  content: string | null
  exists: boolean
}

export interface ProjectProfileDrawerProps {
  projectId: number
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ProjectProfileDrawer({
  projectId,
  open,
  onOpenChange,
}: ProjectProfileDrawerProps) {
  const { t } = useTranslation()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  const fetchProfile = async () => {
    if (projectId === undefined || projectId === null || !open) return
    setLoading(true)
    try {
      const data = await ProjectProfilesService.projectsGetProfile({
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
    if (projectId === undefined || projectId === null) return
    setIsSaving(true)
    try {
      // Use SDK method
      const data = await ProjectProfilesService.projectsUpdateProfile({
        projectId: Number(projectId),
        requestBody: { content: editContent },
      })

      setProfile({
        content: data.content ?? null,
        exists: true,
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
    if (open) {
      fetchProfile()
    } else {
      setIsEditing(false)
    }
  }, [projectId, open])

  const hasProfile = profile?.exists && profile?.content

  return (
    <AppSheet
      open={open}
      onOpenChange={onOpenChange}
      title={t("projects.profile.title")}
      icon={<FileText />}
      actions={
        !isEditing && hasProfile ? (
          <Button variant="outline" size="sm" onClick={startEditing}>
            <Edit className="h-4 w-4 mr-1" />
            {t("common.edit")}
          </Button>
        ) : isEditing ? (
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
        ) : undefined
      }
    >
      <div className="flex-1 overflow-auto px-6 relative">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : hasProfile ? (
          isEditing ? (
            <Textarea
              className="min-h-full font-mono text-sm resize-none h-full"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              placeholder={t("projects.profile.editPlaceholder")}
            />
          ) : (
            <div className="pb-6 pt-4">
              <MarkdownRenderer content={profile.content!} />
            </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground h-full">
            <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
            <h3 className="text-lg font-medium">
              {t("projects.profile.notFound")}
            </h3>
            <p className="text-sm max-w-md text-center mt-2">
              {t("projects.profile.notFoundDescription")}
            </p>
          </div>
        )}
      </div>
    </AppSheet>
  )
}
