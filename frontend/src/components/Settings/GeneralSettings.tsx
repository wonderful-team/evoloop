import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { open } from "@tauri-apps/plugin-dialog"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
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
                toast.error("Failed to load system settings")
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
            toast.success("Settings saved successfully")
            await queryClient.invalidateQueries({ queryKey: ["systemConfig"] })
        } catch (error) {
            toast.error("Failed to save settings")
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
            toast.error("Failed to open directory selector")
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">General Settings</h3>
                <p className="text-sm text-muted-foreground">
                    Configure global system preferences and paths.
                </p>
            </div>
            <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
                    <FormField
                        control={form.control}
                        name="EVOLOOP_DEVICE_NAME"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel>Device Name</FormLabel>
                                <FormControl>
                                    <Input placeholder="My Device" {...field} />
                                </FormControl>
                                <FormDescription>
                                    This name identifies this device in the EvoLoop network.
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
                                <FormLabel>Projects Root Directory</FormLabel>
                                <div className="flex gap-2">
                                    <FormControl>
                                        <Input placeholder="/path/to/projects" {...field} />
                                    </FormControl>
                                    <Button type="button" variant="outline" onClick={handleBrowse}>
                                        Browse
                                    </Button>
                                </div>
                                <FormDescription>
                                    The implementation requires read/write access to this directory.
                                </FormDescription>
                                <FormMessage />
                            </FormItem>
                        )}
                    />
                    <Button type="submit" disabled={loading}>
                        Save changes
                    </Button>
                </form>
            </Form>
        </div>
    )
}
