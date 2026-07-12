import { Alert, AlertDescription } from "@evoloop/shared/components/ui/alert"
import { createFileRoute } from "@tanstack/react-router"
import { Info, Loader2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { PaymentDialog } from "@/components/Subscription/PaymentDialog"
import { PlanComparison } from "@/components/Subscription/PlanComparison"
import { SubscriptionStatus } from "@/components/Subscription/SubscriptionStatus"
import { useSubscription } from "@/hooks/useSubscription"

export const Route = createFileRoute("/_layout/subscription/")({
  component: SubscriptionDashboard,
})

function SubscriptionDashboard() {
  const { t } = useTranslation()
  const {
    detail,
    plans,
    quota,
    isLoading,
    createOrderMutation,
    checkOrderStatus,
    refetchDetail,
    refetchQuota,
  } = useSubscription()

  const [showPayment, setShowPayment] = useState(false)
  const [isRenewalMode, setIsRenewalMode] = useState(false)

  const handleSelectPlan = async (levelId: number) => {
    const isRenewing = levelId === detail?.level_id
    setIsRenewalMode(isRenewing)
    try {
      await createOrderMutation.mutateAsync(levelId)
      // 下单成功后才打开支付弹窗（免费等级等非法目标会被后端拒绝）
      setShowPayment(true)
    } catch (e) {
      console.error("Order creation failed", e)
      setShowPayment(false)
    }
  }

  const handleRefreshOrder = async () => {
    const levelId = createOrderMutation.variables as any
    if (levelId) {
      try {
        await createOrderMutation.mutateAsync(levelId)
      } catch (e) {
        console.error("Order refresh failed", e)
      }
    }
  }

  const handlePaymentSuccess = () => {
    // Refresh data after successful payment
    refetchDetail()
    refetchQuota()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* 1. Subscription Overview & Quota (Combined) */}
      <div className="space-y-6">
        <div className="flex items-baseline gap-3">
          <h2 className="text-xl font-semibold tracking-tight">
            {t("subscription.title")}
          </h2>
          <p className="text-muted-foreground text-sm">
            {t("subscription.subtitle")}
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <SubscriptionStatus
            detail={detail}
            quota={quota}
            onRenew={() => {
              if (detail?.level_id) {
                handleSelectPlan(detail.level_id)
              }
            }}
            onUpgrade={() => {
              document
                .getElementById("plans-section")
                ?.scrollIntoView({ behavior: "smooth" })
            }}
          />

          <Alert className="bg-muted/50 border-border py-2.5">
            <Info className="h-4 w-4 text-muted-foreground shrink-0" />
            <AlertDescription className="text-xs text-muted-foreground leading-normal">
              {t("subscription.notice.benefits")}
            </AlertDescription>
          </Alert>
        </div>
      </div>

      {/* 2. Pricing & Upgrade Section */}
      <div id="plans-section" className="space-y-6 pt-8 border-t border-border">
        <div className="flex items-baseline gap-3">
          <h2 className="text-xl font-semibold tracking-tight">
            {t("subscription.plans.title")}
          </h2>
          <p className="text-muted-foreground text-sm">
            {t("subscription.plans.desc")}
          </p>
        </div>

        <PlanComparison
          plans={plans}
          currentLevelId={detail?.level_id}
          currentPlanPrice={parseFloat(
            plans.find((p: any) => p.level_id === detail?.level_id)?.price ||
              "0",
          )}
          onSelect={handleSelectPlan}
          isLoading={createOrderMutation.isPending}
        />
      </div>

      {/* Payment Dialog Component */}
      <PaymentDialog
        open={showPayment}
        onOpenChange={setShowPayment}
        orderData={(createOrderMutation.data as any)?.data}
        isRenewalMode={isRenewalMode}
        isPending={createOrderMutation.isPending}
        checkOrderStatus={checkOrderStatus}
        onSuccess={handlePaymentSuccess}
        onRefresh={handleRefreshOrder}
      />
    </div>
  )
}
