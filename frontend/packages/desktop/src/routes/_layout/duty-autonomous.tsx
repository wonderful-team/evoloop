import {createFileRoute, redirect} from "@tanstack/react-router"
import {isLoggedIn} from "@/hooks/useAuth"
import {DutyWorkbench} from "@evoloop/workbench"

export const Route = createFileRoute("/_layout/duty-autonomous")({
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
  component: DutyWorkbench,
})
