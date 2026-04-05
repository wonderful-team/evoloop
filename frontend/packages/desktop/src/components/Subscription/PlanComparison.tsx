import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Check, Crown, AlertCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

// 权益数据类型（简单key-value）
type Benefits = Record<string, number | boolean | string>

interface Plan {
  level_id: number
  level_name: string
  price: string
  market_price: string
  description?: string
  privileges?: string[]
  is_current?: boolean
  benefits?: Benefits  // 来自后端的权益数据
  sort?: number        // 等级排序字段，用于判断等级高低
}

interface PlanComparisonProps {
  plans: Plan[]
  currentLevelId?: number
  currentPlanPrice?: number
  onSelect: (levelId: number) => void
  isLoading?: boolean
}

// 简单的权益格式化函数
function formatBenefitValue(key: string, value: any): string {
  if (typeof value === 'boolean') {
    return value ? '✓' : '✗'
  }
  if (key === 'ai_quota' && value === 0) {
    return '无限'
  }
  if (key === 'storage') {
    return `${value}GB`
  }
  return String(value)
}

// 获取权益显示名称（简单映射，可扩展为多语言）
function getBenefitLabel(key: string): string {
  const labels: Record<string, string> = {
    ai_quota: 'AI调用额度',
    ai_advanced: '高级模型',
    code_execution: '代码执行',
    browser_control: '浏览器控制',
    desktop_control: '桌面控制',
    mobile_control: '手机控制',
    voice: '语音交互',
    skill_recording: '技能录制',
    skill_recording_limit: '录制限制',
    mcp: 'MCP服务',
    project_limit: '项目数量',
    gantt: '甘特图',
    timesheet: '工时表',
    storage: '存储空间',
  }
  return labels[key] || key
}

// 权益列表组件（简单遍历）
function BenefitsList({ benefits }: { benefits?: Benefits }) {
  if (!benefits) {
    // 默认展示
    return (
      <ul className="space-y-2 text-[13px] text-muted-foreground">
        <li>• 基础AI功能</li>
        <li>• 标准支持</li>
      </ul>
    )
  }

  // 简单遍历所有权益
  const entries = Object.entries(benefits)
    .filter(([_, value]) => typeof value === 'boolean' ? value : value > 0 || value === '0')
    .slice(0, 6)

  return (
    <ul className="space-y-2">
      {entries.map(([key, value]) => (
        <li key={key} className="flex items-center justify-between text-[13px]">
          <span className="text-muted-foreground">{getBenefitLabel(key)}</span>
          <span className="font-medium">{formatBenefitValue(key, value)}</span>
        </li>
      ))}
    </ul>
  )
}

