import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Calendar, Crown, AlertTriangle } from "lucide-react"
import { useTranslation } from "react-i18next"

interface SubscriptionDetail {
  level_id: number
  level_name: string
  expire_time: number
  status: number
  is_auto_renew: boolean
  order_no?: string
}

interface SubscriptionStatusProps {
  detail?: SubscriptionDetail
  isLoading?: boolean
  onRenew?: () => void
}

export const SubscriptionStatus = ({ detail, isLoading, onRenew }: SubscriptionStatusProps) => {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <Card className="border-border bg-muted/30 animate-pulse">
        <div className="h-32" />
      </Card>
    )
  }

  if (!detail || detail.level_id === 1) {
    return (
      <Card className="border-border bg-card gap-2 py-2">
        <CardContent className="py-4">
          <div className="flex items-center gap-4">
            <div className="p-2.5 rounded-lg bg-muted text-primary">
              <Crown className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-sm">{t("subscription.status.freeTitle")}</h3>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                {t("subscription.status.freeDesc")}
              </p>
            </div>
            <Button onClick={onRenew} size="sm" className="shrink-0">
                {t("subscription.status.upgradeNow")}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  const now = Date.now() / 1000
  const isExpired = detail.expire_time > 0 && detail.expire_time < now
  const daysUntilExpire = detail.expire_time > 0 ? Math.ceil((detail.expire_time - now) / 86400) : 0
  const isExpiringSoon = !isExpired && daysUntilExpire <= 7 // 7天内过期视为即将过期
  const expireDate = new Date(detail.expire_time * 1000).toLocaleDateString()

  return (
    <Card className={`border-l-4 ${isExpired ? "border-l-destructive bg-destructive/5" : isExpiringSoon ? "border-l-amber-500 bg-amber-50/50" : "border-l-primary bg-primary/5"}`}>
      <CardContent className="py-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold">{detail.level_name}</span>
              <Badge 
                variant={isExpired ? "destructive" : isExpiringSoon ? "secondary" : "default"} 
                className="text-xs px-1.5 py-0"
              >
                {isExpired ? t("subscription.status.expired") : isExpiringSoon ? t("subscription.status.expiringSoon") : t("subscription.status.active")}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {isExpired ? t("subscription.status.expiredAt") : t("subscription.status.expireAt")}{expireDate}
                {!isExpired && daysUntilExpire > 0 && (
                  <span className={isExpiringSoon ? "text-amber-600 font-medium" : ""}>
                    （{daysUntilExpire} 天）
                  </span>
                )}
              </span>
            </div>
            {/* 续费提醒 */}
            {isExpired ? (
              <div className="flex items-center gap-1.5 text-xs text-destructive mt-1">
                <AlertTriangle className="h-3 w-3" />
                <span>{t("subscription.notice.desc")}</span>
              </div>
            ) : isExpiringSoon && (
              <div className="flex items-center gap-1.5 text-xs text-amber-600 mt-1">
                <AlertTriangle className="h-3 w-3" />
                <span>
                  {daysUntilExpire <= 3 
                    ? t("subscription.renew.urgent", { days: daysUntilExpire })
                    : t("subscription.renew.reminder", { days: daysUntilExpire })
                  }
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
             {!isExpired && onRenew && (
                <Button size="sm" onClick={onRenew} variant={isExpiringSoon ? "default" : "secondary"}>
                  {isExpiringSoon ? t("subscription.status.renewNow") : t("subscription.status.renew")}
                </Button>
             )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
