import { createFileRoute } from "@tanstack/react-router"
import { useSubscription } from "@/hooks/useSubscription"
import { QuotaCard } from "@/components/Subscription/QuotaCard"
import { SubscriptionStatus } from "@/components/Subscription/SubscriptionStatus"
import { PlanComparison } from "@/components/Subscription/PlanComparison"
import { useTranslation } from "react-i18next"
import { useState, useEffect, useRef } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@evoloop/shared/components/ui/dialog"
import { Alert, AlertDescription, AlertTitle } from "@evoloop/shared/components/ui/alert"
import { Info, Loader2, CheckCircle2, Zap } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"

export const Route = createFileRoute("/_layout/subscription/")({
  component: SubscriptionDashboard,
})

function SubscriptionDashboard() {
  const { t } = useTranslation()
  const { detail, plans, quota, isLoading, createOrderMutation, checkOrderStatus, refetchDetail, refetchQuota } = useSubscription()
  const [showPayment, setShowPayment] = useState(false)
  const [paymentSuccess, setPaymentSuccess] = useState(false)
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null)

  const handleSelectPlan = async (levelId: number) => {
    setShowPayment(true)
    setPaymentSuccess(false)
    try {
        await createOrderMutation.mutateAsync(levelId)
    } catch (e) {
        console.error("Order creation failed", e)
    }
  }

  // Polling for payment status
  useEffect(() => {
    const orderId = (createOrderMutation.data as any)?.data?.order_id
    
    if (showPayment && orderId && !paymentSuccess) {
        pollTimerRef.current = setInterval(async () => {
            const status = await checkOrderStatus(orderId)
            if (status?.is_paid) {
                setPaymentSuccess(true)
                if (pollTimerRef.current) clearInterval(pollTimerRef.current)
                
                // Refresh data
                setTimeout(() => {
                    refetchDetail()
                    refetchQuota()
                }, 1000)
            }
        }, 3000)
    }

    return () => {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [showPayment, createOrderMutation.data, paymentSuccess])

  const handleClosePayment = () => {
    setShowPayment(false)
    if (paymentSuccess) {
        setPaymentSuccess(false)
    }
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
      {/* 1. Subscription Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 items-stretch">
        <div className="lg:col-span-2 flex flex-col gap-4">
           <SubscriptionStatus 
             detail={detail} 
             onManage={() => {
                const element = document.getElementById('plans-section');
                element?.scrollIntoView({ behavior: 'smooth' });
             }}
           />
           
           <Alert className="bg-muted/50 border-border py-2.5">
             <Info className="h-4 w-4 text-muted-foreground shrink-0" />
             <AlertDescription className="text-xs text-muted-foreground leading-normal">
                {t("subscription.notice.desc", "会员等级决定 AI 调用额度和上下文窗口大小，专业版及以上享受优先处理权。")}
             </AlertDescription>
           </Alert>
        </div>

        {/* 2. Quota Usage Breakdown */}
        <div className="lg:col-span-1">
          <QuotaCard quota={quota} />
        </div>
      </div>

      {/* 3. Pricing & Upgrade Section */}
      <div id="plans-section" className="space-y-6 pt-8 border-t border-border">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold tracking-tight">{t("subscription.plans.title", "订阅方案")}</h2>
          <p className="text-muted-foreground text-sm">{t("subscription.plans.desc", "选择最适合您的 AI 创作与开发套餐")}</p>
        </div>
        
        <PlanComparison 
          plans={plans} 
          currentLevelId={detail?.level_id}
          onSelect={handleSelectPlan}
          isLoading={createOrderMutation.isPending}
        />
      </div>

      {/* Payment Dialog */}
      <Dialog open={showPayment} onOpenChange={handleClosePayment}>
        <DialogContent className="sm:max-w-md border-border bg-background/95 backdrop-blur-xl">
          <DialogHeader className="space-y-2">
            <DialogTitle className="text-xl font-bold tracking-tight">
                {paymentSuccess ? t("subscription.payment.successTitle", "支付成功") : t("subscription.payment.title", "确认订单")}
            </DialogTitle>
            <DialogDescription className="text-[13px]">
                {paymentSuccess 
                    ? t("subscription.payment.successDesc", "您的订阅已激活，会员权益已即时生效")
                    : t("subscription.payment.desc", "请扫描下方二维码完成支付以激活您的订阅")
                }
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex flex-col items-center justify-center p-6 space-y-8">
             {paymentSuccess ? (
                <div className="flex flex-col items-center space-y-6 animate-in zoom-in duration-300">
                    <div className="h-24 w-24 bg-primary/10 rounded-full flex items-center justify-center ring-8 ring-primary/5">
                        <CheckCircle2 className="h-12 w-12 text-primary" />
                    </div>
                    <p className="text-center text-sm text-muted-foreground max-w-[240px] leading-relaxed">
                        {t("subscription.payment.thankYou", "感谢您的订阅！现在您可以享受更强大的 AI 能力。")}
                    </p>
                    <Button onClick={handleClosePayment} className="w-full bg-primary hover:bg-primary/90 font-bold h-11">
                        {t("common.ok", "确定")}
                    </Button>
                </div>
             ) : (
                <>
                    <div className="relative group">
                        {createOrderMutation.isPending ? (
                            <div className="h-52 w-52 bg-muted/30 animate-pulse rounded-2xl flex items-center justify-center border border-border/50">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : (createOrderMutation.data as any)?.data?.qrcode ? (
                            <div className="p-5 bg-white rounded-2xl shadow-xl ring-1 ring-border/10 relative transition-transform hover:scale-[1.02] duration-300">
                                <img 
                                    src={(createOrderMutation.data as any).data.qrcode} 
                                    alt="Payment QR" 
                                    className="h-48 w-48"
                                />
                                {/* Bottom Indicator */}
                                <div className="absolute -bottom-2 -right-2 bg-primary text-white p-1 rounded-full shadow-lg">
                                     <Zap size={14} fill="white" />
                                </div>
                            </div>
                        ) : (
                            <div className="h-52 w-52 bg-muted/40 rounded-2xl flex items-center justify-center text-muted-foreground text-xs text-center p-6 border border-dashed">
                                {t("subscription.payment.error", "获取支付方式失败，请重试")}
                            </div>
                        )}
                    </div>

                    <div className="text-center space-y-4">
                        <div className="flex items-baseline justify-center gap-1.5 translate-x-2">
                            <span className="text-sm font-bold text-muted-foreground">¥</span>
                            <span className="text-4xl font-black text-primary tracking-tighter">
                                {(createOrderMutation.data as any)?.data?.order?.order_money || "0.00"}
                            </span>
                        </div>
                        <div className="px-5 py-2.5 bg-primary/5 rounded-full inline-flex items-center gap-2.5 border border-primary/10 ring-4 ring-primary/[0.02]">
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                            <span className="text-[11px] font-bold text-primary uppercase tracking-wider">
                                {t("subscription.payment.pollNotice", "正在等待支付结果")}
                            </span>
                        </div>
                    </div>
                </>
             )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

