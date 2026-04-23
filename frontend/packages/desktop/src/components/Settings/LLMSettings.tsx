import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { 
  Brain, 
  Globe, 
  Shield, 
  Zap, 
  Settings2, 
  Loader2, 
  CheckCircle2, 
  XCircle, 
  Eye, 
  EyeOff,
  Save,
  Network
} from "lucide-react"

import { SystemService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Label } from "@evoloop/shared/components/ui/label"
import { Input } from "@evoloop/shared/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import { Badge } from "@evoloop/shared/components/ui/badge"

// Preset model type from backend
interface PresetModel {
  id: string
  name: string
  type: "platform" | "custom"
  provider: string
  provider_type: "openai" | "anthropic"
  base_url: string
  model: string
  vision_model: string
  description?: string
  icon?: string
}

export function LLMSettings() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    msg: string
  } | null>(null)

  const [presetModels, setPresetModels] = useState<PresetModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = useState(true)

  // Form states
  const [defaultModelId, setDefaultModelId] = useState("")
  const [provider, setProvider] = useState("openai")
  const [providerType, setProviderType] = useState("openai")
  const [baseUrl, setBaseUrl] = useState("")
  const [model, setModel] = useState("")
  const [visionModel, setVisionModel] = useState("")
  const [apiKey, setApiKey] = useState("")

  // Load models and config
  useEffect(() => {
    const init = async () => {
      try {
        setIsLoadingModels(true)
        const [modelsRes, configRes] = await Promise.all([
          SystemService.getLlmModels(),
          SystemService.getSystemConfig()
        ])

        setPresetModels((modelsRes as any)?.models || [])

        const configMap: Record<string, string> = {}
        if (Array.isArray(configRes)) {
          configRes.forEach((item: any) => {
            configMap[item.key] = item.value
          })
        }

        setDefaultModelId(configMap.LLM_MODEL || "")
        setProvider(configMap.LLM_PROVIDER || "openai")
        setProviderType(configMap.LLM_PROVIDER_TYPE || "openai")
        setBaseUrl(configMap.LLM_BASE_URL || "")
        setModel(configMap.CUSTOM_LLM_MODEL || "")
        setVisionModel(configMap.VISION_MODEL || "")
        setApiKey(configMap.LLM_API_KEY || "")
      } catch (error) {
        toast.error(t("settings.llm.loadError"))
      } finally {
        setIsLoadingModels(false)
      }
    }
    init()
  }, [t])

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)

    try {
      const res: any = await SystemService.testLlmConnection({
        requestBody: {
          provider,
          provider_type: providerType as any,
          base_url: baseUrl,
          model,
          api_key: apiKey,
        },
      })
      if (res.success) {
        setTestResult({
          success: true,
          msg: `${t("settings.llm.connected")} Reply: ${res.reply || "OK"}`,
        })
        toast.success(t("settings.llm.connected"))
      } else {
        setTestResult({
          success: false,
          msg: t("settings.llm.connection_failed"),
        })
        toast.error(t("settings.llm.connection_failed"))
      }
    } catch (error) {
      setTestResult({ success: false, msg: (error as any).message })
      toast.error(`${t("settings.llm.connection_error")}: ${(error as any).message}`)
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setLoading(true)
    try {
      await SystemService.applyLlmConfig({
        requestBody: {
          provider,
          provider_type: providerType as any,
          base_url: baseUrl,
          model,
          vision_model: visionModel,
          api_key: apiKey,
          default_model_id: defaultModelId,
        },
      })
      toast.success(t("settings.llm.saved"))
      setTestResult(null)
    } catch (_error) {
      toast.error(t("settings.llm.save_failed"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Default Model Card */}
      <Card className="overflow-hidden border-primary/10 shadow-lg">
        <CardHeader className="bg-muted/30 pb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-xl">{t("settings.llm.default_model")}</CardTitle>
              <CardDescription>{t("settings.llm.default_model_desc")}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-4">
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t("settings.llm.select_active_model")}</Label>
            <Select value={defaultModelId} onValueChange={setDefaultModelId}>
              <SelectTrigger className="w-full h-12">
                <SelectValue placeholder={t("settings.llm.select_model_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Globe className="h-3.5 w-3.5" />
                    {t("chat.modelSelector.platformModels")}
                  </SelectLabel>
                  {presetModels
                    .filter((m) => m.type === "platform")
                    .map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        <div className="flex items-center gap-2">
                          <span>{m.name}</span>
                          <Badge variant="secondary" className="text-[10px] h-4">Platform</Badge>
                        </div>
                      </SelectItem>
                    ))}
                </SelectGroup>
                <SelectSeparator />
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Settings2 className="h-3.5 w-3.5" />
                    {t("chat.modelSelector.customModels")}
                  </SelectLabel>
                  <SelectItem value={`custom-${provider}-${model}`}>
                    <div className="flex items-center gap-2">
                      <span>{model || t("settings.llm.custom")}</span>
                      <Badge variant="outline" className="text-[10px] h-4 border-amber-500/50 text-amber-600">Custom</Badge>
                    </div>
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Provider Config Card */}
      <Card className="border-primary/10 shadow-lg">
        <CardHeader className="bg-muted/30 pb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-amber-500/10 p-2 text-amber-600">
              <Network className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-xl">{t("settings.llm.configure_provider")}</CardTitle>
              <CardDescription>{t("settings.llm.configure_provider_desc")}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t("settings.modelFields.provider")}</Label>
              <Input 
                placeholder="openai" 
                value={provider || ""} 
                onChange={(e) => setProvider(e.target.value)}
                className="h-10 focus:ring-amber-500/20"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t("settings.modelFields.providerType")}</Label>
              <Select value={providerType} onValueChange={setProviderType}>
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-blue-500" />
                      <span>{t("settings.providerType.openai")}</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="anthropic">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-orange-500" />
                      <span>{t("settings.providerType.anthropic")}</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-sm font-medium">{t("settings.modelFields.baseUrl")}</Label>
              <Input 
                placeholder="https://api.openai.com/v1" 
                value={baseUrl || ""} 
                onChange={(e) => setBaseUrl(e.target.value)}
                className="h-10"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t("settings.modelFields.modelName")}</Label>
              <Input 
                placeholder="gpt-4o" 
                value={model || ""} 
                onChange={(e) => setModel(e.target.value)}
                className="h-10"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t("settings.modelFields.visionModel")}</Label>
              <Input 
                placeholder="gpt-4o" 
                value={visionModel || ""} 
                onChange={(e) => setVisionModel(e.target.value)}
                className="h-10"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">{t("settings.modelFields.apiKey")}</Label>
            <div className="relative">
              <Input
                type={showApiKey ? "text" : "password"}
                placeholder="sk-..."
                value={apiKey || ""}
                onChange={(e) => setApiKey(e.target.value)}
                className="pr-10 h-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-muted-foreground" />}
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={testing}
              className="w-full hover:bg-amber-500/5 hover:text-amber-600 transition-colors"
            >
              {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4 text-amber-500" />}
              {t("settings.llm.test_connection")}
            </Button>

            {testResult && (
              <div
                className={`flex items-start gap-2 p-4 rounded-lg border text-sm animate-in fade-in slide-in-from-top-2 ${
                  testResult.success 
                    ? "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/10 dark:text-green-400 dark:border-green-900/30" 
                    : "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/10 dark:text-red-400 dark:border-red-900/30"
                }`}
              >
                {testResult.success ? <CheckCircle2 className="h-4 w-4 mt-0.5" /> : <XCircle className="h-4 w-4 mt-0.5" />}
                <span className="flex-1 leading-relaxed">{testResult.msg}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end pt-4">
        <Button 
          onClick={handleSave} 
          disabled={loading} 
          size="lg" 
          className="px-8 shadow-md hover:shadow-lg transition-all gap-2"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {t("settings.llm.apply_btn")}
        </Button>
      </div>
    </div>
  )
}
