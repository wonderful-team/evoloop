import { useState, useEffect, useRef } from "react"
import { Dialog, DialogContent, DialogTitle } from "@evoloop/shared/components/ui/dialog"
import { Button } from "@evoloop/shared/components/ui/button"
import { Loader2, CheckCircle2, Timer, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { OrderData, OrderStatus } from "@/types/subscription"

interface PaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  orderData: OrderData | null
  isRenewalMode: boolean
  isPending: boolean
  checkOrderStatus: (orderId: string) => Promise<OrderStatus | null>
  onSuccess: () => void
  onRefresh: () => void
}

export const PaymentDialog = ({
  open,
  onOpenChange,
  orderData,
  isRenewalMode,
  isPending,
  checkOrderStatus,
  onSuccess,
  onRefresh
}: PaymentDialogProps) => {
  const { t } = useTranslation()
  const [paymentSuccess, setPaymentSuccess] = useState(false)
  const [qrCountdown, setQrCountdown] = useState(3600)
  const [isQrExpired, setIsQrExpired] = useState(false)
  
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null)
  const countdownTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Reset state when dialog opens with new order
  useEffect(() => {
    if (open && orderData) {
      setPaymentSuccess(false)
      setQrCountdown(3600)
      setIsQrExpired(false)
    }
  }, [open, orderData?.order?.order_id])

  // Countdown logic
  useEffect(() => {
    if (open && !paymentSuccess && !isQrExpired && orderData) {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
      
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
  }, [open, orderData, paymentSuccess, isQrExpired])

  // Polling logic
  useEffect(() => {
    const orderId = orderData?.order?.order_id
    
    if (open && orderId && !paymentSuccess && !isQrExpired) {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current)
        
        pollTimerRef.current = setInterval(async () => {
            const status = await checkOrderStatus(orderId)
            if (status?.is_paid) {
                setPaymentSuccess(true)
                if (pollTimerRef.current) clearInterval(pollTimerRef.current)
                if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
                
                // Trigger success callback after a short delay
                setTimeout(() => {
                    onSuccess()
                }, 1000)
            }
        }, 3000)
    }

    return () => {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [open, orderData, paymentSuccess, isQrExpired, checkOrderStatus, onSuccess])

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

  const handleClose = () => {
    onOpenChange(false)
  }

  const isUpgrade = orderData?.is_upgrade
  const upgradeInfo = orderData?.upgrade_info

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md border-border bg-background/95 backdrop-blur-xl">
        <DialogTitle className="sr-only">
          {paymentSuccess
            ? t("subscription.payment.successTitle")
            : isRenewalMode
              ? t("subscription.payment.renewTitle", { name: orderData?.order?.level_name || "" })
              : t("subscription.payment.subscribeTitle", { name: orderData?.order?.level_name || "" })}
        </DialogTitle>
        
        {paymentSuccess ? (
          <div className="flex flex-col items-center space-y-6 p-6 animate-in zoom-in duration-300">
            <div className="h-24 w-24 bg-primary/10 rounded-full flex items-center justify-center ring-8 ring-primary/5">
              <CheckCircle2 className="h-12 w-12 text-primary" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-bold">{t("subscription.payment.successTitle")}</h3>
              <p className="text-sm text-muted-foreground">
                {t("subscription.payment.successDesc")}
              </p>
            </div>
            {isUpgrade && upgradeInfo && parseFloat(upgradeInfo.refund_amount) > 0 && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center w-full">
                <p className="text-sm text-green-700">
                  ¥{upgradeInfo.refund_amount} 已退还到您的账户余额
                </p>
              </div>
            )}
            <Button onClick={handleClose} className="w-full bg-primary hover:bg-primary/90 font-bold h-11">
              {t("common.ok")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col">
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
            
            <div className="flex flex-col items-center gap-2 pb-6">
              {isPending ? (
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
                        onClick={onRefresh}
                        disabled={isPending}
                      >
                        <RefreshCw className="h-3 w-3 mr-1" />
                        重新获取
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="h-44 w-44 bg-muted/40 rounded-xl flex items-center justify-center text-muted-foreground text-xs text-center p-4 border border-dashed">
                  {t("subscription.payment.error")}
                </div>
              )}
              {!isQrExpired && (
                <p className={`text-[11px] ${qrCountdown <= 60 ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                  {qrCountdown > 0 ? formatCountdown(qrCountdown) : '二维码已失效'}
                </p>
              )}
            </div>
            
            <div className="px-6 pb-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <span className="text-sm font-medium">微信扫码支付</span>
                <span className="text-xl font-bold">¥{isUpgrade && upgradeInfo ? upgradeInfo.net_amount || "0.00" : orderData?.order?.order_money || "0.00"}</span>
              </div>
              
              <ul className="space-y-2 text-xs text-muted-foreground">
                {isUpgrade && upgradeInfo ? (
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
              
              <div className="pt-2 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                <span>正在等待支付结果...</span>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
