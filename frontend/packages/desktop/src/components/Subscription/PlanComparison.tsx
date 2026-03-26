import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Check, Crown } from "lucide-react"
import { useTranslation } from "react-i18next"

interface Plan {
  level_id: number
  level_name: string
  price: string
  market_price: string
  description?: string
  privileges?: string[]
  is_current?: boolean
}

interface PlanComparisonProps {
  plans: Plan[]
  currentLevelId?: number
  onSelect: (levelId: number) => void
  isLoading?: boolean
}

export const PlanComparison = ({ plans, currentLevelId, onSelect, isLoading }: PlanComparisonProps) => {
  const { t } = useTranslation()

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {plans.map((plan) => {
        const isCurrent = plan.level_id === currentLevelId
        const isPro = plan.level_id > 1

        return (
          <Card key={plan.level_id} className={`relative flex flex-col transition-all duration-300 ${isCurrent ? "border-primary bg-primary/[0.02] shadow-sm ring-1 ring-primary" : "border-border hover:border-primary/30 hover:bg-muted/10"}`}>
            {isCurrent && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                <Badge variant="default" className="bg-primary text-primary-foreground font-bold px-3 py-0.5 shadow-sm border-none">
                  {t("subscription.plan.current", "当前方案")}
                </Badge>
              </div>
            )}
            
            <CardHeader className="space-y-1.5">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-bold tracking-tight">{plan.level_name}</CardTitle>
                {isPro && (
                    <div className="p-1.5 rounded-full bg-primary/10 text-primary">
                        <Crown className="h-4 w-4" />
                    </div>
                )}
              </div>
              <div className="flex items-baseline gap-1.5 py-2">
                <span className="text-3xl font-bold tracking-tighter">¥{plan.price}</span>
                <span className="text-[13px] text-muted-foreground font-medium">{t("subscription.plan.perMonth", "/月")}</span>
              </div>
              {parseFloat(plan.market_price) > parseFloat(plan.price) && (
                <div className="flex items-center gap-2">
                    <span className="line-through text-xs text-muted-foreground/60 italic">
                         ¥{plan.market_price}
                    </span>
                    <Badge variant="outline" className="text-[10px] h-4 px-1 border-primary/20 text-primary bg-primary/5">
                        {t("subscription.plan.discount", "限时优惠")}
                    </Badge>
                </div>
              )}
            </CardHeader>

            <CardContent className="flex-1 flex flex-col gap-6">
              <p className="text-[13px] text-muted-foreground leading-relaxed">
                {plan.description || t("subscription.plan.defaultDesc", "解锁高级 AI 功能，提升工作效率")}
              </p>
              
              <div className="space-y-3">
                <p className="text-[11px] font-bold text-muted-foreground/80 uppercase tracking-widest">
                    {t("subscription.plan.featuresInclude", "包含权益")}
                </p>
                <ul className="space-y-3">
                    {(plan.privileges || [
                        t("subscription.privilege.unlimitedChat", "无限制智能对话"),
                        t("subscription.privilege.advancedModels", "访问 Claude 3.5 & GPT-4o"),
                        t("subscription.privilege.codeAnalysis", "深度代码审计与分析"),
                        t("subscription.privilege.cloudSync", "跨设备实时同步")
                    ]).map((privilege, idx) => (
                    <li key={idx} className="flex items-start gap-2.5 text-[13px] text-foreground/90">
                        <div className="mt-1 rounded-full bg-primary/10 p-0.5">
                            <Check className="h-3 w-3 text-primary shrink-0" />
                        </div>
                        <span className="leading-snug">{privilege}</span>
                    </li>
                    ))}
                </ul>
              </div>
            </CardContent>

            <CardFooter className="pt-4">
              <Button 
                variant={isCurrent ? "outline" : "default"}
                className={`w-full h-10 font-bold transition-all ${isCurrent ? "border-primary/20 text-primary hover:bg-primary/5" : "bg-primary hover:bg-primary/90 shadow-md shadow-primary/10"}`}
                disabled={isCurrent || isLoading}
                onClick={() => onSelect(plan.level_id)}
              >
                {isCurrent ? t("subscription.plan.active", "当前使用中") : t("subscription.plan.upgrade", "立即升级")}
              </Button>
            </CardFooter>
          </Card>
        )
      })}
    </div>
  )
}
