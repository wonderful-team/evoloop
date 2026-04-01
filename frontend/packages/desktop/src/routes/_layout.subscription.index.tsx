import { createFileRoute } from "@tanstack/react-router"
import { useSubscription } from "@/hooks/useSubscription"
import { QuotaCard } from "@/components/Subscription/QuotaCard"
import { SubscriptionStatus } from "@/components/Subscription/SubscriptionStatus"
import { PlanComparison } from "@/components/Subscription/PlanComparison"
import { useTranslation } from "react-i18next"
import { useState, useEffect, useRef } from "react"
import { Dialog, DialogContent } from "@evoloop/shared/components/ui/dialog"
import { Alert, AlertDescription } from "@evoloop/shared/components/ui/alert"
import { Info, Loader2, CheckCircle2, Timer, RefreshCw } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"

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
    refetchQuota 
  } = useSubscription()
  
  // 支付弹窗状态
  const [showPayment, setShowPayment] = useState(false)
  const [paymentSuccess, setPaymentSuccess] = useState(false)
  const [qrCountdown, setQrCountdown] = useState(3600)
  const [isQrExpired, setIsQrExpired] = useState(false)
  const [isRenewalMode, setIsRenewalMode] = useState(false) // 是否是续费模式
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null)
  const countdownTimerRef = useRef<NodeJS.Timeout | null>(null)

  // 处理选择方案：直接创建订单并显示支付弹窗
  const handleSelectPlan = async (levelId: number) => {
    // 判断是否是续费（选择当前相同的套餐）
    const isRenewing = levelId === detail?.level_id
    setIsRenewalMode(isRenewing)
    setShowPayment(true)
    setPaymentSuccess(false)
    try {
      await createOrderMutation.mutateAsync(levelId)
    } catch (e) {
      console.error("Order creation failed", e)
    }
  }

  // 二维码倒计时 - 微信支付二维码实际有效期为1小时（3600秒）
  useEffect(() => {
    if (showPayment && !paymentSuccess && !isQrExpired) {
      setQrCountdown(3600) // 1小时 = 3600秒，与后端一致
      setIsQrExpired(false)
      
      countdownTimerRef.current = setInterval(() => {
        setQrCountdown((prev) => {
          if (prev <= 1) {
            setIsQrExpired(true)
            if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }

    return () => {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
    }
  }, [showPayment, createOrderMutation.data, paymentSuccess])

  // Polling for payment status
  useEffect(() => {
    const orderId = (createOrderMutation.data as any)?.data?.order_id
    
    if (showPayment && orderId && !paymentSuccess && !isQrExpired) {
        pollTimerRef.current = setInterval(async () => {
            const status = await checkOrderStatus(orderId)
            if (status?.is_paid) {
                setPaymentSuccess(true)
                if (pollTimerRef.current) clearInterval(pollTimerRef.current)
                if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
                
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
  }, [showPayment, createOrderMutation.data, paymentSuccess, isQrExpired])

  // 重新获取订单（二维码过期后）
  const handleRefreshOrder = async () => {
    const levelId = (createOrderMutation.variables as any)
    if (levelId) {
      setIsQrExpired(false)
      setQrCountdown(3600)
      try {
        await createOrderMutation.mutateAsync(levelId)
      } catch (e) {
        console.error("Order refresh failed", e)
      }
    }
  }

  // 格式化倒计时显示
  const formatCountdown = (seconds: number) => {
    if (seconds >= 3600) {
      const hours = Math.floor(seconds / 3600)
      const mins = Math.floor((seconds % 3600) / 60)
      return `${hours}小时${mins}分后失效`
    } else if (seconds >= 60) {
      const mins = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${mins}分${secs}秒后失效`
    } else {
      return `${seconds}秒后失效`
    }
  }

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

  // 获取订单数据
  const orderData = (createOrderMutation.data as any)?.data
  const isUpgrade = orderData?.is_upgrade
  const upgradeInfo = orderData?.upgrade_info

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
             onRenew={() => {
                // 续费当前套餐
                if (detail?.level_id) {
                  handleSelectPlan(detail.level_id)
                }
             }}
           />
           
           <Alert className="bg-muted/50 border-border py-2.5">
             <Info className="h-4 w-4 text-muted-foreground shrink-0" />
             <AlertDescription className="text-xs text-muted-foreground leading-normal">
                {t("subscription.notice.benefits")}
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
          currentPlanPrice={parseFloat(plans.find((p: any) => p.level_id === detail?.level_id)?.price || "0")}
          onSelect={handleSelectPlan}
          isLoading={createOrderMutation.isPending}
        />
      </div>

      {/* Payment Dialog */}
      <Dialog open={showPayment} onOpenChange={handleClosePayment}>
        <DialogContent className="sm:max-w-md border-border bg-background/95 backdrop-blur-xl">
          {paymentSuccess ? (
            <div className="flex flex-col items-center space-y-6 p-6 animate-in zoom-in duration-300">
                <div className="h-24 w-24 bg-primary/10 rounded-full flex items-center justify-center ring-8 ring-primary/5">
                    <CheckCircle2 className="h-12 w-12 text-primary" />
                </div>
                <div className="text-center space-y-2">
                    <h3 className="text-lg font-bold">{t("subscription.payment.successTitle", "支付成功")}</h3>
                    <p className="text-sm text-muted-foreground">
                        {t("subscription.payment.successDesc", "您的订阅已激活，会员权益已即时生效")}
                    </p>
                </div>
                {isUpgrade && upgradeInfo?.refund_amount > 0 && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center w-full">
                        <p className="text-sm text-green-700">
                        ¥{upgradeInfo.refund_amount} 已退还到您的账户余额
                        </p>
                    </div>
                )}
                <Button onClick={handleClosePayment} className="w-full bg-primary hover:bg-primary/90 font-bold h-11">
                    {t("common.ok", "确定")}
                </Button>
            </div>
          ) : (
            <div className="flex flex-col">
                {/* 标题 */}
                <div className="px-6 pt-6 pb-4">
                    <h3 className="text-lg font-semibold">
                        {isRenewalMode 
                          ? t("subscription.payment.renewTitle", { name: orderData?.order?.level_name || "" })
                          : t("subscription.payment.subscribeTitle", { name: orderData?.order?.level_name || "" })
                        }
                    </h3>
                    {isRenewalMode && (
                        <p className="text-xs text-muted-foreground mt-1">
                            {t("subscription.payment.renewDesc")}
                        </p>
                    )}
                </div>
                
                {/* 二维码区域 */}
                <div className="flex flex-col items-center gap-2 pb-6">
                    {createOrderMutation.isPending ? (
                        <div className="h-44 w-44 bg-muted/30 animate-pulse rounded-xl flex items-center justify-center border border-border/50">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        </div>
                    ) : orderData?.qrcode ? (
                        <div className={`p-3 bg-white rounded-xl shadow-sm ring-1 ring-border/20 relative ${isQrExpired ? 'opacity-50' : ''}`}>
                            <img 
                                src={orderData.qrcode} 
                                alt="Payment QR" 
                                className="h-40 w-40"
                            />
                            {isQrExpired && (
                                <div className="absolute inset-0 bg-background/80 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center gap-2">
                                    <Timer className="h-8 w-8 text-muted-foreground" />
                                    <span className="text-xs text-muted-foreground">二维码已过期</span>
                                    <Button 
                                        size="sm" 
                                        variant="outline" 
                                        onClick={handleRefreshOrder}
                                        disabled={createOrderMutation.isPending}
                                    >
                                        <RefreshCw className="h-3 w-3 mr-1" />
                                        重新获取
                                    </Button>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="h-44 w-44 bg-muted/40 rounded-xl flex items-center justify-center text-muted-foreground text-xs text-center p-4 border border-dashed">
                            {t("subscription.payment.error", "获取支付失败")}
                        </div>
                    )}
                    {!isQrExpired && (
                        <p className={`text-[11px] ${qrCountdown <= 60 ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                            {qrCountdown > 0 ? formatCountdown(qrCountdown) : '二维码已失效'}
                        </p>
                    )}
                </div>
                
                {/* 支付信息区域 */}
                <div className="px-6 pb-6 space-y-4">
                    {/* 支付方式和价格 */}
                    <div className="flex items-center justify-between pb-3 border-b border-border">
                        <span className="text-sm font-medium">微信扫码支付</span>
                        <span className="text-xl font-bold">¥{isUpgrade && upgradeInfo ? upgradeInfo.net_amount || "0.00" : orderData?.order?.order_money || "0.00"}</span>
                    </div>
                    
                    {/* 条款列表 */}
                    <ul className="space-y-2 text-xs text-muted-foreground">
                        {isUpgrade && upgradeInfo ? (
                            // 升级场景
                            <>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>升级补差价：新套餐 ¥{upgradeInfo.pay_amount} - 原套餐剩余 ¥{upgradeInfo.refund_amount}</span>
                                </li>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>原套餐剩余¥{upgradeInfo.refund_amount}将在支付成功后退还到余额</span>
                                </li>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>升级后套餐期限累加，额外配额自动补差</span>
                                </li>
                            </>
                        ) : isRenewalMode ? (
                            // 续费场景
                            <>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>续费 ¥{orderData?.order?.order_money || "0"}/月</span>
                                </li>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>续费后有效期延长，额度叠加</span>
                                </li>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>原剩余有效期将累加，不会浪费</span>
                                </li>
                            </>
                        ) : (
                            // 新购场景
                            <>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>开通会员订阅：¥{orderData?.order?.order_money || "0"}/月</span>
                                </li>
                                <li className="flex gap-2">
                                    <span className="text-primary">•</span>
                                    <span>有效期自支付成功日起计算</span>
                                </li>
                            </>
                        )}
                        <li className="flex gap-2">
                            <span className="text-primary">•</span>
                            <span>会员服务属于虚拟商品，一经支付无法退款，请你谅解</span>
                        </li>
                    </ul>
                    
                    {/* 支付状态提示 */}
                    <div className="pt-2 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                        <span>正在等待支付结果...</span>
                    </div>
                </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
