import { Play, XCircle, CheckCircle2, MessageCircleQuestion, Ban } from "lucide-react"
import { useState } from "react"
import { MessageContent } from "./MessageContent"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { RadioGroup, RadioGroupItem } from "@evoloop/shared/components/ui/radio-group"
import { Label } from "@evoloop/shared/components/ui/label"
import { useChatStore } from "@/stores/chatStore"

export interface HumanRequestCardProps {
    request: {
        id: string
        type: "text" | "choice" | "confirmation" | "approval" | "text_input" | "confirm"
        prompt: string
        options?: string[]
        context?: string
    }
}

export function HumanRequestCard({ request }: HumanRequestCardProps) {
    const { t } = useTranslation()
    const resumeAgent = useChatStore((s) => s.resumeAgent)
    const cancelHumanRequest = useChatStore((s) => s.cancelHumanRequest)
    const [input, setInput] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)

    const handleResponse = async (response: string) => {
        setIsSubmitting(true)
        try {
            await resumeAgent(response)
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleCancel = async () => {
        setIsSubmitting(true)
        try {
            await cancelHumanRequest()
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <Card className="w-full my-2 border-amber-500/30 bg-amber-500/5 shadow-sm animate-in fade-in slide-in-from-bottom-2">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2 text-amber-600 dark:text-amber-500">
                    <MessageCircleQuestion className="h-4 w-4" />
                    {t("chat.request.title")}
                </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Prompt */}
                <div className="font-medium">
                    <MessageContent content={request.prompt} />
                </div>

                {/* Context */}
                {request.context && (
                    <div className="bg-background/50 p-2 rounded border overflow-auto">
                        <MessageContent content={request.context} />
                    </div>
                )}

                {/* Inputs based on Type */}

                {/* Text Input */}
                {(request.type === "text" || request.type === "text_input") && (
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={t("chat.request.placeholder", "Enter your response...")}
                        className="min-h-[80px]"
                    />
                )}

                {/* Choice Input */}
                {request.type === "choice" && request.options && (
                    <RadioGroup value={input} onValueChange={setInput}>
                        {request.options.map((opt, i) => (
                            <div key={i} className="flex items-center space-x-2">
                                <RadioGroupItem value={opt} id={`opt-${i}`} />
                                <Label htmlFor={`opt-${i}`}>{opt}</Label>
                            </div>
                        ))}
                    </RadioGroup>
                )}
            </CardContent>

            <CardFooter className="flex justify-end gap-2 pt-0">
                {/* Cancel Button - Available for all request types */}
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancel}
                    disabled={isSubmitting}
                    className="text-muted-foreground hover:text-destructive"
                >
                    <Ban className="mr-2 h-4 w-4" />
                    {t("common.cancel", "Cancel")}
                </Button>

                {/* Standard Submit for Text/Choice */}
                {(request.type === "text" || request.type === "text_input" || request.type === "choice") && (
                    <Button
                        onClick={() => handleResponse(input)}
                        disabled={isSubmitting || !input.trim()}
                        size="sm"
                    >
                        <Play className="mr-2 h-4 w-4" />
                        {t("common.submit", "Submit")}
                    </Button>
                )}

                {/* Confirmation Buttons */}
                {(request.type === "confirmation" || request.type === "confirm" || request.type === "approval") && (
                    <>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleResponse("no")}
                            disabled={isSubmitting}
                            className="text-destructive hover:text-destructive"
                        >
                            <XCircle className="mr-2 h-4 w-4" />
                            {request.type === "approval" ? t("common.reject", "Reject") : t("common.no", "No")}
                        </Button>
                        <Button
                            size="sm"
                            onClick={() => handleResponse("yes")}
                            disabled={isSubmitting}
                        >
                            <CheckCircle2 className="mr-2 h-4 w-4" />
                            {request.type === "approval" ? t("common.approve", "Approve") : t("common.yes", "Yes")}
                        </Button>
                    </>
                )}
            </CardFooter>
        </Card>
    )
}
