import { Progress } from "@evoloop/shared/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@evoloop/shared/components/ui/card"
import { Zap } from "lucide-react"
import { useTranslation } from "react-i18next"

interface QuotaInfo {
  total: number
  used: number
  remaining: number
  is_unlimited: boolean
}

interface QuotaCardProps {
  quota: QuotaInfo
}

export const QuotaCard = ({ quota }: QuotaCardProps) => {
  const { t } = useTranslation()

  if (!quota) return null

  const usagePercent = quota.is_unlimited ? 0 : (quota.used / quota.total) * 100

  return (
    <Card className="h-full border-border bg-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">{t("subscription.quota.title", "AI 配额")}</CardTitle>
          <Zap className="h-4 w-4 text-primary" />
        </div>
        <CardDescription className="text-xs">{t("subscription.quota.description", "实时查看额度使用情况")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-primary/10 text-primary">
              <Zap className="h-3.5 w-3.5" />
            </div>
            <span className="text-sm font-medium">{t("subscription.quota.aiQuota", "剩余额度")}</span>
          </div>
          <div className="text-sm font-semibold">
            {quota.is_unlimited ? (
              <span className="text-primary">{t("subscription.quota.unlimited", "无限")}</span>
            ) : (
              <span className="text-foreground">{quota.remaining} <span className="text-muted-foreground font-normal text-xs">/ {quota.total}</span></span>
            )}
          </div>
        </div>
        
        {!quota.is_unlimited && (
          <div className="space-y-1.5">
            <Progress value={usagePercent} className="h-1.5" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{Math.round(usagePercent)}% 已使用</span>
              {usagePercent > 80 && (
                <span className="text-destructive font-medium">余额不足</span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
