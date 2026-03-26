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
    <Card className="shadow-none border-border bg-muted/20">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="text-base font-semibold tracking-tight">{t("subscription.quota.title", "AI 配额")}</CardTitle>
            <CardDescription className="text-xs">{t("subscription.quota.description", "实时查看您的 AI 调用额度使用情况")}</CardDescription>
          </div>
          <Zap className="h-5 w-5 text-primary animate-pulse" />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2.5">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-background border border-border shadow-sm text-primary">
                <Zap className="h-4 w-4" />
              </div>
              <span className="font-medium text-sm tracking-tight">{t("subscription.quota.aiQuota", "AI 额度")}</span>
            </div>
            <div className="text-[13px] font-medium">
              {quota.is_unlimited ? (
                <span className="text-primary">{t("subscription.quota.unlimited", "无限额度")}</span>
              ) : (
                <div className="flex items-baseline gap-1">
                  <span className="text-foreground font-bold">{quota.used}</span>
                  <span className="text-muted-foreground/60 font-normal">/</span>
                  <span className="text-muted-foreground">{quota.total}</span>
                </div>
              )}
            </div>
          </div>
          {!quota.is_unlimited && (
            <div className="space-y-1">
              <Progress 
                  value={usagePercent} 
                  className="h-1.5 bg-muted-foreground/10"
              />
              {usagePercent > 80 && (
                <p className="text-[10px] text-destructive font-medium text-right">
                    {t("subscription.quota.lowBalance", "余额不足")}
                </p>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
