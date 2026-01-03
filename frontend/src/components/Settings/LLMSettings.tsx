import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Loader2, CheckCircle2, XCircle } from "lucide-react"
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

const llmSchema = z.object({
    provider: z.string(),
    base_url: z.string().min(1, "Base URL is required"),
    model: z.string().min(1, "Model name is required"),
    api_key: z.string().optional(),
})

type LLMValues = z.infer<typeof llmSchema>

export function LLMSettings() {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<{ success: boolean; msg: string } | null>(null)

    const form = useForm<LLMValues>({
        resolver: zodResolver(llmSchema),
        defaultValues: {
            provider: "openai",
            base_url: "",
            model: "",
            api_key: "",
        },
    })

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
                    provider: configMap.LLM_PROVIDER || "openai",
                    base_url: configMap.LLM_BASE_URL || "",
                    model: configMap.LLM_MODEL || "",
                    api_key: configMap.LLM_API_KEY || "",
                })
            } catch (error) {
                console.error("Failed to load LLM config", error)
            }
        }
        fetchConfig()
    }, [form])

    // Auto-fill defaults when provider changes
    const onProviderChange = (val: string) => {
        form.setValue("provider", val)
        if (val === "ollama") {
            form.setValue("base_url", "http://localhost:11434/v1") // LangChain OpenAI uses /v1 usually for Ollama too? Or base. Ollama matches OpenAI format at /v1
            form.setValue("model", "llama3")
        } else if (val === "generic") {
            form.setValue("base_url", "http://localhost:1234/v1")
            form.setValue("model", "local-model")
        } else if (val === "openai") {
            form.setValue("base_url", "https://api.openai.com/v1")
            form.setValue("model", "gpt-4o")
        } else if (val === "qwen") {
            form.setValue("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            form.setValue("model", "qwen-max")
        } else if (val === "deepseek") {
            form.setValue("base_url", "https://api.deepseek.com/v1")
            form.setValue("model", "deepseek-chat")
        }
    }

    const onTestConnection = async () => {
        const values = form.getValues()
        setTesting(true)
        setTestResult(null)
        try {
            const res = await SystemService.testLLMConnection({
                requestBody: {
                    provider: values.provider,
                    base_url: values.base_url,
                    model: values.model,
                    api_key: values.api_key,
                }
            })
            if (res.success) {
                setTestResult({ success: true, msg: `${t("settings.llm.connected")} Reply: ${res.reply || "OK"}` })
                toast.success(t("settings.llm.connected"))
            } else {
                setTestResult({ success: false, msg: t("settings.llm.connection_failed") })
                toast.error(t("settings.llm.connection_failed"))
            }
        } catch (error) {
            setTestResult({ success: false, msg: t("settings.llm.connection_error") })
            toast.error(t("settings.llm.connection_error") + ": " + (error as any).message)
        } finally {
            setTesting(false)
        }
    }

    const onSubmit = async (data: LLMValues) => {
        setLoading(true)
        try {
            await SystemService.applyLLMConfig({
                requestBody: {
                    provider: data.provider,
                    base_url: data.base_url,
                    model: data.model,
                    api_key: data.api_key
                }
            })
            toast.success(t("settings.llm.saved"))
            setTestResult(null)
        } catch (error) {
            toast.error(t("settings.llm.save_failed"))
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
                            {t("settings.llm.title")}
                        </CardTitle>
                        <CardDescription className="mt-1.5">
                            {t("settings.llm.description")}
                        </CardDescription>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        <FormField
                            control={form.control}
                            name="provider"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>{t("settings.llm.provider")}</FormLabel>
                                    <Select onValueChange={onProviderChange} defaultValue={field.value} value={field.value}>
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue placeholder={t("settings.llm.provider_placeholder")} />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            <SelectItem value="openai">OpenAI</SelectItem>
                                            <SelectItem value="qwen">Qwen / DashScope (Aliyun)</SelectItem>
                                            <SelectItem value="deepseek">DeepSeek</SelectItem>
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
                                        <FormLabel>{t("settings.llm.base_url")}</FormLabel>
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
                                        <FormLabel>{t("settings.llm.model_name")}</FormLabel>
                                        <FormControl>
                                            <Input placeholder="gpt-4o" {...field} />
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
                                    <FormLabel>{t("settings.llm.api_key")}</FormLabel>
                                    <FormControl>
                                        <Input type="password" placeholder="sk-..." {...field} />
                                    </FormControl>
                                    <FormDescription>{t("settings.llm.api_key_desc")}</FormDescription>
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
                                {t("settings.llm.test_connection")}
                            </Button>

                            <Button
                                type="submit"
                                disabled={loading || testing}
                            >
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                {t("settings.llm.apply_btn")}
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
