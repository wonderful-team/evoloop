import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useTranslation } from "react-i18next"
import { open } from "@tauri-apps/plugin-dialog"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
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
import { SystemService, type SystemConfig } from "@/client"

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
            } catch (error) {
                toast.error(t('settings.general.loadError'))
            }
        }
        fetchConfig()
    }, [form])

    const queryClient = useQueryClient()

    const onSubmit = async (data: GeneralSettingsValues) => {
        setLoading(true)
        try {
            await SystemService.updateSystemConfig({
                requestBody: { key: "PROJECTS_ROOT", value: data.PROJECTS_ROOT },
            })
            await SystemService.updateSystemConfig({
                requestBody: { key: "EVOLOOP_DEVICE_NAME", value: data.EVOLOOP_DEVICE_NAME },
            })
            toast.success(t('settings.general.success'))
            await queryClient.invalidateQueries({ queryKey: ["systemConfig"] })
        } catch (error) {
            toast.error(t('settings.general.error'))
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
        } catch (error) {
            toast.error(t('settings.general.browseError'))
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">{t('settings.general.title')}</h3>
                <p className="text-sm text-muted-foreground">
                    {t('settings.general.description')}
                </p>
            </div>
            <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
                    <div className="space-y-2">
                        <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">{t('settings.general.language')}</label>
                        <Select
                            value={i18n.language}
                            onValueChange={(value) => i18n.changeLanguage(value)}
                        >
                            <SelectTrigger className="w-[240px]">
                                <SelectValue placeholder={t('settings.general.selectLanguage')} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="en">English</SelectItem>
                                <SelectItem value="zh">中文 (Chinese)</SelectItem>
                            </SelectContent>
                        </Select>
                        <p className="text-[10px] text-muted-foreground">{t('settings.general.selectLanguageDesc')}</p>
                    </div>

                    <FormField
                        control={form.control}
                        name="EVOLOOP_DEVICE_NAME"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel>{t('settings.general.deviceName')}</FormLabel>
                                <FormControl>
                                    <Input placeholder={t('settings.general.deviceNamePlaceholder')} {...field} />
                                </FormControl>
                                <FormDescription>
                                    {t('settings.general.deviceNameDesc')}
                                </FormDescription>
                                <FormMessage />
                            </FormItem>
                        )}
                    />
                    <FormField
                        control={form.control}
                        name="PROJECTS_ROOT"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel>{t('settings.general.projectsRoot')}</FormLabel>
                                <div className="flex gap-2">
                                    <FormControl>
                                        <Input placeholder="/path/to/projects" {...field} />
                                    </FormControl>
                                    <Button type="button" variant="outline" onClick={handleBrowse}>
                                        {t('settings.general.browse')}
                                    </Button>
                                </div>
                                <FormDescription>
                                    {t('settings.general.projectsRootDesc')}
                                </FormDescription>
                                <FormMessage />
                            </FormItem>
                        )}
                    />
                    <Button type="submit" disabled={loading}>
                        {t('settings.general.save')}
                    </Button>
                </form>
            </Form>
        </div >
    )
}
