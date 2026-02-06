import { Play, XCircle, CheckCircle2, MessageCircleQuestion, AlertTriangle } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { RadioGroup, RadioGroupItem } from "@evoloop/shared/components/ui/radio-group"
import { Label } from "@evoloop/shared/components/ui/label"
import { cn } from "@evoloop/shared"

interface HumanRequestProps {
    request: {
        id: string
        type: "text" | "choice" | "confirmation" | "approval"
        prompt: string
        options?: string[]
        default_value?: string
        context?: string | {
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

    // Unified theme: Desktop uses Amber for all HITL
    const cardTheme = "border-amber-500/30 bg-amber-500/5 dark:bg-amber-500/10"
    const titleColor = "text-amber-600 dark:text-amber-500"

    // Risk level might still be passed in context object for some flows
    const riskLevel = typeof request.context === 'object' ? request.context?.risk_level : undefined
    const isHighRisk = riskLevel === "high" || riskLevel === "critical"

    return (
        <Card className={cn(
            "w-full mb-4 border-l-4 shadow-lg overflow-hidden animate-in zoom-in-95 duration-300 rounded-xl",
            isHighRisk ? "border-l-red-500" : "border-l-amber-500",
            cardTheme
        )}>
            <CardHeader className="pb-3 pt-4 px-4">
                <div className="flex items-center justify-between mb-1">
                    <CardTitle className={cn("text-sm font-bold flex items-center gap-2", titleColor)}>
                        <MessageCircleQuestion className="h-4 w-4" />
                        {t("chat.request.title", "Input Required")}
                    </CardTitle>
                    {riskLevel && (
                        <div className={cn(
                            "px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider",
                            isHighRisk ? "bg-red-500 text-white" : "bg-amber-500 text-white"
                        )}>
                            {riskLevel}
                        </div>
                    )}
                </div>

                <div className="text-base font-bold leading-tight mt-1">
                    {typeof request.context === 'object' ? request.context?.action_description : ""}
                </div>

                <CardDescription className="text-sm mt-2 text-foreground font-medium leading-relaxed">
                    {request.prompt}
                </CardDescription>
            </CardHeader>

            <CardContent className="pb-3 pt-0 px-4 space-y-4">
                {/* Context / Details with Markdown support */}
                {(typeof request.context === 'string' ? request.context : request.context?.details) && (
                    <div className="bg-background/60 p-3 rounded-lg text-muted-foreground border border-border/50 shadow-inner overflow-x-auto">
                        <div className="prose prose-sm dark:prose-invert max-w-none text-[11px] leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {typeof request.context === 'string' ? request.context : request.context?.details || ""}
                            </ReactMarkdown>
                        </div>
                    </div>
                )}

                {/* Consequences Warning */}
                {typeof request.context === 'object' && request.context?.consequences && (
                    <div className="flex gap-2.5 text-[11px] text-amber-700 dark:text-amber-400 bg-amber-500/10 p-3 rounded-lg border border-amber-500/20 leading-snug">
                        <AlertTriangle className="w-4 h-4 shrink-0 text-amber-500" />
                        <span>{request.context.consequences}</span>
                    </div>
                )}

                {/* Text Input */}
                {request.type === "text" && (
                    <Textarea
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        placeholder={t("chat.request.placeholder", "Enter your response...")}
                        className="min-h-[100px] bg-background/50 text-sm rounded-xl focus-visible:ring-amber-500/20"
                    />
                )}

                {/* Choice Input */}
                {request.type === "choice" && request.options && (
                    <RadioGroup value={value} onValueChange={setValue} className="gap-3">
                        {request.options.map((opt, i) => (
                            <div key={i} className="flex items-center space-x-3 p-3 rounded-lg border border-border/40 bg-background/30 active:bg-background/60 transition-colors">
                                <RadioGroupItem value={opt} id={`opt-${i}`} className="text-amber-600 border-amber-500" />
                                <Label htmlFor={`opt-${i}`} className="flex-1 text-sm font-medium">{opt}</Label>
                            </div>
                        ))}
                    </RadioGroup>
                )}
            </CardContent>

            <CardFooter className="flex flex-col gap-3 pt-2 pb-5 px-4">
                {/* Standard Submit for Text/Choice */}
                {(request.type === "text" || request.type === "choice") && (
                    <Button
                        onClick={() => handleSubmit(value)}
                        disabled={isSubmitting || (request.type === "text" && !value.trim())}
                        size="lg"
                        className="w-full h-12 rounded-xl font-bold shadow-md bg-amber-600 hover:bg-amber-700 text-white active:scale-[0.98] transition-transform"
                    >
                        <Play className="mr-2 h-4 w-4" />
                        {t("common.submit", "Submit")}
                    </Button>
                )}

                {/* Confirmation/Approval Buttons */}
                {(request.type === "confirmation" || request.type === "approval") && (
                    <div className="grid grid-cols-2 gap-3 w-full">
                        <Button
                            variant="outline"
                            className="h-12 rounded-xl border-amber-200 text-amber-700 hover:bg-amber-50 active:bg-amber-100 dark:border-amber-900/50 dark:hover:bg-amber-900/20 font-semibold"
                            onClick={() => handleSubmit(request.type === "approval" ? "REJECTED" : "no")}
                            disabled={isSubmitting}
                        >
                            <XCircle className="w-4 h-4 mr-2" />
                            {request.type === "approval" ? t("common.reject", "Reject") : t("common.no", "No")}
                        </Button>
                        <Button
                            className={cn(
                                "h-12 rounded-xl font-bold shadow-md active:scale-[0.98] transition-transform",
                                isHighRisk ? "bg-red-600 hover:bg-red-700 text-white" : "bg-amber-600 hover:bg-amber-700 text-white"
                            )}
                            onClick={() => handleSubmit(request.type === "approval" ? "APPROVED" : "yes")}
                            disabled={isSubmitting}
                        >
                            <CheckCircle2 className="w-4 h-4 mr-2" />
                            {request.type === "approval" ? t("common.approve", "Approve") : t("common.yes", "Yes")}
                        </Button>
                    </div>
                )}
            </CardFooter>
        </Card>
    )
}
