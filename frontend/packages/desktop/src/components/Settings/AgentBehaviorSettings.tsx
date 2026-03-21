import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { SystemService, type SystemConfig } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"

export function AgentBehaviorSettings() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [loading, setLoading] = useState(false)

  const form = useForm({
    defaultValues: {
      intentMinConfidence: "0.35",
      requirePlanApproval: true,
    },
  })

  // Load config
  const { data: configData } = useQuery({
    queryKey: ["systemConfig"],
    queryFn: async () => {
      const response = await SystemService.getSystemConfig()
      const configMap: Record<string, string> = {}
      // Handle case when response is an array
      if (Array.isArray(response)) {
        (response as unknown as SystemConfig[]).forEach((item) => {
          configMap[item.key] = item.value
        })
      }
      return configMap
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  useEffect(() => {
    if (configData) {
      form.reset({
        intentMinConfidence: configData.INTENT_MIN_CONFIDENCE || "0.35",
        requirePlanApproval: configData.REQUIRE_PLAN_APPROVAL !== "false",
      })
    }
  }, [configData, form])

  const onSubmit = async (values: { intentMinConfidence: string; requirePlanApproval: boolean }) => {
    setLoading(true)
    try {
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "INTENT_MIN_CONFIDENCE",
          value: values.intentMinConfidence || "0.35",
        },
      })
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "REQUIRE_PLAN_APPROVAL",
          value: String(values.requirePlanApproval),
        },
      })
      toast.success(t("settings.general.success"))
      queryClient.invalidateQueries({ queryKey: ["systemConfig"] })
    } catch (_error) {
      toast.error(t("settings.general.error"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.general.agentBehavior.title")}</CardTitle>
        <CardDescription>
          {t("settings.general.agentBehavior.description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="intentMinConfidence"
                render={({ field }) => (
                  <FormItem className="space-y-1">
                    <FormLabel className="text-sm">
                      {t("settings.general.intentThreshold.label")}
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step="0.05"
                        min="0"
                        max="1"
                        placeholder="0.35"
                        {...field}
                        className="h-9"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="requirePlanApproval"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-3">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel className="text-sm">
                        {t("settings.general.planApproval.label")}
                      </FormLabel>
                      <p className="text-xs text-muted-foreground">
                        {t("settings.general.planApproval.description")}
                      </p>
                    </div>
                  </FormItem>
                )}
              />
            </div>

            <div className="flex justify-end">
              <Button type="submit" disabled={loading}>
                {t("settings.general.save")}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}
