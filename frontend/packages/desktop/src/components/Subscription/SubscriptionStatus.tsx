import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Calendar, Crown, ShieldCheck } from "lucide-react"
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
  onManage: () => void
}

export const SubscriptionStatus = ({ detail, isLoading, onManage }: SubscriptionStatusProps) => {
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
              <h3 className="font-medium text-sm">{t("subscription.status.freeTitle", "当前为普通会员")}</h3>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                {t("subscription.status.freeDesc", "升级到 Pro 解锁更强大的 AI 能力")}
              </p>
            </div>
            <Button onClick={onManage} size="sm" className="shrink-0">
                {t("subscription.status.upgradeNow", "立即升级")}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  const isExpired = detail.expire_time > 0 && detail.expire_time < Date.now() / 1000
  const expireDate = new Date(detail.expire_time * 1000).toLocaleDateString()

  return (
    <Card className={`border-l-4 ${isExpired ? "border-l-destructive bg-destructive/5" : "border-l-primary bg-primary/5"}`}>
      <CardContent className="py-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold">{detail.level_name}</span>
              <Badge 
                variant={isExpired ? "destructive" : "default"} 
                className="text-xs px-1.5 py-0"
              >
                {isExpired ? t("subscription.status.expired", "已过期") : t("subscription.status.active", "生效中")}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {isExpired ? t("subscription.status.expiredAt", "过期：") : t("subscription.status.expireAt", "至 ")}{expireDate}
              </span>
              {detail.is_auto_renew && (
                <span className="flex items-center gap-1 text-primary">
                  <span className="w-1 h-1 rounded-full bg-primary" />
                  {t("subscription.status.autoRenewOn", "自动续费")}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
             <Button variant="outline" size="sm" onClick={onManage}>
                {t("subscription.status.manage", "管理")}
             </Button>
             {!isExpired && (
                <Button size="sm">{t("subscription.status.renew", "续费")}</Button>
             )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
