import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@evoloop/shared/components/NotFound"
import { useState } from "react"
import StartupScreen from "@/components/Startup/StartupScreen"
import { DetectedProjectAlert } from "@/components/Projects/Import"
import { SetupWizardProvider } from "@/components/Wizard"

import { BenefitRequirementDialog } from "@/components/Subscription/BenefitRequirementDialog"

export const Route = createRootRoute({
  component: RootComponent,
  notFoundComponent: () => <NotFound />,
  errorComponent: () => <ErrorComponent />,
})

function RootComponent() {
  const [isBackendReady, setIsBackendReady] = useState(false)

  if (!isBackendReady) {
    return <StartupScreen onReady={() => setIsBackendReady(true)} />
  }

  return (
    <SetupWizardProvider>
      <HeadContent />
      <Outlet />
      <DetectedProjectAlert />
      <BenefitRequirementDialog />
    </SetupWizardProvider>
  )
}
