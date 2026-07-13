import NotFound from "@evoloop/shared/components/NotFound"
import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import { useState } from "react"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { GlobalOverlayManager } from "@/components/Common/GlobalOverlayManager"
import { WindowDragRegion } from "@/components/Common/WindowDragRegion"
import { DetectedProjectAlert } from "@/components/Projects/Import"
import StartupScreen from "@/components/Startup/StartupScreen"
import { BenefitRequirementDialog } from "@/components/Subscription/BenefitRequirementDialog"
import { SetupWizardProvider } from "@/components/Wizard"

export const Route = createRootRoute({
  component: RootComponent,
  notFoundComponent: () => <NotFound />,
  errorComponent: () => <ErrorComponent />,
})

function RootComponent() {
  const [isBackendReady, setIsBackendReady] = useState(false)

  const isOverlay = typeof window !== "undefined" && (
    window.location.pathname.includes("marker-overlay") ||
    window.location.hash.includes("marker-overlay")
  )

  if (isOverlay) {
    return (
      <>
        <HeadContent />
        <Outlet />
      </>
    )
  }

  if (!isBackendReady) {
    return (
      <>
        <WindowDragRegion />
        <StartupScreen onReady={() => setIsBackendReady(true)} />
      </>
    )
  }

  return (
    <>
      <WindowDragRegion />
      <SetupWizardProvider>
        <HeadContent />
        <Outlet />
        <DetectedProjectAlert />
        <BenefitRequirementDialog />
        <GlobalOverlayManager />
      </SetupWizardProvider>
    </>
  )
}
