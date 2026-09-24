import {Button} from "@evoloop/shared/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import {CheckCircle2, Loader2, MessageCircle, RefreshCw} from "lucide-react"
import {useCallback, useEffect, useRef, useState} from "react"
import {useTranslation} from "react-i18next"
import {AccountService} from "@/client"

interface WechatLoginProps {
  onSuccess?: () => void
  onError?: (error: Error) => void
}

// Response types from backend
interface QRCodeResponse {
  key: string
  expire_time: number
  qrcode_url: string
  ticket: string
}

interface LoginStatusResponse {
  status: "pending" | "confirmed" | "expired" | "error"
  message?: string
  access_token?: string
  token_type?: string
}

export function WechatLoginButton({ onSuccess, onError }: WechatLoginProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [config, setConfig] = useState<{
    enabled: boolean
    app_id: string | null
  } | null>(null)

  useEffect(() => {
    // Check if WeChat login is enabled
    AccountService.getWechatConfig()
      .then((data: any) =>
        setConfig(data as { enabled: boolean; app_id: string | null }),
      )
      .catch(console.error)
  }, [])

  const handleOpen = () => {
    setIsOpen(true)
  }

  // Don't show button if WeChat login is not configured
  if (!config?.enabled) {
    return null
  }

  return (
    <>
      <Button
        variant="outline"
        className="w-full"
        onClick={handleOpen}
        type="button"
      >
        <MessageCircle className="mr-2 h-4 w-4 text-green-600" />
        {t("auth.login.wechatLogin")}
      </Button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("auth.login.wechatScanTitle")}</DialogTitle>
            <DialogDescription>
              {t("auth.login.wechatScanDesc")}
            </DialogDescription>
          </DialogHeader>
          <WechatQRCode onSuccess={onSuccess} onError={onError} />
        </DialogContent>
      </Dialog>
    </>
  )
}

function WechatQRCode({ onSuccess, onError }: WechatLoginProps) {
  const { t } = useTranslation()
  const [qrCode, setQrCode] = useState<QRCodeResponse | null>(null)
  const [status, setStatus] = useState<LoginStatusResponse["status"]>("pending")
  const [error, setError] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(600)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  const countdownRef = useRef<NodeJS.Timeout | null>(null)

  const generateQR = useCallback(async () => {
    try {
      setError(null)
      setStatus("pending")
      const response = await AccountService.generateQrCode()
      const qrData = response as QRCodeResponse
      setQrCode(qrData)
      setCountdown(qrData.expire_time)
    } catch (err) {
      setError(t("auth.login.wechatQRCodeError"))
      if (onError && err instanceof Error) onError(err)
    }
  }, [t, onError])

  const checkStatus = useCallback(
    async (key: string) => {
      try {
        const response = await AccountService.checkWechatLoginStatus({ key })
        const statusData = response as LoginStatusResponse
        setStatus(statusData.status)

        if (statusData.status === "confirmed") {
          // Stop polling
          if (pollingRef.current) clearInterval(pollingRef.current)
          if (countdownRef.current) clearInterval(countdownRef.current)

          // Always call wechatDirectLogin to ensure Backend session cookie is set.
          // Frontend no longer stores tokens; session is managed by Backend.
          await AccountService.wechatDirectLogin({ key })
          onSuccess?.()
        } else if (statusData.status === "expired") {
          if (pollingRef.current) clearInterval(pollingRef.current)
          if (countdownRef.current) clearInterval(countdownRef.current)
        }
      } catch (err) {
        console.error("Check status error:", err)
      }
    },
    [onSuccess],
  )

  // Generate QR code on mount
  useEffect(() => {
    generateQR()
  }, [generateQR])

  // Start polling when QR code is generated
  useEffect(() => {
    if (!qrCode?.key) return

    // Poll every 2 seconds
    pollingRef.current = setInterval(() => {
      checkStatus(qrCode.key)
    }, 2000)

    // Countdown timer
    countdownRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(countdownRef.current!)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
      if (countdownRef.current) clearInterval(countdownRef.current)
    }
  }, [qrCode, checkStatus])

  // Format countdown
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 space-y-4">
        <p className="text-red-500">{error}</p>
        <Button onClick={generateQR} variant="outline">
          <RefreshCw className="mr-2 h-4 w-4" />
          {t("auth.login.retry")}
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center space-y-4 p-4">
      {/* QR Code */}
      <div className="relative">
        {qrCode ? (
          <>
            <img
              src={
                qrCode.qrcode_url ||
                `https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket=${qrCode.ticket}`
              }
              alt={t("auth.login.wechatQRAlt")}
              className="w-48 h-48 border rounded-lg"
            />
            {/* Overlay for expired or confirmed states */}
            {status === "expired" && (
              <div className="absolute inset-0 bg-white/90 flex flex-col items-center justify-center rounded-lg">
                <p className="text-sm text-gray-500 mb-2">
                  {t("auth.login.qrExpired")}
                </p>
                <Button onClick={generateQR} size="sm" variant="outline">
                  <RefreshCw className="mr-1 h-3 w-3" />
                  {t("auth.login.refresh")}
                </Button>
              </div>
            )}
            {status === "confirmed" && (
              <div className="absolute inset-0 bg-white/90 flex flex-col items-center justify-center rounded-lg">
                <CheckCircle2 className="h-12 w-12 text-green-500 mb-2" />
                <p className="text-sm text-green-600">
                  {t("auth.login.loginSuccess")}
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="w-48 h-48 bg-gray-100 flex items-center justify-center rounded-lg">
            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          </div>
        )}
      </div>

      {/* Status */}
      <div className="text-center space-y-2">
        {status === "pending" && (
          <>
            <p className="text-sm text-gray-600">
              {t("auth.login.scanWithWechat")}
            </p>
            <p className="text-xs text-gray-400">
              {t("auth.login.expiresIn")}: {formatTime(countdown)}
            </p>
          </>
        )}
        {status === "pending" && (
          <div className="flex flex-col items-center">
            <Loader2 className="h-5 w-5 animate-spin text-green-500 mb-1" />
            <p className="text-sm text-green-600">
              {t("auth.login.scanWithWechat")}
            </p>
          </div>
        )}
        {status === "confirmed" && (
          <p className="text-sm text-green-600">{t("auth.login.processing")}</p>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-gray-50 p-3 rounded-md text-xs text-gray-500 w-full">
        <p>{t("auth.login.wechatInstructions1")}</p>
        <p>{t("auth.login.wechatInstructions2")}</p>
        <p>{t("auth.login.wechatInstructions3")}</p>
      </div>
    </div>
  )
}
