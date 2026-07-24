import {
  SidebarInset,
  SidebarProvider,
} from "@evoloop/shared/components/ui/sidebar"
import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AppTitleBar } from "@/components/Common/AppTitleBar"
import { SpotlightTourProvider, useTour } from "@/components/Common/SpotlightTour"
import { desktopTourSteps } from "@/components/Common/tourSteps"
import { GlobalRecorderManager } from "@/components/Learning/GlobalRecorderManager"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { SetupWizard, useSetupRequired } from "@/components/Wizard"
import { useSetupWizard } from "@/components/Wizard/SetupWizardContext"
import useAuth from "@/hooks/useAuth"
import { useSystemEvent } from "@/hooks/useSystemEvent"
import { useVoiceEvents } from "@/hooks/useVoiceEvents"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  // beforeLoad removed to allow Guest access
})

function Layout() {
  const { t } = useTranslation()
  const router = useRouterState()
  const pathname = router.location.pathname
  const { user } = useAuth()
  const { required: setupRequired, loading: setupLoading } = useSetupRequired()
  const { setIsWizardOpen } = useSetupWizard()
  const [showWizard, setShowWizard] = useState(false)
  const [hasShownWizard, setHasShownWizard] = useState(false)

  useVoiceEvents()

  const isFullWidth =
    pathname.includes("/chat") ||
    pathname.includes("/files") ||
    pathname.includes("/projects") ||
    pathname.includes("/todos") ||
    pathname.startsWith("/learning/skills") ||
    pathname.startsWith("/learning/macros")

  // Sync wizard state with context
  useEffect(() => {
    setIsWizardOpen(showWizard)
  }, [showWizard, setIsWizardOpen])

  // Show wizard when setup is required (only once per session)
  // Exclude settings page as user is already configuring manually
  useEffect(() => {
    const isSettingsPage = pathname === "/settings"
    if (
      !setupLoading &&
      setupRequired &&
      user &&
      !hasShownWizard &&
      !isSettingsPage
    ) {
      setShowWizard(true)
      setHasShownWizard(true)
    }
  }, [setupRequired, setupLoading, user, hasShownWizard, pathname])

  // Global SSE listener for project indexing status changes
  useSystemEvent("indexing.status", (event) => {
    const status = event.data?.status
    const projId = event.data?.project_id
    if (!projId) return

    if (status === "indexing") {
      toast.loading(t("globalToast.indexingStatus.loading"), {
        id: `global-indexing-${projId}`,
      })
    } else if (status === "done") {
      toast.success(t("globalToast.indexingStatus.success"), {
        id: `global-indexing-${projId}`,
      })
    } else if (status === "error" || status === "failed") {
      toast.error(t("globalToast.indexingStatus.error"), {
        id: `global-indexing-${projId}`,
      })
    }
  })

  // Global SSE listener for artifact generation status changes
  useSystemEvent("generation.status", (event) => {
    const { item, status, project_id } = event.data || {}
    if (!project_id || !item) return

    const label =
      item === "wiki"
        ? t("globalToast.generationStatus.labels.wiki")
        : item === "appmap"
          ? t("globalToast.generationStatus.labels.appmap")
          : t("globalToast.generationStatus.labels.profile")

    if (status === "running") {
      toast.loading(t("globalToast.generationStatus.loading", { label }), {
        id: `global-gen-${project_id}-${item}`,
      })
    } else if (status === "completed") {
      toast.success(t("globalToast.generationStatus.success", { label }), {
        id: `global-gen-${project_id}-${item}`,
      })
    } else if (status === "failed") {
      toast.error(t("globalToast.generationStatus.failed", { label }), {
        id: `global-gen-${project_id}-${item}`,
      })
    }
  })

  return (
    <SpotlightTourProvider
      steps={desktopTourSteps}
      preventAutoStart={setupLoading || setupRequired}
    >
      <GlobalRecorderManager />

      <SidebarProvider
        defaultOpen={false}
        className={isFullWidth ? "h-svh overflow-hidden" : ""}
      >
        <AppSidebar />
        <SidebarInset className="min-w-0 overflow-hidden flex flex-col h-full">
          <AppTitleBar />
          <main
            className={`flex-1 min-w-0 ${isFullWidth ? "overflow-hidden" : "p-6 md:p-8 overflow-auto"}`}
          >
            <div
              className={
                isFullWidth
                  ? "h-full w-full min-w-0 overflow-hidden"
                  : "mx-auto max-w-7xl min-w-0"
              }
            >
              <Outlet />
            </div>
          </main>
        </SidebarInset>
      </SidebarProvider>

      <SetupWizard open={showWizard} onOpenChange={setShowWizard} />
    </SpotlightTourProvider>
  )
}

// Export hook for settings page to replay tour
export { useTour }

export default Layout
