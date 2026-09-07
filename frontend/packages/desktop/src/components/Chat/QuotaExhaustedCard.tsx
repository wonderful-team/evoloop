import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { useNavigate } from "@tanstack/react-router"
import { AlertTriangle, ExternalLink, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useAgentStore } from "@/stores/agentStore"
import { useChatStore } from "@/stores/chatStore"

/**
 * QuotaExhaustedCard - Interactive card when LLM quota is exhausted
 * Similar to HumanRequestCard but for quota exhaustion
 * Provides actions to check quota or continue after recharging
 */
export function QuotaExhaustedCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const quotaInfo = useAgentStore((s) => s.quotaExhaustedInfo)
  const status = useAgentStore((s) => s.status)
  const sendMessage = useChatStore((s) => s.sendMessage)

  // Only show when quota is exhausted
  if (status !== "quota_exhausted") return null

  const handleCheckQuota = () => {
    // Navigate to subscription page using TanStack Router
    navigate({ to: "/subscription" })
  }

  const handleContinue = async () => {
    // Send a "continue" message via normal chat flow
    // If quota is still exhausted, backend will return error and card will reappear
    const prompt = t("chat.quota.continuePrompt")
    await sendMessage(prompt || t("common.continue"))
  }

  return (
    <Card className="w-full my-2 border-destructive/30 bg-destructive/5 shadow-sm animate-in fade-in slide-in-from-bottom-2">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2 text-destructive">
          <AlertTriangle className="h-4 w-4" />
          {quotaInfo?.title || t("chat.quota.card.title")}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Main Message */}
        <div className="font-medium text-foreground">
          {quotaInfo?.message || t("chat.quota.card.message")}
        </div>

        {/* Hint */}
        {quotaInfo?.hint && (
          <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-md">
            {quotaInfo.hint}
          </div>
        )}

        {/* Info Box */}
        <div className="text-sm text-muted-foreground">
          <p>{t("chat.quota.card.info")}</p>
          <ul className="list-disc list-inside mt-1 space-y-1">
            <li>{t("chat.quota.card.option1")}</li>
            <li>{t("chat.quota.card.option2")}</li>
          </ul>
        </div>
      </CardContent>

      <CardFooter className="flex gap-2 pt-2">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 border-destructive/30 hover:bg-destructive/10"
          onClick={handleCheckQuota}
        >
          <ExternalLink className="h-4 w-4 mr-2" />
          {quotaInfo?.actionText || t("chat.quota.card.checkQuota")}
        </Button>
        <Button
          variant="default"
          size="sm"
          className="flex-1 bg-destructive hover:bg-destructive/90 text-white"
          onClick={handleContinue}
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          {t("chat.quota.card.continue")}
        </Button>
      </CardFooter>
    </Card>
  )
}
