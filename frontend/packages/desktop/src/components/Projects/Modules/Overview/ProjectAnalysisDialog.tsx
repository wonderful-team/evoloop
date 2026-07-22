import { Button } from "@evoloop/shared/components/ui/button"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { FileText, Loader2, Search, Shield, Zap } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectsService } from "@/client"
import { ProjectProfilesService } from "@/client/sdk.gen"

interface ProjectAnalysisDialogProps {
  projectId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  onDiscovered?: () => void
}

interface ArtifactItem {
  key: string
  label: string
  desc: string
  icon: any
  checked: boolean
  status: string
}

export function ProjectAnalysisDialog({
  projectId,
  open,
  onOpenChange,
  onDiscovered,
}: ProjectAnalysisDialogProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [recordSecrets, setRecordSecrets] = useState(false)
  const [items, setItems] = useState<ArtifactItem[]>([])

  const fetchStatus = async () => {
    if (!projectId || !open) return
    setLoading(true)
    try {
      const [statusRes, profileRes] = await Promise.all([
        ProjectsService.listGenerationStatusEndpoint({ projectId }).catch(() => ({ items: [] })),
        ProjectProfilesService.projectsGetProfile({ projectId }),
      ])
      const map: Record<string, string> = {}
      for (const item of (statusRes as any).items || []) {
        map[item.item] = item.status
      }
      map.overview = profileRes.exists ? "completed" : "pending"

      const allItems: ArtifactItem[] = [
        { key: "overview", label: t("generation.dialog.items.overview"), desc: t("generation.dialog.items.overviewDesc"), icon: FileText, checked: false, status: map.overview || "pending" },
        { key: "wiki", label: t("generation.dialog.items.wiki"), desc: t("generation.dialog.items.wikiDesc"), icon: FileText, checked: false, status: map.wiki || "pending" },
        { key: "appmap", label: t("generation.dialog.items.appmap"), desc: t("generation.dialog.items.appmapDesc"), icon: Zap, checked: false, status: map.appmap || "pending" },
      ]

      const hasPending = allItems.some((i) => i.status === "pending")
      if (hasPending) {
        allItems.forEach((i) => { i.checked = i.status !== "completed" })
      }

      setItems(allItems)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setRecordSecrets(false)
      setGenerating(false)
      fetchStatus()
    }
  }, [projectId, open])

  const handleToggle = (key: string) => {
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, checked: !i.checked } : i)))
  }

  const handleGenerate = async () => {
    const selected = items.filter((i) => i.checked)
    if (selected.length === 0) {
      toast.error(t("generation.dialog.selectAtLeastOne"))
      return
    }

    setGenerating(true)
    try {
      const dispatchItems = selected
        .map((i) => (i.key === "overview" ? "summary" : i.key))
        .filter((k): k is string => !!k)

      const promises: Promise<any>[] = []
      if (dispatchItems.length > 0) {
        promises.push(
          ProjectsService.dispatchGenerationEndpoint({
            projectId,
            requestBody: { project_id: projectId, items: dispatchItems },
          })
        )
      }
      if (selected.some((i) => i.key === "overview")) {
        promises.push(
          ProjectProfilesService.projectsDiscoverProfile({
            projectId,
            requestBody: { project_id: projectId, record_secrets: recordSecrets },
          })
        )
      }
      await Promise.all(promises)
      toast.success(t("generation.dialog.submitted", { count: selected.length }))
      onDiscovered?.()
      onOpenChange(false)
    } catch {
      toast.error(t("generation.dialog.submitFailed"))
    } finally {
      setGenerating(false)
    }
  }

  const statusLabel = (status: string) => {
    if (status === "completed") return t("generation.status.completed")
    if (status === "running") return t("generation.status.running")
    if (status === "failed") return t("generation.status.failed")
    return t("generation.status.pending")
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            {t("generation.dialog.title")}
          </DialogTitle>
          <DialogDescription>
            {t("generation.dialog.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {items.map((item) => (
                <div
                  key={item.key}
                  className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    item.checked ? "border-primary/50 bg-primary/5" : "hover:bg-muted/50"
                  }`}
                  onClick={() => handleToggle(item.key)}
                >
                  <Checkbox checked={item.checked} onCheckedChange={() => handleToggle(item.key)} className="mt-0.5" />
                  <item.icon className={`h-5 w-5 mt-0.5 shrink-0 ${item.checked ? "text-primary" : "text-muted-foreground"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                        item.status === "completed" ? "bg-green-100 text-green-700" :
                        item.status === "running" ? "bg-blue-100 text-blue-700" :
                        "bg-muted text-muted-foreground"
                      }`}>
                        {statusLabel(item.status)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
                  </div>
                </div>
              ))}

              <div className="flex items-start gap-3 rounded-md border p-3 bg-muted/20">
                <Checkbox
                  id="record-secrets"
                  checked={recordSecrets}
                  onCheckedChange={(checked) => setRecordSecrets(checked === true)}
                  className="mt-0.5"
                />
                <Shield className="h-5 w-5 mt-0.5 text-amber-500 shrink-0" />
                <div className="space-y-1 leading-none">
                  <label htmlFor="record-secrets" className="text-sm font-medium cursor-pointer flex items-center gap-1.5">
                    {t("generation.dialog.recordSecrets")}
                    <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{t("generation.dialog.recordSecretsWarning")}</span>
                  </label>
                  <p className="text-xs text-muted-foreground">
                    {t("generation.dialog.recordSecretsDesc")}
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={generating}>
            {t("generation.dialog.cancel")}
          </Button>
          <Button onClick={handleGenerate} disabled={loading || generating || items.every((i) => !i.checked)}>
            {generating ? (
              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
            ) : null}
            {t("generation.dialog.generate", { count: items.filter((i) => i.checked).length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