export const PlanComparison = ({ plans, currentLevelId, currentPlanPrice = 0, onSelect, isLoading }: PlanComparisonProps) => {
  const { t } = useTranslation()

  const currentPrice = currentPlanPrice || parseFloat(plans.find(p => p.level_id === currentLevelId)?.price || "0")
  
  // 获取当前方案的sort排序（用于准确判断等级高低）
  const currentPlan = plans.find(p => p.level_id === currentLevelId)
  const currentSort = currentPlan?.benefits?.sort as number || 0

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {plans.map((plan) => {
        const isCurrent = plan.level_id === currentLevelId
        const isFree = parseFloat(plan.price) === 0
        
        const targetPrice = parseFloat(plan.price)
        const targetSort = plan.benefits?.sort as number || 0

        const hasActiveSubscription = currentPrice > 0

        // 使用多种方式判断是否是降级：
        // 1. 有sort字段时按sort比较（sort越小等级越低）
        // 2. 没有sort时按价格比较
        // 3. 价格和sort都相同时按quota比较
        let isDowngrade = false
        if (hasActiveSubscription && !isCurrent) {
          if (currentSort > 0 && targetSort > 0) {
            // 都有sort，按sort比较
            isDowngrade = targetSort < currentSort
          } else {
            // 按价格比较
            isDowngrade = targetPrice < currentPrice
          }
        }

        return (
          <Card key={plan.level_id} className={`relative flex flex-col transition-all duration-300 ${isCurrent ? "border-primary bg-primary/[0.02] shadow-sm ring-1 ring-primary" : isDowngrade ? "opacity-60 grayscale" : "border-border hover:border-primary/30 hover:bg-muted/10"}`}>
            {isCurrent && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                <Badge variant="default" className="bg-primary text-primary-foreground font-bold px-3 py-0.5 shadow-sm border-none">
                  {t("subscription.plan.current", "当前方案")}
                </Badge>
              </div>
            )}
            
            {isDowngrade && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                <Badge variant="secondary" className="bg-muted text-muted-foreground font-bold px-3 py-0.5 shadow-sm border">
                  <AlertCircle className="h-3 w-3 mr-1" />
                  {t("subscription.plan.downgrade", "无法降级")}
                </Badge>
              </div>
            )}
            
            <CardHeader className="space-y-1.5 pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-bold tracking-tight">{plan.level_name}</CardTitle>
                {!isFree && (
                    <div className="p-1.5 rounded-full bg-primary/10 text-primary">
                        <Crown className="h-4 w-4" />
                    </div>
                )}
              </div>
              <div className="flex items-baseline gap-1.5 py-2">
                {parseFloat(plan.price) === 0 ? (
                  <span className="text-3xl font-bold tracking-tighter text-primary">{t("subscription.plan.free", "免费")}</span>
                ) : (
                  <>
                    <span className="text-3xl font-bold tracking-tighter">¥{plan.price}</span>
                    <span className="text-[13px] text-muted-foreground font-medium">{t("subscription.plan.perMonth", "/月")}</span>
                  </>
                )}
              </div>
              
              {parseFloat(plan.market_price) > parseFloat(plan.price) && parseFloat(plan.price) > 0 && (
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

            <CardContent className="flex-1 flex flex-col gap-4">
              <p className="text-[13px] text-muted-foreground leading-relaxed">
                {plan.description || t("subscription.plan.defaultDesc", "解锁高级 AI 功能")}
              </p>
              
              <div className="space-y-3">
                <p className="text-[11px] font-bold text-muted-foreground/80 uppercase tracking-widest">
                    {t("subscription.plan.featuresInclude", "包含权益")}
                </p>
                <BenefitsList benefits={plan.benefits} />
              </div>
            </CardContent>

            <CardFooter className="pt-4 flex flex-col gap-2">
              {isDowngrade ? (
                // 降级选项：不显示按钮，显示提示信息
                <div className="w-full py-3 px-4 bg-muted/50 rounded-lg text-center">
                  <p className="text-sm text-muted-foreground font-medium">
                    {t("subscription.plan.cannotDowngrade", "当前等级更高")}
                  </p>
                  <p className="text-[11px] text-muted-foreground/70 mt-1">
                    {t("subscription.plan.downgradeHint", "到期后可购买此方案")}
                  </p>
                </div>
              ) : (
                // 正常选项：显示按钮
                <>
                  <Button 
                    variant={isCurrent ? "outline" : "default"}
                    className={`w-full h-10 font-bold transition-all ${
                      isCurrent 
                        ? "border-primary/20 text-primary hover:bg-primary/5" 
                        : "bg-primary hover:bg-primary/90 shadow-md shadow-primary/10"
                    }`}
                    disabled={isCurrent || isLoading}
                    onClick={() => !isCurrent && onSelect(plan.level_id)}
                  >
                    {isCurrent 
                      ? t("subscription.plan.active", "当前使用中") 
                      : isFree 
                        ? t("subscription.plan.startFree", "立即使用")
                        : t("subscription.plan.subscribe", "立即订阅")
                    }
                  </Button>
                  {!isFree && !isCurrent && hasActiveSubscription && (
                    <p className="text-[11px] text-muted-foreground text-center">
                      {t("subscription.plan.upgradeRefund")}
                    </p>
                  )}
                </>
              )}
            </CardFooter>
          </Card>
        )
      })}
    </div>
  )
}
