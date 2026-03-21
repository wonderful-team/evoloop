import { zodResolver } from "@hookform/resolvers/zod"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { useQueryClient } from "@tanstack/react-query"
import { open } from "@tauri-apps/plugin-dialog"
import { PlayCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { type SystemConfig, SystemService } from "@/client"
import { useTour } from "@/components/Common/SpotlightTour"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"

const generalSettingsSchema = z.object({
  WORKSPACE_ROOT: z.string().min(1),
  EVOCLOUD_DEVICE_NAME: z.string().min(1),
  LANGUAGE: z.string().default("zh"),
})

type GeneralSettingsValues = z.infer<typeof generalSettingsSchema>

export default function GeneralSettings() {
  const { t, i18n } = useTranslation()
  const [loading, setLoading] = useState(false)
  const { startTour } = useTour()
  const form = useForm<GeneralSettingsValues>({
    resolver: zodResolver(generalSettingsSchema) as any,
    defaultValues: {
      WORKSPACE_ROOT: "",
      EVOCLOUD_DEVICE_NAME: "",
      LANGUAGE: "zh",
    },
  })

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await SystemService.getSystemConfig()
        const configMap: Record<string, string> = {}
        if (Array.isArray(response)) {
          ;(response as unknown as SystemConfig[]).forEach((item) => {
            configMap[item.key] = item.value
          })
        }

        const language = configMap.LANGUAGE || "zh"
        form.reset({
          WORKSPACE_ROOT: configMap.WORKSPACE_ROOT || "",
          EVOCLOUD_DEVICE_NAME: configMap.EVOCLOUD_DEVICE_NAME || "",
          LANGUAGE: language,
        })

        // Sync Language from Backend
        i18n.changeLanguage(language)
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
        requestBody: { key: "WORKSPACE_ROOT", value: data.WORKSPACE_ROOT },
      })
      await SystemService.updateSystemConfig({
        requestBody: {
          key: "EVOCLOUD_DEVICE_NAME",
          value: data.EVOCLOUD_DEVICE_NAME,
        },
      })
      // Save Language Preference
      await SystemService.updateSystemConfig({
        requestBody: { key: "LANGUAGE", value: data.LANGUAGE },
      })
      // Apply language change immediately
      i18n.changeLanguage(data.LANGUAGE)

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
        form.setValue("WORKSPACE_ROOT", selected, { shouldDirty: true })
      }
    } catch (_error) {
      toast.error(t("settings.general.browseError"))
    }
  }

  const handleReplayTour = () => {
    // Clear the storage to allow re-triggering
    localStorage.removeItem("evoloop_desktop_tour_seen")
    startTour()
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
                <FormField
                  control={form.control}
                  name="LANGUAGE"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("settings.general.language")}</FormLabel>
                      <Select
                        value={field.value}
                        onValueChange={(value) => {
                          field.onChange(value)
                          i18n.changeLanguage(value)
                        }}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue
                              placeholder={t("settings.general.selectLanguage")}
                            />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="en">{t("settings.general.languageOptions.en")}</SelectItem>
                          <SelectItem value="zh">{t("settings.general.languageOptions.zh")}</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        {t("settings.general.selectLanguageDesc")}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="EVOCLOUD_DEVICE_NAME"
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
                name="WORKSPACE_ROOT"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("settings.general.workspaceRoot")}</FormLabel>
                    <div className="flex gap-2">
                      <FormControl>
                        <Input placeholder={t("settings.general.workspaceRootPlaceholder")} {...field} />
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
                      {t("settings.general.workspaceRootDesc")}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-end">
                <Button type="submit" disabled={loading}>
                  {t("settings.general.save")}
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>

      {/* Replay Tour Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t("tour.replayTitle")}</CardTitle>
          <CardDescription>{t("tour.replayDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={handleReplayTour}>
            <PlayCircle className="mr-2 h-4 w-4" />
            {t("tour.replayTitle")}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

