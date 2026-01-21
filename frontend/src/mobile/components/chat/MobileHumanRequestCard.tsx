import { AlertTriangle, Check, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface HumanRequestProps {
    request: {
        id: string
        type: "text" | "approval"
        prompt: string
        options?: string[]
        default_value?: string
        context?: {
            risk_level?: "low" | "medium" | "high" | "critical"
            action_description?: string
            details?: string
            consequences?: string
        }
    }
    onRespond: (value: string) => void
}

export function MobileHumanRequestCard({ request, onRespond }: HumanRequestProps) {
    const { t } = useTranslation()
    const [value, setValue] = useState(request.default_value || "")
    const [isSubmitting, setIsSubmitting] = useState(false)

    const handleSubmit = (response: string) => {
        setIsSubmitting(true)
        onRespond(response)
    }

    const isHighRisk = request.context?.risk_level === "high" || request.context?.risk_level === "critical"

    return (
        <Card className={cn(
            "w-full max-w-[90%] mb-4 border-l-4 shadow-md overflow-hidden animate-in zoom-in-95 duration-300",
            isHighRisk ? "border-l-red-500 bg-red-50/50 dark:bg-red-950/10" : "border-l-blue-500 bg-blue-50/50 dark:bg-blue-950/10"
        )}>
            <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                        {isHighRisk && <AlertTriangle className="w-4 h-4 text-red-500" />}
                        {request.context?.action_description || t("hitl.approvalRequired")}
                    </CardTitle>
                </div>
                <CardDescription className="text-xs mt-1">
                    {request.prompt}
                </CardDescription>
            </CardHeader>

            <CardContent className="pb-2 text-sm space-y-3">
                {/* Helper Details */}
                {request.context?.details && (
                    <div className="bg-background/80 p-3 rounded-md text-muted-foreground whitespace-pre-wrap text-xs font-mono max-h-[200px] overflow-y-auto border">
                        {request.context.details}
                    </div>
                )}

                {/* Consequences Warning */}
                {request.context?.consequences && (
                    <div className="flex gap-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 rounded-md border border-amber-200 dark:border-amber-900">
                        <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                        <span>{request.context.consequences}</span>
                    </div>
                )}

                {/* Input for Text Type */}
                {request.type === "text" && (
                    <Textarea
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        placeholder={t("hitl.enterResponse")}
                        className="min-h-[80px]"
                    />
                )}
            </CardContent>

            <CardFooter className="flex justify-end gap-2 pt-2">
                {request.type === "approval" ? (
                    <>
                        <Button
                            variant="outline"
                            size="sm"
                            className="border-red-200 hover:bg-red-100 hover:text-red-700 dark:border-red-900 dark:hover:bg-red-900/30"
                            onClick={() => handleSubmit("REJECTED")}
                            disabled={isSubmitting}
                        >
                            <X className="w-4 h-4 mr-1" />
                            {t("common.reject")}
                        </Button>
                        <Button
                            size="sm"
                            className={cn(
                                isHighRisk ? "bg-red-600 hover:bg-red-700" : "bg-primary hover:bg-primary/90"
                            )}
                            onClick={() => handleSubmit("APPROVED")}
                            disabled={isSubmitting}
                        >
                            <Check className="w-4 h-4 mr-1" />
                            {t("common.approve")}
                        </Button>
                    </>
                ) : (
                    <Button
                        size="sm"
                        onClick={() => handleSubmit(value)}
                        disabled={!value.trim() || isSubmitting}
                    >
                        {t("common.submit")}
                    </Button>
                )}
            </CardFooter>
        </Card>
    )
}
