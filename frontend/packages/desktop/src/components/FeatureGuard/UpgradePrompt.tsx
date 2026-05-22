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
    browser_control: t("features.browserControl"),
    desktop_control: t("features.desktopControl"),
    mobile_control: t("features.mobileControl"),
    voice: t("features.voice"),
    skill_learning: t("features.skillLearning"),
    wiki_generation: t("features.wikiGeneration"),
    knowledge_base: t("features.knowledgeBase"),
    gantt: t("features.gantt"),
    timesheet: t("features.timesheet"),
  }

  const planName = t(`subscription.plans.${requiredPlan}`)

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
            ? t("subscription.status.expired")
            : t("subscription.status.upgradeNow")}
        </CardTitle>
        <CardDescription>
          {isExpired
            ? t("subscription.notice.desc")
            : t("subscription.plans.desc")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
          <span className="text-sm text-muted-foreground">
            {t("subscription.plans.title")}
          </span>
          <span className="font-medium">{featureNames[feature]}</span>
        </div>

        <div className="flex items-center justify-between p-3 bg-primary/5 rounded-lg border border-primary/20">
          <span className="text-sm text-muted-foreground">
            {t("subscription.quota.aiQuota")}
          </span>
          <span className="font-medium text-primary flex items-center gap-1">
            <Star className="h-4 w-4 fill-primary" />
            {planName}
          </span>
        </div>

        <Button onClick={handleUpgrade} className="w-full">
          {isExpired
            ? t("subscription.status.renew")
            : t("subscription.status.upgradeNow")}
        </Button>

        <p className="text-xs text-center text-muted-foreground">
          {t("subscription.notice.benefits")}
        </p>
      </CardContent>
    </Card>
  )
}
