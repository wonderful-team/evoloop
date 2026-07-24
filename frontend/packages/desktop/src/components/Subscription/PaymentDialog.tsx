import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { CheckCircle2, Loader2, RefreshCw, Timer } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { OrderData, OrderStatus } from "@/types/subscription"

interface PaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  orderData: OrderData | null
  isRenewalMode: boolean
  isPending: boolean
  payType: string
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
  payType,
  checkOrderStatus,
  onSuccess,
  onRefresh,
}: PaymentDialogProps) => {
  const { t } = useTranslation()
  const [paymentSuccess, setPaymentSuccess] = useState(false)
  const [qrCountdown, setQrCountdown] = useState(3600)
  const [isQrExpired, setIsQrExpired] = useState(false)
  const [stripeError, setStripeError] = useState<string | null>(null)
  const [stripeProcessing, setStripeProcessing] = useState(false)

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null)
  const countdownTimerRef = useRef<NodeJS.Timeout | null>(null)
  const stripeElementsRef = useRef<HTMLDivElement>(null)
  const stripeInstanceRef = useRef<any>(null)
  const elementsInstanceRef = useRef<any>(null)
  const cardElementRef = useRef<any>(null)

  const payData = (orderData as any)?.pay_data
  const isStripe = payType === "stripe"
  const hasStripeSecret = isStripe && payData?.data?.client_secret

  // Reset state when dialog opens
  useEffect(() => {
    if (open && orderData) {
      setPaymentSuccess(false)
      setQrCountdown(3600)
      setIsQrExpired(false)
      setStripeError(null)
      setStripeProcessing(false)
    }
  }, [open, orderData?.order?.order_id])

  // Initialize Stripe Elements when dialog opens with Stripe
  useEffect(() => {
    if (!open || !hasStripeSecret || !stripeElementsRef.current) return

    let cancelled = false

    const initStripe = async () => {
      try {
        const publishableKey = payData.data.publishable_key
        const clientSecret = payData.data.client_secret

        const { loadStripe } = await import("@stripe/stripe-js")
        const stripe = await loadStripe(publishableKey)
        if (!stripe || cancelled) return
        stripeInstanceRef.current = stripe

        const elements = stripe.elements({ clientSecret })
        elementsInstanceRef.current = elements

        const cardElement = elements.create(
          "payment" as any,
          {
            style: {
              base: {
                fontSize: "16px",
                color: "#fff",
                "::placeholder": { color: "#888" },
              },
            },
          } as any,
        )
        if (stripeElementsRef.current)
          cardElement.mount(stripeElementsRef.current)
        cardElementRef.current = cardElement
      } catch (e: any) {
        if (!cancelled)
          setStripeError(e.message || "Stripe initialization failed")
      }
    }

    initStripe()

    return () => {
      cancelled = true
      if (cardElementRef.current) {
        try {
          cardElementRef.current.destroy()
        } catch {}
        cardElementRef.current = null
      }
      stripeInstanceRef.current = null
      elementsInstanceRef.current = null
    }
  }, [open, hasStripeSecret])

  // Countdown logic (non-Stripe)
  useEffect(() => {
    if (!open || paymentSuccess || isQrExpired || !orderData || isStripe) return
    if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
    countdownTimerRef.current = setInterval(() => {
      setQrCountdown((prev) => {
        if (prev <= 1) {
          setIsQrExpired(true)
          if (countdownTimerRef.current)
            clearInterval(countdownTimerRef.current)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
    }
  }, [open, orderData, paymentSuccess, isQrExpired, isStripe])

  // Polling logic (non-Stripe)
  useEffect(() => {
    if (isStripe) return
    const orderId = orderData?.order?.order_id
    if (!open || !orderId || paymentSuccess || isQrExpired) return
    if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    pollTimerRef.current = setInterval(async () => {
      const status = await checkOrderStatus(orderId)
      if (status?.is_paid) {
        setPaymentSuccess(true)
        if (pollTimerRef.current) clearInterval(pollTimerRef.current)
        if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
        setTimeout(() => onSuccess(), 1000)
      }
    }, 3000)
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [
    open,
    orderData,
    paymentSuccess,
    isQrExpired,
    checkOrderStatus,
    onSuccess,
    isStripe,
  ])

  const handleStripePay = async () => {
    if (!stripeInstanceRef.current || !cardElementRef.current) return
    setStripeProcessing(true)
    setStripeError(null)
    try {
      const { error } = await stripeInstanceRef.current.confirmPayment({
        elements: elementsInstanceRef.current,
        redirect: "if_required",
      })
      if (error) {
        setStripeError(error.message || "Payment failed")
      } else {
        setPaymentSuccess(true)
        setTimeout(() => onSuccess(), 1000)
      }
    } catch (e: any) {
      setStripeError(e.message || "Payment failed")
    } finally {
      setStripeProcessing(false)
    }
  }

  const formatCountdown = (seconds: number) => {
    if (seconds >= 3600) {
      const hours = Math.floor(seconds / 3600)
      const mins = Math.floor((seconds % 3600) / 60)
      return t("subscription.payment.expiresInHours", { hours, mins })
    }
    if (seconds >= 60) {
      const mins = Math.floor(seconds / 60)
      const secs = seconds % 60
      return t("subscription.payment.expiresInMinutes", { mins, secs })
    }
    return t("subscription.payment.expiresInSeconds", { seconds })
  }

  const handleClose = () => onOpenChange(false)

  const isUpgrade = orderData?.is_upgrade
  const upgradeInfo = orderData?.upgrade_info

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md border-border bg-background/95 backdrop-blur-xl">
        <DialogTitle className="sr-only">
          {paymentSuccess
            ? t("subscription.payment.successTitle")
            : isRenewalMode
              ? t("subscription.payment.renewTitle", {
                  name: orderData?.order?.level_name || "",
                })
              : t("subscription.payment.subscribeTitle", {
                  name: orderData?.order?.level_name || "",
                })}
        </DialogTitle>

        {paymentSuccess ? (
          <div className="flex flex-col items-center space-y-6 p-6 animate-in zoom-in duration-300">
            <div className="h-24 w-24 bg-primary/10 rounded-full flex items-center justify-center ring-8 ring-primary/5">
              <CheckCircle2 className="h-12 w-12 text-primary" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-bold">
                {t("subscription.payment.successTitle")}
              </h3>
              <p className="text-sm text-muted-foreground">
                {t("subscription.payment.successDesc")}
              </p>
            </div>
            {isUpgrade &&
              upgradeInfo &&
              parseFloat(upgradeInfo.refund_amount) > 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center w-full">
                  <p className="text-sm text-green-700">
                    {t("subscription.payment.refunded", {
                      amount: upgradeInfo.refund_amount,
                    })}
                  </p>
                </div>
              )}
            <Button
              onClick={handleClose}
              className="w-full bg-primary hover:bg-primary/90 font-bold h-11"
            >
              {t("common.ok")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col">
            <div className="px-6 pt-6 pb-4">
              <h3 className="text-lg font-semibold">
                {isRenewalMode
                  ? t("subscription.payment.renewTitle", {
                      name: orderData?.order?.level_name || "",
                    })
                  : t("subscription.payment.subscribeTitle", {
                      name: orderData?.order?.level_name || "",
                    })}
              </h3>
            </div>

            <div className="flex flex-col items-center gap-2 pb-6">
              {isStripe && hasStripeSecret ? (
                <div className="w-full px-6 space-y-4">
                  <div
                    ref={stripeElementsRef}
                    className="p-4 bg-black/5 rounded-xl border border-border min-h-[120px]"
                  />
                  {stripeError && (
                    <p className="text-xs text-destructive font-medium text-center">
                      {stripeError}
                    </p>
                  )}
                  <Button
                    onClick={handleStripePay}
                    disabled={stripeProcessing}
                    className="w-full font-bold h-11"
                  >
                    {stripeProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        {t("subscription.payment.processing")}
                      </>
                    ) : (
                      t("subscription.payment.payNow")
                    )}
                  </Button>
                </div>
              ) : isPending ? (
                <div className="h-44 w-44 bg-muted/30 animate-pulse rounded-xl flex items-center justify-center border border-border/50">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : orderData?.qrcode ? (
                <>
                  <div
                    className={`p-3 bg-white rounded-xl shadow-sm ring-1 ring-border/20 relative ${isQrExpired ? "opacity-50" : ""}`}
                  >
                    <img
                      src={orderData.qrcode}
                      alt={t("subscription.payment.qrAlt")}
                      className="h-40 w-40"
                    />
                    {isQrExpired && (
                      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center gap-2">
                        <Timer className="h-8 w-8 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">
                          {t("subscription.payment.qrExpired")}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={onRefresh}
                          disabled={isPending}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" />
                          {t("subscription.payment.refresh")}
                        </Button>
                      </div>
                    )}
                  </div>
                  {!isQrExpired && (
                    <p
                      className={`text-[11px] ${qrCountdown <= 60 ? "text-destructive font-medium" : "text-muted-foreground"}`}
                    >
                      {qrCountdown > 0
                        ? formatCountdown(qrCountdown)
                        : t("subscription.payment.qrInvalid")}
                    </p>
                  )}
                </>
              ) : (
                <div className="h-44 w-44 bg-muted/40 rounded-xl flex items-center justify-center text-muted-foreground text-xs text-center p-4 border border-dashed">
                  {t("subscription.payment.error")}
                </div>
              )}
            </div>

            {/* Price & Info Summary */}
            <div className="px-6 pb-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <span className="text-sm font-medium">
                  {isStripe
                    ? t("subscription.payment.cardPay")
                    : t("subscription.payment.wechatPay")}
                </span>
                <span className="text-xl font-bold">
                  {t("common.currencySymbol")}
                  {isUpgrade && upgradeInfo
                    ? upgradeInfo.net_amount || "0.00"
                    : orderData?.order?.order_money || "0.00"}
                </span>
              </div>
              <ul className="space-y-2 text-xs text-muted-foreground">
                {isUpgrade && upgradeInfo ? (
                  <>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>
                        {t("subscription.payment.upgradeDiff", {
                          newPrice: upgradeInfo.pay_amount,
                          refund: upgradeInfo.refund_amount,
                        })}
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>
                        {t("subscription.payment.refundToBalance", {
                          amount: upgradeInfo.refund_amount,
                        })}
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>{t("subscription.payment.upgradeNote")}</span>
                    </li>
                  </>
                ) : isRenewalMode ? (
                  <>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>
                        {t("subscription.payment.renewPrice", {
                          price: orderData?.order?.order_money || "0",
                        })}
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>{t("subscription.payment.renewNote1")}</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>{t("subscription.payment.renewNote2")}</span>
                    </li>
                  </>
                ) : (
                  <>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>
                        {t("subscription.payment.subscribePrice", {
                          price: orderData?.order?.order_money || "0",
                        })}
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-primary">{t("common.bullet")}</span>
                      <span>{t("subscription.payment.validityNote")}</span>
                    </li>
                  </>
                )}
                <li className="flex gap-2">
                  <span className="text-primary">{t("common.bullet")}</span>
                  <span>{t("subscription.payment.noRefund")}</span>
                </li>
              </ul>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
