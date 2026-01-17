import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"
import { useState, useEffect } from "react"
import { Footer } from "@/components/Common/Footer"
import {
  SpotlightTourProvider,
  useTour,
} from "@/components/Common/SpotlightTour"
import { desktopTourSteps } from "@/components/Common/tourSteps"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { SetupWizard, useSetupRequired } from "@/components/Wizard"
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
  const [showWizard, setShowWizard] = useState(false)

  const isFullWidth =
    pathname.includes("/chat") ||
    pathname.includes("/files") ||
    pathname.includes("/projects") ||
    pathname.includes("/todos")

  // Show wizard when setup is required
  useEffect(() => {
    if (!setupLoading && setupRequired && user) {
      setShowWizard(true)
    }
  }, [setupRequired, setupLoading, user])

  return (
    <SpotlightTourProvider steps={desktopTourSteps}>
      <SidebarProvider className={isFullWidth ? "h-svh overflow-hidden" : ""}>
        <AppSidebar />
        <SidebarInset>
          <main className={`flex-1 ${isFullWidth ? "overflow-hidden" : "p-6 md:p-8"}`}>
            <div className={isFullWidth ? "h-full w-full" : "mx-auto max-w-7xl"}>
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

