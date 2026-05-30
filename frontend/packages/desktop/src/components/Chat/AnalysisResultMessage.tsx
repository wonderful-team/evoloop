/**
 * Analysis Result Message Component
 *
 * This component wraps AnalysisResultCard and handles interactions with
 * the requirement store for confirming analysis and requesting changes.
 */

import { useTranslation } from "react-i18next"
import {
  AnalysisResultCard,
  type AnalysisData,
} from "../Projects/Requirements/AnalysisResultCard"
import { useRequirementStore } from "@/stores/requirementStore"
import { useChatStore } from "@/stores/chatStore"
import { toast } from "sonner"

interface AnalysisResultMessageProps {
  analysisId: string
  documentId: string
  projectId: number
  data: AnalysisData
}

export function AnalysisResultMessage({
  analysisId,
  documentId,
  projectId,
  data,
}: AnalysisResultMessageProps) {
  const { t } = useTranslation()
  const { confirmAnalysis, requestAnalysisChanges } = useRequirementStore()
  const sendMessage = useChatStore(s => s.sendMessage)

  const handleConfirm = async (modifications?: Partial<AnalysisData>) => {
    // First, confirm the analysis via API
    const success = await confirmAnalysis(
      projectId,
      documentId,
      analysisId,
      modifications
    )

    if (success) {
      // Send a follow-up message to trigger task breakdown
      const confirmMessage = modifications
        ? t(
            "requirements.analysis.confirmedWithModifications",
            "我已确认分析结果并进行了修改，请继续拆解任务。"
          )
        : t(
            "requirements.analysis.confirmed",
            "我已确认分析结果，请继续拆解任务。"
          )

      await sendMessage(confirmMessage)
    }
  }

  const handleRequestChanges = async (feedback: string) => {
    // Submit feedback via API
    const success = await requestAnalysisChanges(
      projectId,
      documentId,
      analysisId,
      feedback
    )

    if (success) {
      // Send a follow-up message to trigger re-analysis
      await sendMessage(
        t(
          "requirements.analysis.requestingChanges",
          "我对分析结果有一些修改意见：{{feedback}}，请重新分析。",
          { feedback }
        )
      )
    }
  }

  return (
    <AnalysisResultCard
      analysisId={analysisId}
      data={data}
      onConfirm={handleConfirm}
      onRequestChanges={handleRequestChanges}
    />
  )
}
