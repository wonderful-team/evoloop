import {Alert, AlertDescription} from "@evoloop/shared/components/ui/alert"
import {Badge} from "@evoloop/shared/components/ui/badge"
import {createFileRoute} from "@tanstack/react-router"
import {CreditCard, Info, Loader2, Smartphone} from "lucide-react"
import {useState} from "react"
import {useTranslation} from "react-i18next"
import {PaymentDialog} from "@/components/Subscription/PaymentDialog"
import {PlanComparison} from "@/components/Subscription/PlanComparison"
import {SubscriptionStatus} from "@/components/Subscription/SubscriptionStatus"
import {useSubscription} from "@/hooks/useSubscription"

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
  const [selectedPayType, setSelectedPayType] = useState("wechatpay")
  const [selectedLevelId, setSelectedLevelId] = useState<number | null>(null)

  const payTypes = [
    {
      key: "wechatpay",
      label: t("subscription.payment.wechatPay"),
      icon: Smartphone,
    },
    {
      key: "stripe",
      label: t("subscription.payment.cardPay"),
      icon: CreditCard,
    },
  ]

  const handleSelectPlan = async (levelId: number) => {
    const isRenewing = levelId === detail?.level_id
    setIsRenewalMode(isRenewing)
    setSelectedLevelId(levelId)
    setShowPayment(true)
  }

  // When dialog opens, create the order with the selected payment type
  const handleDialogOpenChange = (open: boolean) => {
    setShowPayment(open)
    if (open && selectedLevelId) {
      createOrderMutation.mutate({
        levelId: selectedLevelId,
        payType: selectedPayType,
      })
    }
  }

  const handleRefreshOrder = () => {
    if (selectedLevelId) {
      createOrderMutation.mutate({
        levelId: selectedLevelId,
        payType: selectedPayType,
      })
    }
  }

  const handlePaymentSuccess = () => {
    refetchDetail()
    refetchQuota()
  }

  const orderData = (createOrderMutation.data as any)?.data

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* 1. Subscription Overview & Quota */}
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
              if (detail?.level_id) handleSelectPlan(detail.level_id)
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

      {/* 2. Payment Method Selection */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-muted-foreground">
          {t("subscription.payment.method")}
        </span>
        <div className="flex gap-2">
          {payTypes.map((pt) => {
            const Icon = pt.icon
            const active = selectedPayType === pt.key
            return (
              <Badge
                key={pt.key}
                variant={active ? "default" : "secondary"}
                className="cursor-pointer gap-1.5 px-3 py-1.5 text-xs"
                onClick={() => setSelectedPayType(pt.key)}
              >
                <Icon className="h-3 w-3" />
                {t(`subscription.payment.${pt.key}`) || pt.label}
              </Badge>
            )
          })}
        </div>
      </div>

      {/* 3. Pricing & Upgrade Section */}
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

      {/* Payment Dialog */}
      <PaymentDialog
        open={showPayment}
        onOpenChange={handleDialogOpenChange}
        orderData={orderData}
        isRenewalMode={isRenewalMode}
        isPending={createOrderMutation.isPending}
        payType={selectedPayType}
        checkOrderStatus={checkOrderStatus}
        onSuccess={handlePaymentSuccess}
        onRefresh={handleRefreshOrder}
      />
    </div>
  )
}
