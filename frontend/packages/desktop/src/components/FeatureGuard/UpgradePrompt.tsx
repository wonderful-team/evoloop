import { Lock, Star } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import type { FeatureCode } from "@/hooks/useFeatureAccess"

interface UpgradePromptProps {
  feature: FeatureCode
  requiredPlan: string
  isExpired?: boolean
  onClose?: () => void
}

export function UpgradePrompt({
  feature,
  requiredPlan,
  isExpired = false,
  onClose,
}: UpgradePromptProps) {
  const { t } = useTranslation()

  const featureNames: Record<FeatureCode, string> = {
    browser_control: t("features.browserControl", "浏览器控制"),
    desktop_control: t("features.desktopControl", "桌面控制"),
    mobile_control: t("features.mobileControl", "手机控制"),
    voice: t("features.voice", "语音交互"),
    skill_learning: t("features.skillLearning", "技能学习"),
    wiki_generation: t("features.wikiGeneration", "Wiki生成"),
    knowledge_base: t("features.knowledgeBase", "知识库"),
    gantt: t("features.gantt", "甘特图"),
    timesheet: t("features.timesheet", "工时表"),
  }

  const handleUpgrade = () => {
    window.location.href = "/subscription"
  }

  return (
    <Card className="w-full max-w-md mx-auto mt-8">
      <CardHeader className="text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
          <Lock className="h-6 w-6 text-primary" />
        </div>
        <CardTitle>
          {isExpired
            ? t("subscription.expired.title", "订阅已过期")
            : t("subscription.upgrade.title", "需要升级订阅")}
        </CardTitle>
        <CardDescription>
          {isExpired
            ? t("subscription.expired.description", "您的订阅已过期，请续费以继续使用此功能")
            : t("subscription.upgrade.description", "此功能需要更高等级的订阅")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
          <span className="text-sm text-muted-foreground">
            {t("subscription.feature", "功能")}
          </span>
          <span className="font-medium">{featureNames[feature]}</span>
        </div>

        <div className="flex items-center justify-between p-3 bg-primary/5 rounded-lg border border-primary/20">
          <span className="text-sm text-muted-foreground">
            {t("subscription.requiredPlan", "所需套餐")}
          </span>
          <span className="font-medium text-primary flex items-center gap-1">
            <Star className="h-4 w-4 fill-primary" />
            {requiredPlan}
          </span>
        </div>

        <Button onClick={handleUpgrade} className="w-full">
          {isExpired
            ? t("subscription.renew", "立即续费")
            : t("subscription.upgradeNow", "立即升级")}
        </Button>

        <p className="text-xs text-center text-muted-foreground">
          {t("subscription.upgrade.help", "升级后可立即使用此功能")}
        </p>
      </CardContent>
    </Card>
  )
}
