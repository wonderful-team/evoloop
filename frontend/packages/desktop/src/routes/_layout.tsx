import {
  SidebarInset,
  SidebarProvider,
} from "@evoloop/shared/components/ui/sidebar"
import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { Footer } from "@/components/Common/Footer"
import {
  SpotlightTourProvider,
  useTour,
} from "@/components/Common/SpotlightTour"
import { desktopTourSteps } from "@/components/Common/tourSteps"
import { GlobalRecorderManager } from "@/components/Learning/GlobalRecorderManager"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { SetupWizard, useSetupRequired } from "@/components/Wizard"
import { useSetupWizard } from "@/components/Wizard/SetupWizardContext"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  // beforeLoad removed to allow Guest access
})

function Layout() {
  const router = useRouterState()
  const pathname = router.location.pathname
  const { user } = useAuth()
  const { required: setupRequired, loading: setupLoading } = useSetupRequired()
  const { setIsWizardOpen } = useSetupWizard()
  const [showWizard, setShowWizard] = useState(false)
  const [hasShownWizard, setHasShownWizard] = useState(false)

  const isFullWidth =
    pathname.includes("/chat") ||
    pathname.includes("/files") ||
    pathname.includes("/projects") ||
    pathname.includes("/todos") ||
    pathname.startsWith("/learning/skills")

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

  return (
    <SpotlightTourProvider steps={desktopTourSteps}>
      <GlobalRecorderManager />

      <SidebarProvider
        defaultOpen={false}
        className={isFullWidth ? "h-svh overflow-hidden" : ""}
      >
        <AppSidebar />
        <SidebarInset className="min-w-0 overflow-hidden">
          <main
            className={`flex-1 min-w-0 ${isFullWidth ? "overflow-hidden" : "p-6 md:p-8"}`}
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

          {!isFullWidth && <Footer />}
        </SidebarInset>
      </SidebarProvider>

      <SetupWizard open={showWizard} onOpenChange={setShowWizard} />
    </SpotlightTourProvider>
  )
}

// Export hook for settings page to replay tour
export { useTour }

export default Layout
