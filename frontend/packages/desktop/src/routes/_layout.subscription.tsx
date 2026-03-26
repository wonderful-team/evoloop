import { createFileRoute, Outlet, Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { ChevronRight, CreditCard } from "lucide-react"

export const Route = createFileRoute("/_layout/subscription")({
  component: SubscriptionLayout,
})

function SubscriptionLayout() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-8 pb-10 px-4 pt-4 md:px-0 md:pt-0">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
          <Link to="/" className="hover:text-foreground transition-colors">
            {t("common.home", "首页")}
          </Link>
          <ChevronRight className="h-4 w-4" />
          <span className="text-foreground font-medium">{t("subscription.title", "会员中心")}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <CreditCard className="h-8 w-8 text-primary" />
              {t("subscription.title", "会员中心")}
            </h1>
            <p className="text-muted-foreground text-lg">
              {t("subscription.subtitle", "管理您的订阅计划与 AI 配额")}
            </p>
          </div>
        </div>
      </div>

      <Outlet />
    </div>
  )
}
