/**
 * HumanInputDialog - Human-in-the-Loop Dialog Component
 *
 * Displays pending human input requests and collects user responses.
 * Supports text input, choice selection, confirmation, and approval flows.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  MessageCircleQuestion,
  Shield,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import type { HumanInputRequestOut as HumanInputRequest } from "@/client/types.gen"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Textarea } from "@/components/ui/textarea"

interface HumanInputDialogProps {
  threadId?: string
  // Polling interval in milliseconds
  pollInterval?: number
}

export function HumanInputDialog({
  threadId,
  pollInterval = 3000,
}: HumanInputDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [isOpen, setIsOpen] = useState(false)
  const [currentRequest, setCurrentRequest] =
    useState<HumanInputRequest | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [selectedOption, setSelectedOption] = useState("")

  // Poll for pending requests
  const { data: pendingRequests } = useQuery({
    queryKey: ["human-requests", threadId],
    queryFn: async () => {
      const res = await LearningService.listPendingRequests({ threadId })
      return res
    },
    refetchInterval: pollInterval,
    enabled: true,
  })

  // Show dialog when a new request comes in
  useEffect(() => {
    if (pendingRequests && pendingRequests.length > 0) {
      const firstRequest = pendingRequests[0]
      if (!currentRequest || currentRequest.id !== firstRequest.id) {
        setCurrentRequest(firstRequest)
        setIsOpen(true)
        // Reset input
        setInputValue(firstRequest.default_value || "")
        setSelectedOption("")
      }
    }
  }, [pendingRequests, currentRequest])

  // Submit response mutation
  const respondMutation = useMutation({
    mutationFn: async (response: string) => {
      if (!currentRequest) throw new Error("No current request")
      return LearningService.respondToRequest({
        requestId: currentRequest.id,
        requestBody: { response },
      })
    },
    onSuccess: () => {
      toast.success(t("learning.responseSubmitted", "Response submitted"))
      setIsOpen(false)
      setCurrentRequest(null)
      queryClient.invalidateQueries({ queryKey: ["human-requests"] })
    },
    onError: (error) => {
      toast.error(t("learning.responseFailed", "Failed to submit response"))
      console.error("Response error:", error)
    },
  })

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!currentRequest) throw new Error("No current request")
      return LearningService.cancelPendingRequest({
        requestId: currentRequest.id,
      })
    },
    onSuccess: () => {
      toast.info(t("learning.requestCancelled", "Request cancelled"))
      setIsOpen(false)
      setCurrentRequest(null)
      queryClient.invalidateQueries({ queryKey: ["human-requests"] })
    },
  })

  const handleSubmit = () => {
    if (!currentRequest) return

    let response = ""
    switch (currentRequest.request_type) {
      case "text":
        response = inputValue
        break
      case "choice":
        response = selectedOption
        break
      case "confirmation":
        // Will be handled by button click
        break
      case "approval":
        // Will be handled by button click
        break
    }

    if (response || currentRequest.request_type === "confirmation") {
      respondMutation.mutate(response)
    }
  }

  const handleConfirm = (value: string) => {
    respondMutation.mutate(value)
  }

  if (!currentRequest) return null

  const getIcon = () => {
    switch (currentRequest.request_type) {
      case "approval":
        return <Shield className="h-6 w-6 text-orange-500" />
      case "confirmation":
        return <MessageCircleQuestion className="h-6 w-6 text-blue-500" />
      default:
        return <MessageCircleQuestion className="h-6 w-6 text-primary" />
    }
  }

  const getRiskBadge = () => {
    if (currentRequest.request_type !== "approval") return null

    const riskMatch = currentRequest.context?.match(/Risk Level[:\s]+(\w+)/i)
    if (!riskMatch) return null

    const risk = riskMatch[1].toLowerCase()
    const variants: Record<string, "default" | "secondary" | "destructive"> = {
      low: "secondary",
      medium: "default",
      high: "destructive",
      critical: "destructive",
    }

    return (
      <Badge variant={variants[risk] || "default"} className="ml-2">
        {risk.toUpperCase()}
      </Badge>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {getIcon()}
            <span>
              {currentRequest.request_type === "approval"
                ? t("learning.approvalRequired", "Approval Required")
                : t("learning.inputRequired", "Input Required")}
            </span>
            {getRiskBadge()}
          </DialogTitle>
          <DialogDescription className="whitespace-pre-wrap">
            {currentRequest.prompt}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Context */}
          {currentRequest.context && (
            <div className="mb-4 p-3 bg-muted rounded-md text-sm whitespace-pre-wrap">
              {currentRequest.context}
            </div>
          )}

          {/* Text Input */}
          {currentRequest.request_type === "text" && (
            <Textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={t(
                "learning.enterResponse",
                "Enter your response...",
              )}
              className="min-h-[100px]"
            />
          )}

          {/* Choice Selection */}
          {currentRequest.request_type === "choice" &&
            currentRequest.options && (
              <RadioGroup
                value={selectedOption}
                onValueChange={setSelectedOption}
              >
                {currentRequest.options.map((option, idx) => (
                  <div key={idx} className="flex items-center space-x-2">
                    <RadioGroupItem value={option} id={`option-${idx}`} />
                    <Label htmlFor={`option-${idx}`}>{option}</Label>
                  </div>
                ))}
              </RadioGroup>
            )}
        </div>

        <DialogFooter className="gap-2">
          {/* Confirmation/Approval buttons */}
          {(currentRequest.request_type === "confirmation" ||
            currentRequest.request_type === "approval") && (
            <>
              <Button
                variant="outline"
                onClick={() =>
                  handleConfirm(
                    currentRequest.request_type === "approval"
                      ? "REJECTED"
                      : "no",
                  )
                }
                disabled={respondMutation.isPending}
              >
                <XCircle className="h-4 w-4 mr-2" />
                {currentRequest.request_type === "approval"
                  ? t("learning.reject", "Reject")
                  : t("common.no", "No")}
              </Button>
              <Button
                onClick={() =>
                  handleConfirm(
                    currentRequest.request_type === "approval"
                      ? "APPROVED"
                      : "yes",
                  )
                }
                disabled={respondMutation.isPending}
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                {currentRequest.request_type === "approval"
                  ? t("learning.approve", "Approve")
                  : t("common.yes", "Yes")}
              </Button>
            </>
          )}

          {/* Text/Choice submit */}
          {(currentRequest.request_type === "text" ||
            currentRequest.request_type === "choice") && (
            <>
              <Button
                variant="ghost"
                onClick={() => cancelMutation.mutate()}
                disabled={respondMutation.isPending || cancelMutation.isPending}
              >
                {t("common.cancel", "Cancel")}
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={
                  respondMutation.isPending ||
                  (currentRequest.request_type === "text" &&
                    !inputValue.trim()) ||
                  (currentRequest.request_type === "choice" && !selectedOption)
                }
              >
                {t("common.submit", "Submit")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
