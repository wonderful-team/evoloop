import { Button } from "@evoloop/shared/components/ui/button"
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
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { Languages, Monitor, PlayCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { type SystemConfig, SystemService } from "@/client"
import { useTour } from "@/components/Common/SpotlightTour"
import { isTauri } from "@/lib/tauri"
import CustomerServiceDutySettings from "./CustomerServiceDutySettings"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

const generalSettingsSchema = z.object({
  WORKSPACE_ROOT: z.string().min(1),
  EVOCLOUD_DEVICE_NAME: z.string().min(1),
  EVOCLOUD_DEVICE_DESCRIPTION: z.string(),
  LANGUAGE: z.string().default("zh"),
})

type GeneralSettingsValues = z.infer<typeof generalSettingsSchema>

export default function GeneralSettings() {
  const { t, i18n } = useTranslation()
  const [loading, setLoading] = useState(false)
  const { startTour } = useTour()
  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()

  const form = useForm<GeneralSettingsValues>({
    resolver: zodResolver(generalSettingsSchema) as any,
    defaultValues: {
      WORKSPACE_ROOT: "",
      EVOCLOUD_DEVICE_NAME: "",
      EVOCLOUD_DEVICE_DESCRIPTION: "",
      LANGUAGE: "zh",
    },
  })

  // Track dirty state
  useEffect(() => {
    setComponentDirty("general", form.formState.isDirty)
  }, [form.formState.isDirty, setComponentDirty])

  const fetchConfig = async () => {
    try {
      const configResponse = await SystemService.getSystemConfig()

      const configMap: Record<string, string> = {}
      if (Array.isArray(configResponse)) {
        ;(configResponse as unknown as SystemConfig[]).forEach((item) => {
          configMap[item.key] = item.value
        })
      }

      const language = configMap.LANGUAGE || "zh"
      const values = {
        WORKSPACE_ROOT: configMap.WORKSPACE_ROOT || "",
        EVOCLOUD_DEVICE_NAME: configMap.EVOCLOUD_DEVICE_NAME || "",
        EVOCLOUD_DEVICE_DESCRIPTION:
          configMap.EVOCLOUD_DEVICE_DESCRIPTION || "",
        LANGUAGE: language,
      }
      form.reset(values)
      i18n.changeLanguage(language)
    } catch (_error) {
      toast.error(t("settings.general.loadError"))
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  const queryClient = useQueryClient()

  const handleSave = async () => {
    const data = form.getValues()
    const isValid = await form.trigger()
    if (!isValid) throw new Error("Validation failed")

    setLoading(true)
    try {
      await Promise.all([
        SystemService.updateSystemConfig({
          requestBody: { key: "WORKSPACE_ROOT", value: data.WORKSPACE_ROOT },
        }),
        SystemService.updateSystemConfig({
          requestBody: {
            key: "EVOCLOUD_DEVICE_NAME",
            value: data.EVOCLOUD_DEVICE_NAME,
          },
        }),
        SystemService.updateSystemConfig({
          requestBody: {
            key: "EVOCLOUD_DEVICE_DESCRIPTION",
            value: data.EVOCLOUD_DEVICE_DESCRIPTION,
          },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "LANGUAGE", value: data.LANGUAGE },
        }),
      ])

      i18n.changeLanguage(data.LANGUAGE)
      await queryClient.invalidateQueries({ queryKey: ["systemConfig"] })
      form.reset(data) // Reset dirty state to current values
    } catch (error) {
      toast.error(t("settings.general.error"))
      throw error
    } finally {
      setLoading(false)
    }
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("general", handleSave)
    registerResetHandler("general", () => fetchConfig())
    return () => unregisterSaveHandler("general")
  }, [registerSaveHandler, unregisterSaveHandler, registerResetHandler, form])

  const handleBrowse = async () => {
    if (!isTauri()) {
      toast.info(t("settings.general.webBrowseHint"))
      return
    }
    try {
      const { open } = await import("@tauri-apps/plugin-dialog")
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
    localStorage.removeItem("evoloop_desktop_tour_seen")
    startTour()
  }

  return (
    <div className="space-y-4">
      <SettingsCard
        icon={Monitor}
        title={t("settings.general.title")}
        description={t("settings.general.description")}
        headerExtra={
          loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              {t("common.processing")}
            </div>
          )
        }
      >
        <Form {...form}>
          <form className="space-y-4">
            <div className="grid gap-6 md:grid-cols-2">
              <FormField
                control={form.control}
                name="LANGUAGE"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-2">
                      <Languages className="h-4 w-4 text-muted-foreground" />
                      {t("settings.general.language")}
                    </FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="h-10">
                          <SelectValue
                            placeholder={t("settings.general.selectLanguage")}
                          />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="en">
                          {t("settings.general.languageOptions.en")}
                        </SelectItem>
                        <SelectItem value="zh">
                          {t("settings.general.languageOptions.zh")}
                        </SelectItem>
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
                        className="h-10 transition-colors focus:border-primary"
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
              name="EVOCLOUD_DEVICE_DESCRIPTION"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t("settings.general.deviceDescription")}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      className="min-h-[80px] resize-y transition-colors focus:border-primary"
                      placeholder={t(
                        "settings.general.deviceDescriptionPlaceholder",
                      )}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {t("settings.general.deviceDescriptionDesc")}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="WORKSPACE_ROOT"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("settings.general.workspaceRoot")}</FormLabel>
                  <div className="flex gap-2">
                    <FormControl>
                      <Input
                        className="h-10 transition-colors focus:border-primary"
                        placeholder={t(
                          "settings.general.workspaceRootPlaceholder",
                        )}
                        {...field}
                      />
                    </FormControl>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-10 shrink-0"
                      onClick={handleBrowse}
                      disabled={!isTauri()}
                      title={
                        !isTauri() ? t("settings.general.webBrowseHint") : ""
                      }
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
          </form>
        </Form>
      </SettingsCard>

      {/* 客服值守（全局机制） */}
      <CustomerServiceDutySettings />

      <SettingsCard
        icon={PlayCircle}
        title={t("tour.replayTitle")}
        description={t("tour.replayDesc")}
        iconClassName="text-blue-500 bg-blue-500/10"
      >
        <Button variant="outline" onClick={handleReplayTour} className="gap-2">
          <PlayCircle className="h-4 w-4" />
          {t("tour.replayTitle")}
        </Button>
      </SettingsCard>
    </div>
  )
}
