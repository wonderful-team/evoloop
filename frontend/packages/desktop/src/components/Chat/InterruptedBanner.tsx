/**
 * InterruptedBanner - Displays a banner when Agent is paused for human input
 *
 * Shows resume/cancel controls when the agent status is 'interrupted'
 */

import { AlertCircle, Play, XCircle } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { useChatStore } from "@/stores/chatStore"

export function InterruptedBanner() {
  const { t } = useTranslation()
  const status = useChatStore((s) => s.status)
  const resumeAgent = useChatStore((s) => s.resumeAgent)
  const stopAgent = useChatStore((s) => s.stopAgent)

  const [showInput, setShowInput] = useState(false)
  const [userInput, setUserInput] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (status !== "interrupted") return null

  const handleResume = async () => {
    setIsSubmitting(true)
    try {
      await resumeAgent(showInput ? userInput : undefined)
      setShowInput(false)
      setUserInput("")
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCancel = async () => {
    setIsSubmitting(true)
    try {
      await stopAgent()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mx-4 mb-4 animate-in fade-in slide-in-from-top-2">
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm text-foreground">
            {t("chat.interrupted.title", "Agent Paused")}
          </h4>
          <p className="text-xs text-muted-foreground mt-1">
            {t(
              "chat.interrupted.description",
              "The agent is waiting for your input or confirmation to continue.",
            )}
          </p>

          {/* Optional Input Area */}
          {showInput && (
            <div className="mt-3">
              <Textarea
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                placeholder={t(
                  "chat.interrupted.inputPlaceholder",
                  "Enter additional instructions (optional)...",
                )}
                className="text-sm min-h-[60px]"
              />
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center gap-2 mt-3">
            <Button
              size="sm"
              onClick={handleResume}
              disabled={isSubmitting}
              className="gap-1.5"
            >
              <Play className="h-3.5 w-3.5" />
              {t("chat.interrupted.resume", "Resume")}
            </Button>

            {!showInput && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowInput(true)}
                disabled={isSubmitting}
              >
                {t("chat.interrupted.addInput", "Add Instructions")}
              </Button>
            )}

            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancel}
              disabled={isSubmitting}
              className="gap-1.5 text-destructive hover:text-destructive"
            >
              <XCircle className="h-3.5 w-3.5" />
              {t("chat.interrupted.cancel", "Cancel")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
