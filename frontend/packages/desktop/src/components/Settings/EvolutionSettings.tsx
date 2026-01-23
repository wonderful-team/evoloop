import React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@evoloop/shared/components/ui/alert"
import { AlertTriangle } from "lucide-react"
// Wait, I should check how API calls are made. Assuming useAuth or a custom fetch wrapper.
// Let's use fetch with auth token if accessible, or check Service.ts.
// For now, I will use a simple fetch wrapper or assume Service.
// Actually, let's use a specialized hook or direct fetch for simplicity if Service isn't clear.

// Define types
interface EvolutionStatus {
    enabled: boolean
    env_enabled: boolean
    db_enabled: boolean
}

const EvolutionSettings: React.FC = () => {
    const { t } = useTranslation()
    const queryClient = useQueryClient()
    const token = localStorage.getItem("access_token")

    // Fetch Status
    const { data: status, isLoading } = useQuery<EvolutionStatus>({
        queryKey: ["evolution-status"],
        queryFn: async () => {
            // Using fetch for direct control, adapting to project style later if needed
            const res = await fetch("/api/v1/system/evolution-status", {
                headers: { Authorization: `Bearer ${token}` }
            })
            if (!res.ok) throw new Error("Failed to fetch status")
            return res.json()
        },
        enabled: !!token
    })

    // Toggle Mutation
    const mutation = useMutation({
        mutationFn: async (enabled: boolean) => {
            const res = await fetch("/api/v1/system/config", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify({
                    key: "ENABLE_SELF_EVOLUTION",
                    value: enabled ? "true" : "false",
                    description: "Frontend Toggle"
                })
            })
            if (!res.ok) throw new Error("Failed to update config")
            return res.json()
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["evolution-status"] })
        }
    })

    // Non-blocking render to match other tabs
    // if (isLoading) {
    //     return <div className="flex justify-center p-4"><Loader2 className="animate-spin" /></div>
    // }


    const isMasterDisabled = status && !status.env_enabled

    return (
        <div className="space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle>{t("settings.evolution.title")}</CardTitle>
                    <CardDescription>
                        {t("settings.evolution.description")}
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">

                    <Alert variant={isMasterDisabled ? "destructive" : "default"} className={isMasterDisabled ? "bg-muted" : "border-yellow-500/50 bg-yellow-500/10 text-yellow-600"}>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>{isMasterDisabled ? t("settings.evolution.env_disabled_title") : t("settings.evolution.caution_title")}</AlertTitle>
                        <AlertDescription>
                            {isMasterDisabled
                                ? t("settings.evolution.env_disabled_desc")
                                : t("settings.evolution.caution_desc")
                            }
                        </AlertDescription>
                    </Alert>

                    <div className="flex items-center justify-between rounded-lg border p-4 shadow-sm">
                        <div className="space-y-0.5">
                            <span className="text-base font-medium">{t("settings.evolution.enable_title")}</span>
                            <p className="text-sm text-muted-foreground">
                                {t("settings.evolution.enable_desc")}
                            </p>
                        </div>
                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="evolution-mode"
                                checked={status?.db_enabled || false}
                                onCheckedChange={(checked) => mutation.mutate(checked as boolean)}
                                disabled={isMasterDisabled || mutation.isPending || isLoading}
                            />
                            <label
                                htmlFor="evolution-mode"
                                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                            >
                                {t("settings.evolution.switch_label")}
                            </label>
                        </div>
                    </div>

                </CardContent>
            </Card>
        </div>
    )
}

export default EvolutionSettings
