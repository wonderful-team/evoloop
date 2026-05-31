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
import { useSettings } from "./SettingsContext"
import { SettingsCard } from "./SettingsCard"
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
  const { setComponentDirty, registerSaveHandler, unregisterSaveHandler, registerResetHandler } = useSettings()

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
  const [headers, setHeaders] = useState("")
  
  const [initialState, setInitialState] = useState<any>(null)

  const fetchConfig = async () => {
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

      const state = {
        defaultModelId: configMap.LLM_MODEL || "",
        provider: configMap.LLM_PROVIDER || "openai",
        providerType: configMap.LLM_PROVIDER_TYPE || "openai",
        baseUrl: configMap.LLM_BASE_URL || "",
        model: configMap.CUSTOM_LLM_MODEL || "",
        visionModel: configMap.VISION_MODEL || "",
        apiKey: configMap.LLM_API_KEY || "",
        headers: configMap.LLM_HEADERS || "{}",
      }
      
      setDefaultModelId(state.defaultModelId)
      setProvider(state.provider)
      setProviderType(state.providerType)
      setBaseUrl(state.baseUrl)
      setModel(state.model)
      setVisionModel(state.visionModel)
      setApiKey(state.apiKey)
      setHeaders(state.headers)
      setInitialState(state)
    } catch (error) {
      toast.error(t("settings.llm.loadError"))
    } finally {
      setIsLoadingModels(false)
    }
  }

  // Track dirty
  useEffect(() => {
    if (!initialState) return
    const isDirty = 
      defaultModelId !== initialState.defaultModelId ||
      provider !== initialState.provider ||
      providerType !== initialState.providerType ||
      baseUrl !== initialState.baseUrl ||
      model !== initialState.model ||
      visionModel !== initialState.visionModel ||
      apiKey !== initialState.apiKey ||
      headers !== initialState.headers
      
    setComponentDirty("llm", isDirty)
  }, [defaultModelId, provider, providerType, baseUrl, model, visionModel, apiKey, headers, initialState, setComponentDirty])

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)

    let parsedHeaders = null
    try {
      if (headers && headers.trim()) {
        parsedHeaders = JSON.parse(headers)
      }
    } catch (e) {
      const msg = "Headers must be a valid JSON object"
      setTestResult({ success: false, msg })
      toast.error(msg)
      setTesting(false)
      return false
    }

    try {
      const res: any = await SystemService.testLlmConnection({
        requestBody: {
          provider,
          provider_type: providerType as any,
          base_url: baseUrl,
          model,
          api_key: apiKey,
          headers: parsedHeaders,
        },
      })
      if (res.success) {
        setTestResult({
          success: true,
          msg: `${t("settings.llm.connected")} Reply: ${res.reply || "OK"}`,
        })
        toast.success(t("settings.llm.connected"))
        return true
      } else {
        const msg = t("settings.llm.connection_failed")
        setTestResult({ success: false, msg })
        toast.error(msg)
        return false
      }
    } catch (error) {
      const msg = `${t("settings.llm.connection_error")}: ${(error as any).message}`
      setTestResult({ success: false, msg })
      toast.error(msg)
      return false
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    // 1. If provider settings changed, test connection first
    const configChanged = 
      provider !== initialState?.provider ||
      providerType !== initialState?.providerType ||
      baseUrl !== initialState?.baseUrl ||
      model !== initialState?.model ||
      apiKey !== initialState?.apiKey ||
      headers !== initialState?.headers

    if (configChanged) {
      const isOk = await handleTestConnection()
      if (!isOk) {
        throw new Error("LLM Connection test failed")
      }
    }

    let parsedHeaders = null
    try {
      if (headers && headers.trim()) {
        parsedHeaders = JSON.parse(headers)
      }
    } catch (e) {
      toast.error("Headers must be a valid JSON object")
      throw e
    }

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
          headers: parsedHeaders,
        },
      })
      // Update initial state to current values
      setInitialState({
        defaultModelId,
        provider,
        providerType,
        baseUrl,
        model,
        visionModel,
        apiKey,
        headers,
      })
      toast.success(t("settings.llm.saved"))
    } catch (error) {
      toast.error(t("settings.llm.save_failed"))
      throw error
    } finally {
      setLoading(false)
    }
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("llm", handleSave)
    registerResetHandler("llm", () => fetchConfig())
    return () => unregisterSaveHandler("llm")
  }, [registerSaveHandler, unregisterSaveHandler, registerResetHandler, provider, providerType, baseUrl, model, visionModel, apiKey, defaultModelId, headers, initialState])

  return (
    <div className="space-y-4">
      {/* Default Model Card */}
      <SettingsCard 
        icon={Brain} 
        title={t("settings.llm.default_model")} 
        description={t("settings.llm.default_model_desc")}
        headerExtra={
          loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("common.processing")}
            </div>
          )
        }
      >
        <div className="space-y-3">
          <Label className="text-sm font-medium">{t("settings.llm.select_active_model")}</Label>
          <Select 
            value={defaultModelId} 
            onValueChange={setDefaultModelId}
          >
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
                        <Badge variant="secondary" className="text-[10px] h-4 rounded-none">Platform</Badge>
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
                    <Badge variant="outline" className="text-[10px] h-4 border-amber-500/30 text-amber-600 rounded-none">Custom</Badge>
                  </div>
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </SettingsCard>

      {/* Provider Config Card */}
      <SettingsCard 
        icon={Network} 
        title={t("settings.llm.configure_provider")} 
        description={t("settings.llm.configure_provider_desc")}
        iconClassName="text-amber-600 bg-amber-600/10"
        headerExtra={
          loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("common.processing")}
            </div>
          )
        }
      >
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.modelFields.provider")}</Label>
              <Input 
                placeholder="openai" 
                value={provider || ""} 
                onChange={(e) => setProvider(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-3">
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
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.modelFields.modelName")}</Label>
              <Input 
                placeholder="gpt-4o" 
                value={model || ""} 
                onChange={(e) => setModel(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.modelFields.visionModel")}</Label>
              <Input 
                placeholder="gpt-4o" 
                value={visionModel || ""} 
                onChange={(e) => setVisionModel(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">{t("settings.modelFields.apiKey")}</Label>
            <div className="relative">
              <Input
                type={showApiKey ? "text" : "password"}
                placeholder="sk-..."
                value={apiKey || ""}
                onChange={(e) => setApiKey(e.target.value)}
                className="pr-10 h-10 transition-colors focus:border-primary"
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

          <div className="space-y-3">
            <Label className="text-sm font-medium">{t("settings.modelFields.headers")}</Label>
            <Input
              placeholder='{"User-Agent": "KimiCLI/1.5"}'
              value={headers || ""}
              onChange={(e) => setHeaders(e.target.value)}
              className="h-10 transition-colors focus:border-primary font-mono text-xs"
            />
          </div>

          <div className="flex flex-col gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={testing}
              className="w-full h-11 border-dashed hover:border-amber-500/50 hover:bg-amber-500/5 hover:text-amber-600 transition-all"
            >
              {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4 text-amber-500" />}
              {t("settings.llm.test_connection")}
            </Button>

            {testResult && (
              <div
                className={`flex items-start gap-3 p-4 rounded-xl border text-sm animate-in fade-in slide-in-from-top-2 duration-300 ${
                  testResult.success 
                    ? "bg-green-500/10 text-green-700 border-green-500/20 dark:text-green-400" 
                    : "bg-red-500/10 text-red-700 border-red-500/20 dark:text-red-400"
                }`}
              >
                {testResult.success ? <CheckCircle2 className="h-5 w-5 shrink-0 text-green-500" /> : <XCircle className="h-5 w-5 shrink-0 text-red-500" />}
                <span className="flex-1 leading-relaxed">{testResult.msg}</span>
              </div>
            )}
          </div>
        </div>
      </SettingsCard>
    </div>
  )
}
