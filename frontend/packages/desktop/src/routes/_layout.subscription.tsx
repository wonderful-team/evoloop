import {createFileRoute, Outlet, redirect} from "@tanstack/react-router"
import {isLoggedIn} from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/subscription")({
  component: SubscriptionLayout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function SubscriptionLayout() {
  return (
    <div className="flex flex-col gap-8 pb-10">
      <Outlet />
    </div>
  )
}
