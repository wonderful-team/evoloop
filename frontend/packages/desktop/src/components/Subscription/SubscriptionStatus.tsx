import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent } from "@evoloop/shared/components/ui/card"
import { Progress } from "@evoloop/shared/components/ui/progress"
import { AlertTriangle, Calendar, Crown, Zap } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { AiQuota, SubscriptionDetail } from "@/types/subscription"

interface SubscriptionStatusProps {
  detail?: SubscriptionDetail
  quota?: AiQuota
  isLoading?: boolean
  onRenew?: () => void
  onUpgrade?: () => void
}

export const SubscriptionStatus = ({
  detail,
  quota,
  isLoading,
  onRenew,
  onUpgrade,
}: SubscriptionStatusProps) => {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <Card className="border-border bg-muted/30 animate-pulse">
        <div className="h-32" />
      </Card>
    )
  }

  const renderQuota = () => {
    if (!quota) return null
    const rawPercent = quota.is_unlimited ? 0 : (quota.used / quota.total) * 100
    const usagePercent = Math.min(100, rawPercent)

    return (
      <div className="flex-1 flex flex-col gap-2 px-4 lg:px-12">
        <div className="flex items-center justify-between mb-0.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            <Zap className="h-3.5 w-3.5 text-primary" />
            <span>{t("subscription.quota.aiQuota")}</span>
          </div>
          <div className="text-[11px] font-bold">
            {quota.is_unlimited ? (
              <span className="text-primary text-sm">
                {t("subscription.quota.unlimited")}
              </span>
            ) : (
              <div className="flex items-baseline gap-1">
                <span className="text-base font-black text-foreground">
                  {quota.remaining}
                </span>
                <span className="text-muted-foreground font-normal text-[10px]">
                  / {quota.total}
                </span>
              </div>
            )}
          </div>
        </div>
        {!quota.is_unlimited && (
          <div className="space-y-1.5">
            <Progress
              value={usagePercent}
              className="h-2 shadow-inner bg-muted/50"
            />
            <div className="flex justify-between text-[10px] font-medium text-muted-foreground">
              <span>
                {t("subscription.quota.usedPercent", {
                  percent: Math.round(rawPercent),
                })}
              </span>
              {usagePercent >= 80 && (
                <span className="text-destructive font-bold animate-pulse">
                  {t("subscription.quota.lowBalance")}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  const isFreeUser = !detail || detail.status === "none" || !detail.is_member
  if (isFreeUser) {
    return (
      <Card className="border-border bg-card overflow-hidden">
        <CardContent className="py-6 px-8">
          <div className="flex flex-col lg:flex-row lg:items-center gap-8">
            <div className="flex items-center gap-6 shrink-0">
              <div className="p-3 rounded-xl bg-primary/5 text-primary ring-1 ring-primary/10">
                <Crown className="h-6 w-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-base tracking-tight">
                  {t("subscription.status.freeTitle")}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                  {t("subscription.status.freeDesc")}
                </p>
              </div>
              <Button
                onClick={onRenew}
                size="sm"
                className="h-9 px-6 font-bold shadow-sm shadow-primary/10 transition-all hover:scale-[1.02] active:scale-95"
              >
                {t("subscription.status.upgradeNow")}
              </Button>
            </div>

            {renderQuota()}
          </div>
        </CardContent>
      </Card>
    )
  }

  const now = Date.now() / 1000
  const isExpired = detail.expire_time > 0 && detail.expire_time < now
  const daysUntilExpire =
    detail.expire_time > 0 ? Math.ceil((detail.expire_time - now) / 86400) : 0
  const isExpiringSoon = !isExpired && daysUntilExpire <= 7
  const expireDate = new Date(detail.expire_time * 1000).toLocaleDateString()

  return (
    <Card
      className={`border-l-4 overflow-hidden transition-all duration-300 ${isExpired ? "border-l-destructive bg-destructive/5" : isExpiringSoon ? "border-l-amber-500 bg-amber-50/50" : "border-l-primary bg-primary/5"}`}
    >
      <CardContent className="py-7 px-10">
        <div className="flex flex-col lg:flex-row lg:items-center gap-10">
          {/* Left: Status Info */}
          <div className="flex flex-col space-y-1.5 shrink-0 min-w-[180px]">
            <div className="flex items-center gap-3">
              <span className="text-xl font-black tracking-tighter text-foreground">
                {detail.level_name}
              </span>
              <Badge
                variant={
                  isExpired
                    ? "destructive"
                    : isExpiringSoon
                      ? "secondary"
                      : "default"
                }
                className="text-[10px] px-2 py-0 font-bold uppercase"
              >
                {isExpired
                  ? t("subscription.status.expired")
                  : isExpiringSoon
                    ? t("subscription.status.expiringSoon")
                    : t("subscription.status.active")}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground font-medium">
              <span className="flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5" />
                {isExpired
                  ? t("subscription.status.expiredAt")
                  : t("subscription.status.expireAt")}
                {expireDate}
                {!isExpired && daysUntilExpire > 0 && (
                  <span
                    className={
                      isExpiringSoon
                        ? "text-amber-600 font-bold"
                        : "text-primary/70 font-bold"
                    }
                  >
                    {t("subscription.status.daysRemaining", {
                      days: daysUntilExpire,
                    })}
                  </span>
                )}
              </span>
            </div>
            {isExpired ? (
              <div className="flex items-center gap-1.5 text-xs text-destructive mt-1 font-bold">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>{t("subscription.notice.desc")}</span>
              </div>
            ) : (
              isExpiringSoon && (
                <div className="flex items-center gap-1.5 text-xs text-amber-600 mt-1 font-bold">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span>
                    {daysUntilExpire <= 3
                      ? t("subscription.renew.urgent", {
                          days: daysUntilExpire,
                        })
                      : t("subscription.renew.reminder", {
                          days: daysUntilExpire,
                        })}
                  </span>
                </div>
              )
            )}
          </div>

          {/* Middle: AI Quota (fills the gap) */}
          {renderQuota()}

          {/* Right: Action */}
          {!isExpired && (
            <div className="shrink-0">
              {detail.level_id === 1 && onUpgrade ? (
                <Button
                  size="sm"
                  onClick={onUpgrade}
                  className="h-10 px-6 font-black shadow-sm shadow-primary/10 transition-all hover:scale-[1.02] active:scale-95"
                >
                  {t("subscription.status.upgradeNow")}
                </Button>
              ) : onRenew ? (
                <Button
                  size="sm"
                  onClick={onRenew}
                  variant={isExpiringSoon ? "default" : "secondary"}
                  className={`h-10 px-6 font-black shadow-sm transition-all hover:scale-[1.02] active:scale-95 ${
                    isExpiringSoon
                      ? "bg-amber-500 hover:bg-amber-600 text-white"
                      : ""
                  }`}
                >
                  {isExpiringSoon
                    ? t("subscription.status.renewNow")
                    : t("subscription.status.renew")}
                </Button>
              ) : null}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
