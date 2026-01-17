import { motion } from "framer-motion"
import { CheckCircle2, Eye, EyeOff, Loader2, XCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { SystemService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { useWizard } from "../WizardContext"

const PROVIDERS = [
    {
        value: "openai",
        label: "wizard.llm.providers.openai",
        baseUrl: "https://api.openai.com/v1",
        model: "gpt-4o",
    },
    {
        value: "qwen",
        label: "wizard.llm.providers.qwen",
        baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen-max",
    },
    {
        value: "deepseek",
        label: "wizard.llm.providers.deepseek",
        baseUrl: "https://api.deepseek.com/v1",
        model: "deepseek-chat",
    },
    {
        value: "ollama",
        label: "wizard.llm.providers.ollama",
        baseUrl: "http://localhost:11434/v1",
        model: "llama3",
    },
    {
        value: "generic",
        label: "wizard.llm.providers.generic",
        baseUrl: "http://localhost:1234/v1",
        model: "local-model",
    },
]

export function LLMConfigStep() {
    const { t } = useTranslation()
    const { data, setData, setCanProceed } = useWizard()
    const [testing, setTesting] = useState(false)
    const [showApiKey, setShowApiKey] = useState(false)
    const [testResult, setTestResult] = useState<{
        success: boolean
        msg: string
    } | null>(null)

    // Initialize with defaults if empty
    useEffect(() => {
        if (!data.llmProvider) {
            setData({ llmProvider: "openai" })
        }
    }, [data.llmProvider, setData])

    // Update canProceed based on test result
    useEffect(() => {
        setCanProceed(data.llmTested && testResult?.success === true)
    }, [data.llmTested, testResult, setCanProceed])

    const handleProviderChange = (value: string) => {
        const provider = PROVIDERS.find((p) => p.value === value)
        if (provider) {
            setData({
                llmProvider: value,
                llmBaseUrl: provider.baseUrl,
                llmModel: provider.model,
                llmTested: false,
            })
            setTestResult(null)
        }
    }

    const handleTestConnection = async () => {
        setTesting(true)
        setTestResult(null)
        try {
            const res: any = await SystemService.testLlmConnection({
                requestBody: {
                    provider: data.llmProvider,
                    base_url: data.llmBaseUrl,
                    model: data.llmModel,
                    api_key: data.llmApiKey,
                },
            })
            if (res.success) {
                setTestResult({
                    success: true,
                    msg: t("wizard.llm.testSuccess"),
                })
                setData({ llmTested: true })
            } else {
                setTestResult({
                    success: false,
                    msg: t("wizard.llm.testFailed"),
                })
                setData({ llmTested: false })
            }
        } catch (error) {
            setTestResult({
                success: false,
                msg: `${t("wizard.llm.testError")}: ${(error as Error).message}`,
            })
            setData({ llmTested: false })
        } finally {
            setTesting(false)
        }
    }

    const isOllama = data.llmProvider === "ollama"

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="py-8 px-6 max-w-lg mx-auto"
        >
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold mb-2">{t("wizard.llm.title")}</h2>
                <p className="text-muted-foreground">{t("wizard.llm.subtitle")}</p>
            </div>

            <div className="space-y-5">
                {/* Provider */}
                <div className="space-y-2">
                    <Label>{t("wizard.llm.provider")}</Label>
                    <Select
                        value={data.llmProvider}
                        onValueChange={handleProviderChange}
                    >
                        <SelectTrigger>
                            <SelectValue placeholder={t("wizard.llm.selectProvider")} />
                        </SelectTrigger>
                        <SelectContent>
                            {PROVIDERS.map((p) => (
                                <SelectItem key={p.value} value={p.value}>
                                    {t(p.label)}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                {/* Base URL */}
                <div className="space-y-2">
                    <Label>{t("wizard.llm.baseUrl")}</Label>
                    <Input
                        value={data.llmBaseUrl}
                        onChange={(e) => {
                            setData({ llmBaseUrl: e.target.value, llmTested: false })
                            setTestResult(null)
                        }}
                        placeholder="https://api.openai.com/v1"
                    />
                </div>

                {/* Model */}
                <div className="space-y-2">
                    <Label>{t("wizard.llm.model")}</Label>
                    <Input
                        value={data.llmModel}
                        onChange={(e) => {
                            setData({ llmModel: e.target.value, llmTested: false })
                            setTestResult(null)
                        }}
                        placeholder="gpt-4o"
                    />
                </div>

                {/* API Key */}
                <div className="space-y-2">
                    <Label>
                        {t("wizard.llm.apiKey")}
                        {isOllama && (
                            <span className="text-muted-foreground text-sm ml-2">
                                ({t("wizard.llm.optional")})
                            </span>
                        )}
                    </Label>
                    <div className="relative">
                        <Input
                            type={showApiKey ? "text" : "password"}
                            value={data.llmApiKey}
                            onChange={(e) => {
                                setData({ llmApiKey: e.target.value, llmTested: false })
                                setTestResult(null)
                            }}
                            placeholder="sk-..."
                        />
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="absolute right-0 top-0 h-9 w-9"
                            onClick={() => setShowApiKey(!showApiKey)}
                        >
                            {showApiKey ? (
                                <EyeOff className="h-4 w-4" />
                            ) : (
                                <Eye className="h-4 w-4" />
                            )}
                        </Button>
                    </div>
                </div>

                {/* Test Connection */}
                <div className="pt-4">
                    <Button
                        variant="secondary"
                        onClick={handleTestConnection}
                        disabled={testing || !data.llmBaseUrl || !data.llmModel}
                        className="w-full"
                    >
                        {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {t("wizard.llm.testConnection")}
                    </Button>

                    {testResult && (
                        <div
                            className={`flex items-center gap-2 mt-3 text-sm ${testResult.success ? "text-green-600" : "text-red-600"
                                }`}
                        >
                            {testResult.success ? (
                                <CheckCircle2 className="h-4 w-4" />
                            ) : (
                                <XCircle className="h-4 w-4" />
                            )}
                            {testResult.msg}
                        </div>
                    )}
                </div>

                {/* Tip */}
                {!data.llmTested && (
                    <p className="text-sm text-muted-foreground text-center">
                        {t("wizard.llm.testRequired")}
                    </p>
                )}
            </div>
        </motion.div>
    )
}
