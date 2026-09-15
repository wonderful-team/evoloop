import { createFileRoute, redirect } from "@tanstack/react-router"
import { isLoggedIn } from "@/hooks/useAuth"
import { AutonomousDutyPage } from "@/components/Duty/AutonomousDutyPage"

export const Route = createFileRoute("/_layout/duty-autonomous")({
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
  component: AutonomousDutyPage,
})
