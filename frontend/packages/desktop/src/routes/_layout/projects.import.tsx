import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "@tanstack/react-router"
import {
  ArrowLeft,
  FolderOpen,
  FolderX,
  Check,
  RotateCcw,
  RefreshCw,
  Trash2,
  ArrowUpRight,
  CheckSquare,
  Square,
  X,
} from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent } from "@evoloop/shared/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { toast } from "sonner"
import { useProjectImportStore } from "@/stores/projectImportStore"
import { cn } from "@evoloop/shared/lib/utils"

export default function ProjectImportPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState("detected")
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [isBatchMode, setIsBatchMode] = useState(false)

  const {
    detectedProjects,
    ignoredProjects,
    isLoading,
    fetchDetected,
    fetchIgnored,
    importProject,
    ignoreProject,
    unignoreProject,
    batchImportProjects,
    batchIgnoreProjects,
  } = useProjectImportStore()

  useEffect(() => {
    fetchDetected()
    fetchIgnored()
  }, [fetchDetected, fetchIgnored])

  // Clear selection when switching tabs
  useEffect(() => {
    setSelectedIds(new Set())
    setIsBatchMode(false)
  }, [activeTab])

  const handleImport = async (id: number) => {
    setProcessingIds((prev) => new Set(prev).add(id))
    try {
      await importProject(id)
      toast.success(t("projects.import.importSuccess", "Project imported successfully"))
    } catch (error) {
      toast.error(t("projects.import.importFailed", "Failed to import project"))
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleIgnore = async (id: number) => {
    setProcessingIds((prev) => new Set(prev).add(id))
    try {
      await ignoreProject(id)
      toast.info(t("projects.import.ignored", "Project ignored"))
    } catch (error) {
      toast.error(t("projects.import.ignoreFailed", "Failed to ignore project"))
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleUnignore = async (id: number) => {
    setProcessingIds((prev) => new Set(prev).add(id))
    try {
      await unignoreProject(id)
      toast.success(t("projects.import.unignored", "Project restored to detected"))
    } catch (error) {
      toast.error(t("projects.import.unignoreFailed", "Failed to restore project"))
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleSelect = (id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  const handleSelectAll = () => {
    const projects = activeTab === "detected" ? detectedProjects : ignoredProjects
    if (selectedIds.size === projects.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(projects.map((p) => p.id)))
    }
  }

  const handleBatchImport = async () => {
    if (selectedIds.size === 0) return

    try {
      const result = await batchImportProjects(Array.from(selectedIds))
      toast.success(
        t(
          "projects.import.batchImportSuccess",
          "Imported {{success}} projects, {{failed}} failed",
          { success: result.success, failed: result.failed }
        )
      )
      setSelectedIds(new Set())
      setIsBatchMode(false)
    } catch (error) {
      toast.error(t("projects.import.batchImportFailed", "Failed to batch import projects"))
    }
  }

  const handleBatchIgnore = async () => {
    if (selectedIds.size === 0) return

    try {
      const result = await batchIgnoreProjects(Array.from(selectedIds))
      toast.success(
        t(
          "projects.import.batchIgnoreSuccess",
          "Ignored {{success}} projects, {{failed}} failed",
          { success: result.success, failed: result.failed }
        )
      )
      setSelectedIds(new Set())
      setIsBatchMode(false)
    } catch (error) {
      toast.error(t("projects.import.batchIgnoreFailed", "Failed to batch ignore projects"))
    }
  }

  const formatPath = (path: string) => {
    const home = "/Users"
    if (path.startsWith(home)) {
      return "~" + path.slice(home.length)
    }
    return path
  }

  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleString()
  }

  const renderProjectCard = (
    project: { id: number; name: string; path: string; detected_at: string },
    actions: "detected" | "ignored"
  ) => (
    <Card key={project.id} className="hover:border-primary/50 transition-colors">
      <CardContent className="flex items-start justify-between py-4">
        <div className="flex items-start gap-3 flex-1 min-w-0 mr-4">
          {isBatchMode && actions === "detected" && (
            <Checkbox
              checked={selectedIds.has(project.id)}
              onCheckedChange={(checked) => handleSelect(project.id, checked as boolean)}
              className="mt-1"
            />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <FolderOpen className="h-4 w-4 text-primary flex-shrink-0" />
              <h3 className="font-semibold truncate">{project.name}</h3>
            </div>
            <p
              className="text-sm text-muted-foreground truncate mb-1"
              title={project.path}
            >
              {formatPath(project.path)}
            </p>
            <p className="text-xs text-muted-foreground/70">
              {t("projects.import.detectedAt", "Detected")}: {formatTime(project.detected_at)}
            </p>
          </div>
        </div>

        {!isBatchMode && (
          <div className="flex gap-2 flex-shrink-0">
            {actions === "detected" ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleIgnore(project.id)}
                  disabled={processingIds.has(project.id)}
                >
                  {processingIds.has(project.id) ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <FolderX className="h-4 w-4 mr-1" />
                  )}
                  {t("common.ignore", "Ignore")}
                </Button>
                <Button size="sm" onClick={() => handleImport(project.id)} disabled={processingIds.has(project.id)}>
                  {processingIds.has(project.id) ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4 mr-1" />
                  )}
                  {t("common.import", "Import")}
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleUnignore(project.id)}
                disabled={processingIds.has(project.id)}
              >
                {processingIds.has(project.id) ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4 mr-1" />
                )}
                {t("common.restore", "Restore")}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderEmptyState = (type: "detected" | "ignored") => (
    <Card className="border-dashed">
      <CardContent className="py-12 text-center">
        {type === "detected" ? (
          <>
            <FolderOpen className="h-12 w-12 mx-auto mb-4 text-muted-foreground/30" />
            <p className="text-muted-foreground font-medium">
              {t("projects.import.noDetected", "No projects waiting to be imported")}
            </p>
            <p className="text-sm text-muted-foreground/70 mt-1">
              {t(
                "projects.import.noDetectedDesc",
                "New folders in your projects directory will appear here"
              )}
            </p>
          </>
        ) : (
          <>
            <Trash2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground/30" />
            <p className="text-muted-foreground font-medium">
              {t("projects.import.noIgnored", "No ignored projects")}
            </p>
            <p className="text-sm text-muted-foreground/70 mt-1">
              {t("projects.import.noIgnoredDesc", "Ignored projects can be restored from here")}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )

  const currentProjects = activeTab === "detected" ? detectedProjects : ignoredProjects

  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link to="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold">{t("projects.import.title", "Project Import")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("projects.import.subtitle", "Manage detected and ignored projects")}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchDetected(); fetchIgnored(); }}>
            <RefreshCw className={cn("h-4 w-4 mr-1", isLoading && "animate-spin")} />
            {t("common.refresh", "Refresh")}
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="detected" className="gap-2">
            <FolderOpen className="h-4 w-4" />
            {t("projects.import.tabDetected", "To Import")}
            {detectedProjects.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-primary text-primary-foreground rounded-full">
                {detectedProjects.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="ignored" className="gap-2">
            <FolderX className="h-4 w-4" />
            {t("projects.import.tabIgnored", "Ignored")}
            {ignoredProjects.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-muted rounded-full">
                {ignoredProjects.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="detected" className="space-y-4">
          {/* Batch Mode Controls */}
          {detectedProjects.length > 0 && (
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              {!isBatchMode ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsBatchMode(true)}
                >
                  <CheckSquare className="h-4 w-4 mr-2" />
                  {t("projects.import.batchMode", "Batch Select")}
                </Button>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={selectedIds.size === detectedProjects.length && detectedProjects.length > 0}
                      onCheckedChange={handleSelectAll}
                    />
                    <span className="text-sm">
                      {t("projects.import.selectAll", "Select All")} ({selectedIds.size}/{detectedProjects.length})
                    </span>
                  </div>

                  {selectedIds.size > 0 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleBatchIgnore}
                      >
                        <FolderX className="h-4 w-4 mr-1" />
                        {t("projects.import.batchIgnore", "Ignore Selected")} ({selectedIds.size})
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleBatchImport}
                      >
                        <Check className="h-4 w-4 mr-1" />
                        {t("projects.import.batchImport", "Import Selected")} ({selectedIds.size})
                      </Button>
                    </div>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setIsBatchMode(false)
                      setSelectedIds(new Set())
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          )}

          {detectedProjects.length === 0
            ? renderEmptyState("detected")
            : detectedProjects.map((p) => renderProjectCard(p, "detected"))}
        </TabsContent>

        <TabsContent value="ignored" className="space-y-4">
          {ignoredProjects.length === 0
            ? renderEmptyState("ignored")
            : ignoredProjects.map((p) => renderProjectCard(p, "ignored"))}
        </TabsContent>
      </Tabs>

      {/* Quick link to projects */}
      <div className="mt-8 flex justify-center">
        <Link to="/projects">
          <Button variant="ghost" className="text-muted-foreground">
            {t("projects.import.backToProjects", "Back to Projects")}
            <ArrowUpRight className="h-4 w-4 ml-1" />
          </Button>
        </Link>
      </div>
    </div>
  )
}
