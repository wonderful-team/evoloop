import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { cn } from "@evoloop/shared/lib/utils"
import { Check, FolderOpen, FolderX, RefreshCw, X } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useSetupWizard } from "@/components/Wizard/SetupWizardContext"
import { isLoggedIn } from "@/hooks/useAuth"
import { useSystemEvent } from "@/hooks/useSystemEvent"
import { useProjectImportStore } from "@/stores/projectImportStore"

export function DetectedProjectAlert() {
  const { t } = useTranslation()
  const { shouldSuppressOtherDialogs } = useSetupWizard()
  const [isOpen, setIsOpen] = useState(false)
  const [importingIds, setImportingIds] = useState<Set<number>>(new Set())

  const {
    detectedProjects,
    hasNewDetected,
    isManualMode,
    dismissedProjectIds,
    isLoading,
    isDiscoveryEnabled,
    fetchDetected,
    importProject,
    ignoreProject,
    dismissProject,
    dismissAllAndResetManual,
    checkDiscoveryEnabled,
  } = useProjectImportStore()

  // Check discovery config on mount (only when logged in)
  useEffect(() => {
    if (isLoggedIn()) {
      checkDiscoveryEnabled()
    }
  }, [checkDiscoveryEnabled])

  // Listen for server-pushed project detection events
  useSystemEvent("project.new_detected", () => {
    if (!isLoggedIn()) return
    fetchDetected()
  })

  // Close dialog when discovery is disabled AND not in manual mode
  useEffect(() => {
    if (isDiscoveryEnabled === false && isOpen && !isManualMode) {
      setIsOpen(false)
    }
  }, [isDiscoveryEnabled, isOpen, isManualMode])

  // Show dialog when new projects detected or manual mode enabled
  useEffect(() => {
    // Don't show automatically if discovery is disabled, unless in manual mode
    if (isDiscoveryEnabled === false && !isManualMode) {
      setIsOpen(false)
      return
    }

    // Don't show if setup wizard is open
    if (shouldSuppressOtherDialogs()) {
      setIsOpen(false)
      return
    }

    // Only show dialog if user is logged in
    if (!isLoggedIn()) {
      return
    }

    // Show if there are new projects OR manual mode is active
    if (
      (hasNewDetected || isManualMode) &&
      detectedProjects.length > 0 &&
      !isOpen
    ) {
      // Small delay to not interrupt user immediately
      const timer = setTimeout(() => {
        setIsOpen(true)
      }, 100) // Shorter delay for manual mode
      return () => clearTimeout(timer)
    }
  }, [
    hasNewDetected,
    isManualMode,
    detectedProjects.length,
    isOpen,
    shouldSuppressOtherDialogs,
    isDiscoveryEnabled,
  ])

  // 过滤掉已处理的项目
  const visibleProjects = detectedProjects.filter(
    (p) => !dismissedProjectIds.has(p.id),
  )

  const handleClose = useCallback(() => {
    setIsOpen(false)
    // 一次性原子操作：标记所有项目为已处理 + 重置手动模式
    // 避免两次独立的 store set 导致中间状态触发弹窗 effect
    dismissAllAndResetManual()
  }, [dismissAllAndResetManual])

  const handleImport = async (id: number) => {
    setImportingIds((prev) => new Set(prev).add(id))
    try {
      await importProject(id)
      // 本地标记为已处理，立即从列表中移除
      dismissProject(id)
      toast.success(t("projects.import.importSuccess"))

      // Close dialog if no more visible projects
      const remaining = visibleProjects.filter((p) => p.id !== id)
      if (remaining.length === 0) {
        setIsOpen(false)
      }
    } catch (_error) {
      toast.error(t("projects.import.importFailed"))
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
      toast.info(t("projects.import.ignored"))

      // Close dialog if no more visible projects
      const remaining = visibleProjects.filter((p) => p.id !== id)
      if (remaining.length === 0) {
        setIsOpen(false)
      }
    } catch (_error) {
      toast.error(t("projects.import.ignoreFailed"))
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
        t("projects.import.importAllSuccess", "{{count}} projects imported", {
          count: successCount,
        }),
      )
    }
    if (failCount > 0) {
      toast.error(
        t("projects.import.importAllFailed", "{{count}} projects failed", {
          count: failCount,
        }),
      )
    }

    setIsOpen(false)
    dismissAllAndResetManual()
  }

  // Format relative path for display
  const formatPath = (path: string) => {
    const home = "/Users" // Simplified, should use actual home detection
    if (path.startsWith(home)) {
      return `~${path.slice(home.length)}`
    }
    return path
  }

  // Format detected time
  const formatTime = (timestamp: number | string) => {
    // Handle both number (timestamp) and string (ISO date) inputs
    const date =
      typeof timestamp === "number" ? new Date(timestamp) : new Date(timestamp)

    // Check if date is valid
    if (Number.isNaN(date.getTime())) {
      return t("common.time.unknown")
    }

    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)

    if (minutes < 1) return t("common.time.justNow")
    if (minutes < 60)
      return t("common.time.minutesAgo", "{{count}}m ago", { count: minutes })
    if (hours < 24)
      return t("common.time.hoursAgo", "{{count}}h ago", { count: hours })
    return date.toLocaleDateString()
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) {
          // 点击蒙层、按 ESC 关闭时，走完整关闭逻辑（清理 store 状态）
          handleClose()
        } else {
          setIsOpen(true)
        }
      }}
    >
      <DialogContent className="sm:max-w-[700px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-primary" />
            {t("projects.import.newProjectsDetected")}
          </DialogTitle>
          <DialogDescription>
            {t("projects.import.detectedDescription")}
          </DialogDescription>
        </DialogHeader>

        {importingIds.size > 0 && (
          <div className="py-2 px-3 bg-muted rounded-md text-sm text-center text-muted-foreground flex items-center justify-center gap-2">
            <RefreshCw className="h-4 w-4 animate-spin" />
            {t("projects.import.importing", "Importing {{count}} projects...", {
              count: importingIds.size,
            })}
          </div>
        )}

        <div className="py-4 space-y-3">
          {visibleProjects.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <RefreshCw className="h-8 w-8 mx-auto mb-2 animate-spin opacity-50" />
              <p>{t("projects.import.loading")}</p>
            </div>
          ) : (
            visibleProjects.map((project) => (
              <div
                key={project.id}
                className={cn(
                  "flex items-center justify-between p-3 border rounded-lg",
                  "hover:bg-muted/50 transition-colors",
                  importingIds.has(project.id) && "opacity-50",
                )}
              >
                <div className="flex-1 min-w-0 mr-4">
                  <div className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <p className="font-medium truncate">{project.name}</p>
                  </div>
                  <p
                    className="text-xs text-muted-foreground truncate mt-1"
                    title={project.path}
                  >
                    {formatPath(project.path)}
                  </p>
                  <p className="text-xs text-muted-foreground/70 mt-0.5">
                    {t("projects.import.detected")}{" "}
                    {formatTime(project.detected_at)}
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
                    {t("common.ignore")}
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
                    {t("common.import")}
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={importingIds.size > 0}
            className="w-full sm:w-auto"
          >
            <X className="h-4 w-4 mr-1" />
            {t("common.later")}
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
