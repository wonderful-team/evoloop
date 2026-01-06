import { zodResolver } from "@hookform/resolvers/zod"
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
