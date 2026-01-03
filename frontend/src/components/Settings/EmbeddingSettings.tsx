import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { SystemService, type SystemConfig } from "@/client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

// ... (schema and type definition omitted for brevity, keeping existing)
const embeddingSchema = z.object({
    provider: z.string(),
    base_url: z.string().min(1, "Base URL is required"),
    model: z.string().min(1, "Model name is required"),
    api_key: z.string().optional(),
})

type EmbeddingValues = z.infer<typeof embeddingSchema>

export function EmbeddingSettings() {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<{ success: boolean; msg: string } | null>(null)

    const form = useForm<EmbeddingValues>({
        resolver: zodResolver(embeddingSchema),
        defaultValues: {
            provider: "openai",
            base_url: "",
            model: "",
            api_key: "",
        },
    })

    // ... (useEffect and helper functions kept same)
    // Load initial config
    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const response = await SystemService.getSystemConfig()
                const configMap: Record<string, string> = {}
                    ; (response as unknown as SystemConfig[]).forEach((item) => {
                        configMap[item.key] = item.value
                    })

                form.reset({
                    provider: configMap.EMBEDDING_PROVIDER || "openai",
                    base_url: configMap.EMBEDDING_BASE_URL || "https://api.openai.com/v1",
                    model: configMap.EMBEDDING_MODEL || "text-embedding-ada-002",
                    api_key: configMap.EMBEDDING_API_KEY || "",
                })
            } catch (error) {
                console.error("Failed to load embedding config", error)
            }
        }
        fetchConfig()
    }, [form])

    // Auto-fill defaults when provider changes
    const onProviderChange = (val: string) => {
        form.setValue("provider", val)
        if (val === "ollama") {
            form.setValue("base_url", "http://localhost:11434")
            form.setValue("model", "nomic-embed-text")
        } else if (val === "generic") {
            form.setValue("base_url", "http://localhost:1234/v1")
            form.setValue("model", "text-embedding-nomic-embed-text-v1.5")
        } else if (val === "openai") {
            form.setValue("base_url", "https://api.openai.com/v1")
            form.setValue("model", "text-embedding-3-small")
        }
    }

    const onTestConnection = async () => {
        const values = form.getValues()
        setTesting(true)
        setTestResult(null)
        try {
            const res = await SystemService.testEmbeddingConnection({
                requestBody: {
                    provider: values.provider,
                    base_url: values.base_url,
                    model: values.model,
                    api_key: values.api_key,
                }
            })
            if (res.success) {
                setTestResult({ success: true, msg: t('settings.embedding.success_connected', { dim: res.dimensions }) })
                toast.success(t('settings.embedding.success_connected', { dim: res.dimensions }))
            } else {
                setTestResult({ success: false, msg: t('settings.embedding.error_connection') })
                toast.error(t('settings.embedding.error_connection'))
            }
        } catch (error) {
            setTestResult({ success: false, msg: t('settings.embedding.error_connection') })
            toast.error(t('settings.embedding.error_connection') + ": " + (error as any).message)
        } finally {
            setTesting(false)
        }
    }

    const onSubmit = async (data: EmbeddingValues) => {
        if (!confirm(t('settings.embedding.confirm_switch'))) {
            return
        }

        setLoading(true)
        try {
            await SystemService.applyEmbeddingConfig({
                requestBody: {
                    provider: data.provider,
                    base_url: data.base_url,
                    model: data.model,
                    api_key: data.api_key,
                    project_id: undefined
                }
            })
            toast.success(t('settings.embedding.success_updated'))
            setTestResult(null)
        } catch (error) {
            toast.error(t('settings.embedding.error_update'))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            {t('settings.embedding.title')}
                        </CardTitle>
                        <CardDescription className="mt-1.5">
                            {t('settings.embedding.description')}
                        </CardDescription>
                    </div>
                </div>
                <Alert variant="destructive" className="mt-4">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('settings.embedding.warning')}</AlertTitle>
                    <AlertDescription>
                        {t('settings.embedding.warning_desc')}
                    </AlertDescription>
                </Alert>
            </CardHeader>
            <CardContent>
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        <FormField
                            control={form.control}
                            name="provider"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>{t('settings.embedding.provider')}</FormLabel>
                                    <Select onValueChange={onProviderChange} defaultValue={field.value} value={field.value}>
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select a provider" />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            <SelectItem value="openai">OpenAI</SelectItem>
                                            <SelectItem value="ollama">Ollama (Local)</SelectItem>
                                            <SelectItem value="generic">LMStudio / Generic (OpenAI Compatible)</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <div className="grid grid-cols-2 gap-4">
                            <FormField
                                control={form.control}
                                name="base_url"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>{t('settings.embedding.base_url')}</FormLabel>
                                        <FormControl>
                                            <Input placeholder="https://api.openai.com/v1" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                            <FormField
                                control={form.control}
                                name="model"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>{t('settings.embedding.model_name')}</FormLabel>
                                        <FormControl>
                                            <Input placeholder="text-embedding-3-small" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                        </div>

                        <FormField
                            control={form.control}
                            name="api_key"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>{t('settings.embedding.api_key')}</FormLabel>
                                    <FormControl>
                                        <Input type="password" placeholder="sk-..." {...field} />
                                    </FormControl>
                                    <FormDescription>{t('settings.embedding.api_key_desc')}</FormDescription>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <div className="flex items-center gap-4 pt-2">
                            <Button
                                type="button"
                                variant="secondary"
                                onClick={onTestConnection}
                                disabled={testing || loading}
                            >
                                {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {t('settings.embedding.test_connection')}
                            </Button>

                            <Button
                                type="submit"
                                disabled={loading || testing}
                                className="bg-red-600 hover:bg-red-700 text-white"
                            >
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {t('settings.embedding.apply_btn')}
                            </Button>
                        </div>

                        {testResult && (
                            <div className={`flex items-center gap-2 text-sm ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
                                {testResult.success ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                                {testResult.msg}
                            </div>
                        )}
                    </form>
                </Form>
            </CardContent>
        </Card>
    )
}
