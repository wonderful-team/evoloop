import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { CreditCard } from "lucide-react"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/subscription")({
  component: SubscriptionLayout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function SubscriptionLayout() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-8 pb-10">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
              {t("subscription.title")}
            <p className="text-muted-foreground">
              {t("subscription.subtitle")}
            </p>
          </div>
        </div>
      </div>

      <Outlet />
    </div>
  )
}
