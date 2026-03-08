import { useEffect, useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { FolderOpen, X, Check, FolderX, RefreshCw } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { toast } from "sonner"
import { useProjectImportStore } from "@/stores/projectImportStore"
import { isLoggedIn } from "@/hooks/useAuth"
import { cn } from "@evoloop/shared/lib/utils"

export function DetectedProjectAlert() {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [importingIds, setImportingIds] = useState<Set<number>>(new Set())

  const {
    detectedProjects,
    hasNewDetected,
    dismissedProjectIds,
    isLoading,
    fetchDetected,
    importProject,
    ignoreProject,
    dismissProject,
    dismissAllProjects,
  } = useProjectImportStore()

  // Poll for new detected projects every 30 seconds (only when logged in)
  useEffect(() => {
    // Only check for detected projects if user is logged in
    if (!isLoggedIn()) {
      return
    }

    fetchDetected()
    const interval = setInterval(() => {
      if (isLoggedIn()) {
        fetchDetected()
      }
    }, 30000)
    return () => clearInterval(interval)
  }, [fetchDetected])

  // Show dialog when new projects detected (only when logged in)
  useEffect(() => {
    // Only show dialog if user is logged in
    if (!isLoggedIn()) {
      return
    }
    if (hasNewDetected && detectedProjects.length > 0 && !isOpen) {
      // Small delay to not interrupt user immediately
      const timer = setTimeout(() => {
        setIsOpen(true)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [hasNewDetected, detectedProjects.length, isOpen])

  // 过滤掉已处理的项目
  const visibleProjects = detectedProjects.filter((p) => !dismissedProjectIds.has(p.id))

  const handleClose = useCallback(() => {
    setIsOpen(false)
    // 将所有当前项目标记为已处理，这样稍后不会再弹出
    dismissAllProjects()
  }, [dismissAllProjects])

  const handleImport = async (id: number) => {
    setImportingIds((prev) => new Set(prev).add(id))
    try {
      await importProject(id)
      // 本地标记为已处理，立即从列表中移除
      dismissProject(id)
      toast.success(t("projects.import.importSuccess", "Project imported successfully"))

      // Close dialog if no more visible projects
      const remaining = visibleProjects.filter((p) => p.id !== id)
      if (remaining.length === 0) {
        setIsOpen(false)
      }
    } catch (error) {
      toast.error(t("projects.import.importFailed", "Failed to import project"))
    } finally {
      setImportingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleIgnore = async (id: number) => {
    try {
      await ignoreProject(id)
      // 本地标记为已处理，立即从列表中移除
      dismissProject(id)
      toast.info(t("projects.import.ignored", "Project ignored"))

      // Close dialog if no more visible projects
      const remaining = visibleProjects.filter((p) => p.id !== id)
      if (remaining.length === 0) {
        setIsOpen(false)
      }
    } catch (error) {
      toast.error(t("projects.import.ignoreFailed", "Failed to ignore project"))
    }
  }

  const handleImportAll = async () => {
    const ids = visibleProjects.map((p) => p.id)
    setImportingIds(new Set(ids))

    let successCount = 0
    let failCount = 0

    for (const id of ids) {
      try {
        await importProject(id)
        dismissProject(id)
        successCount++
      } catch {
        failCount++
      }
    }

    setImportingIds(new Set())

    if (successCount > 0) {
      toast.success(
        t("projects.import.importAllSuccess", "{{count}} projects imported", { count: successCount })
      )
    }
    if (failCount > 0) {
      toast.error(
        t("projects.import.importAllFailed", "{{count}} projects failed", { count: failCount })
      )
    }

    setIsOpen(false)
    dismissAllProjects()
  }

  // Format relative path for display
  const formatPath = (path: string) => {
    const home = "/Users" // Simplified, should use actual home detection
    if (path.startsWith(home)) {
      return "~" + path.slice(home.length)
    }
    return path
  }

  // Format detected time
  const formatTime = (timestamp: number | string) => {
    // Handle both number (timestamp) and string (ISO date) inputs
    const date = typeof timestamp === 'number' ? new Date(timestamp) : new Date(timestamp)

    // Check if date is valid
    if (isNaN(date.getTime())) {
      return t("common.time.unknown", "Unknown")
    }

    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)

    if (minutes < 1) return t("common.time.justNow", "Just now")
    if (minutes < 60) return t("common.time.minutesAgo", "{{count}}m ago", { count: minutes })
    if (hours < 24) return t("common.time.hoursAgo", "{{count}}h ago", { count: hours })
    return date.toLocaleDateString()
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="sm:max-w-[550px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-primary" />
            {t("projects.import.newProjectsDetected", "New Projects Detected")}
          </DialogTitle>
          <DialogDescription>
            {t("projects.import.detectedDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-3">
          {visibleProjects.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <RefreshCw className="h-8 w-8 mx-auto mb-2 animate-spin opacity-50" />
              <p>{t("projects.import.loading", "Loading detected projects...")}</p>
            </div>
          ) : (
            visibleProjects.map((project) => (
              <div
                key={project.id}
                className={cn(
                  "flex items-center justify-between p-3 border rounded-lg",
                  "hover:bg-muted/50 transition-colors",
                  importingIds.has(project.id) && "opacity-50"
                )}
              >
                <div className="flex-1 min-w-0 mr-4">
                  <div className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <p className="font-medium truncate">{project.name}</p>
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-1" title={project.path}>
                    {formatPath(project.path)}
                  </p>
                  <p className="text-xs text-muted-foreground/70 mt-0.5">
                    {t("projects.import.detected", "Detected")} {formatTime(project.detected_at)}
                  </p>
                </div>

                <div className="flex gap-2 flex-shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleIgnore(project.id)}
                    disabled={isLoading || importingIds.has(project.id)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <FolderX className="h-4 w-4 mr-1" />
                    {t("common.ignore", "Ignore")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleImport(project.id)}
                    disabled={isLoading || importingIds.has(project.id)}
                  >
                    {importingIds.has(project.id) ? (
                      <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                    ) : (
                      <Check className="h-4 w-4 mr-1" />
                    )}
                    {t("common.import", "Import")}
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={handleClose} className="w-full sm:w-auto">
            <X className="h-4 w-4 mr-1" />
            {t("common.later", "Later")}
          </Button>
          {visibleProjects.length > 1 && (
            <Button
              variant="secondary"
              onClick={handleImportAll}
              disabled={isLoading || importingIds.size > 0}
              className="w-full sm:w-auto"
            >
              <Check className="h-4 w-4 mr-1" />
              {t("projects.import.importAll", "Import All ({{count}})", {
                count: visibleProjects.length,
              })}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
