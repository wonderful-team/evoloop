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
      <Card className="border-border bg-muted/30">
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-background border shadow-sm text-primary">
              <Crown className="h-6 w-6" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-base tracking-tight">{t("subscription.status.freeTitle", "当前为普通会员")}</h3>
              <p className="text-sm text-muted-foreground mt-0.5">
                {t("subscription.status.freeDesc", "升级到 Pro 以解锁更强大的 AI 模型和无限制功能")}
              </p>
            </div>
            <Button onClick={onManage} size="sm" className="bg-primary hover:bg-primary/90">
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
    <Card className={`border-border ${isExpired ? "bg-destructive/5" : "bg-primary/5"} relative overflow-hidden`}>
      {/* Decorative Background Element */}
      <div className="absolute top-0 right-0 p-8 opacity-10 translate-x-1/4 -translate-y-1/4">
         <Crown className="h-32 w-32" />
      </div>

      <CardHeader className="pb-3 relative">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-lg font-bold tracking-tight">{detail.level_name}</CardTitle>
            <Badge 
              variant={isExpired ? "destructive" : "secondary"} 
              className={isExpired ? "" : "bg-primary/20 text-primary border-primary/20"}
            >
              {isExpired ? t("subscription.status.expired", "已过期") : t("subscription.status.active", "尊贵会员")}
            </Badge>
          </div>
          <ShieldCheck className={`h-6 w-6 ${isExpired ? "text-muted-foreground" : "text-primary"}`} />
        </div>
      </CardHeader>
      <CardContent className="relative">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground font-medium">
              <Calendar className="h-3.5 w-3.5" />
              <span>{isExpired ? t("subscription.status.expiredAt", "过期时间：") : t("subscription.status.expireAt", "有效期至：")}{expireDate}</span>
            </div>
            {detail.is_auto_renew && (
              <div className="flex items-center gap-2 text-xs text-primary/80 font-medium">
                <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                <span>{t("subscription.status.autoRenewOn", "已开启自动续费")}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
             <Button variant="outline" size="sm" onClick={onManage} className="h-8 border-primary/20 hover:bg-primary/5 text-primary">
                {t("subscription.status.manage", "管理订阅")}
             </Button>
             {!isExpired && (
                <Button size="sm" className="h-8 bg-primary hover:bg-primary/90">
                    {t("subscription.status.renew", "立即续费")}
                </Button>
             )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
