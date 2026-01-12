import { zodResolver } from "@hookform/resolvers/zod"
import { Checkbox } from "@/components/ui/checkbox"
import { useQueryClient } from "@tanstack/react-query"
import { open } from "@tauri-apps/plugin-dialog"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { type SystemConfig, SystemService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const generalSettingsSchema = z.object({
  PROJECTS_ROOT: z.string().min(1, "Paths cannot be empty"),
  EVOLOOP_DEVICE_NAME: z.string().min(1, "Device name cannot be empty"),
  INTENT_MIN_CONFIDENCE: z.string().optional(),
  REQUIRE_PLAN_APPROVAL: z.boolean().default(true),
})

type GeneralSettingsValues = z.infer<typeof generalSettingsSchema>

export default function GeneralSettings() {
  const { t, i18n } = useTranslation()
  const [loading, setLoading] = useState(false)
  const form = useForm<GeneralSettingsValues>({
    resolver: zodResolver(generalSettingsSchema),
    defaultValues: {
      PROJECTS_ROOT: "",
      EVOLOOP_DEVICE_NAME: "",
      INTENT_MIN_CONFIDENCE: "0.35",
      REQUIRE_PLAN_APPROVAL: true,
    },
  })

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await SystemService.getSystemConfig()
        const configMap: Record<string, string> = {}
          ; (response as unknown as SystemConfig[]).forEach((item) => {
            configMap[item.key] = item.value
          })

        form.reset({
          PROJECTS_ROOT: configMap.PROJECTS_ROOT || "",
          EVOLOOP_DEVICE_NAME: configMap.EVOLOOP_DEVICE_NAME || "",
          INTENT_MIN_CONFIDENCE: configMap.INTENT_MIN_CONFIDENCE || "0.35",
          REQUIRE_PLAN_APPROVAL: configMap.REQUIRE_PLAN_APPROVAL !== "false",
        })

        // Sync Language from Backend if exists
        if (configMap.LANGUAGE) {
          i18n.changeLanguage(configMap.LANGUAGE)
        }
      } catch (_error) {
        toast.error(t("settings.general.loadError"))
      }
    }
    fetchConfig()
  }, [])

  const queryClient = useQueryClient()

  const onSubmit = async (data: GeneralSettingsValues) => {
    setLoading(true)
    try {
      await SystemService.updateSystemConfig({
        requestBody: { key: "PROJECTS_ROOT", value: data.PROJECTS_ROOT },
      })
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "EVOLOOP_DEVICE_NAME",
          value: data.EVOLOOP_DEVICE_NAME,
        },
      })
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "INTENT_MIN_CONFIDENCE",
          value: data.INTENT_MIN_CONFIDENCE || "0.35",
        },
      })
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "REQUIRE_PLAN_APPROVAL",
          value: String(data.REQUIRE_PLAN_APPROVAL),
        },
      })
      // Save Language Preference
      await SystemService.updateSystemConfig({
        requestBody: { key: "LANGUAGE", value: i18n.language },
      })

      toast.success(t("settings.general.success"))
      await queryClient.invalidateQueries({ queryKey: ["systemConfig"] })
    } catch (_error) {
      toast.error(t("settings.general.error"))
    } finally {
      setLoading(false)
    }
  }

  const handleBrowse = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      })
      if (typeof selected === "string") {
        form.setValue("PROJECTS_ROOT", selected, { shouldDirty: true })
      }
    } catch (_error) {
      toast.error(t("settings.general.browseError"))
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.general.title")}</CardTitle>
          <CardDescription>{t("settings.general.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <div className="grid gap-6 md:grid-cols-2">
                <FormItem>
                  <FormLabel>{t("settings.general.language")}</FormLabel>
                  <Select
                    value={i18n.language}
                    onValueChange={(value) => i18n.changeLanguage(value)}
                  >
                    <SelectTrigger>
                      <SelectValue
                        placeholder={t("settings.general.selectLanguage")}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="zh">中文 (Chinese)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    {t("settings.general.selectLanguageDesc")}
                  </FormDescription>
                </FormItem>

                <FormField
                  control={form.control}
                  name="EVOLOOP_DEVICE_NAME"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("settings.general.deviceName")}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder={t(
                            "settings.general.deviceNamePlaceholder",
                          )}
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        {t("settings.general.deviceNameDesc")}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="PROJECTS_ROOT"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("settings.general.projectsRoot")}</FormLabel>
                    <div className="flex gap-2">
                      <FormControl>
                        <Input placeholder="/path/to/projects" {...field} />
                      </FormControl>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleBrowse}
                      >
                        {t("settings.general.browse")}
                      </Button>
                    </div>
                    <FormDescription>
                      {t("settings.general.projectsRootDesc")}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="space-y-4 rounded-lg border p-4">
                <div className="space-y-0.5">
                  <h3 className="text-base font-medium">Agent Behavior (HITL)</h3>
                  <p className="text-sm text-muted-foreground">
                    Configure how the agent interacts with you.
                  </p>
                </div>

                <div className="grid gap-6 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="INTENT_MIN_CONFIDENCE"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Intent Threshold (0.0 - 1.0)</FormLabel>
                        <FormControl>
                          <Input type="number" step="0.05" min="0" max="1" placeholder="0.35" {...field} />
                        </FormControl>
                        <FormDescription>
                          Lower = Faster (More matching). Higher = Smarter (More LLM fallback). Default: 0.35
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="REQUIRE_PLAN_APPROVAL"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                        <FormControl>
                          <Checkbox
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                        <div className="space-y-1 leading-none">
                          <FormLabel>
                            Require Plan Approval
                          </FormLabel>
                          <FormDescription>
                            If unchecked, the agent will auto-execute generated plans without waiting for your confirmation.
                          </FormDescription>
                        </div>
                      </FormItem>
                    )}
                  />
                </div>
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
    </div>
  )
}
