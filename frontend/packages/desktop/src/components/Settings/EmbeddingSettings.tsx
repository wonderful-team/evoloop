import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
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
import {
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  Globe,
  Layers,
  Loader2,
  Network,
  Save,
  Shield,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

// Preset embedding model type from backend
interface PresetEmbeddingModel {
  id: string
  name: string
  type: "platform" | "custom"
  provider: string
  base_url: string
  model: string
  dimensions: number
  description?: string
}

export function EmbeddingSettings() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    msg: string
  } | null>(null)
  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()

  const [presetModels, setPresetModels] = useState<PresetEmbeddingModel[]>([])
  const [_isLoadingModels, setIsLoadingModels] = useState(true)

  // Form states
  const [defaultModelId, setDefaultModelId] = useState("")
  const [provider, setProvider] = useState("openai")
  const [baseUrl, setBaseUrl] = useState("")
  const [model, setModel] = useState("")
  const [dimensions, setDimensions] = useState("768")
  const [apiKey, setApiKey] = useState("")

  const [initialState, setInitialState] = useState<any>(null)

  const fetchConfig = async () => {
    try {
      setIsLoadingModels(true)
      const [modelsRes, configRes] = await Promise.all([
        SystemService.getEmbeddingModels(),
        SystemService.getSystemConfig(),
      ])

      setPresetModels((modelsRes as any)?.models || [])

      const configMap: Record<string, string> = {}
      if (Array.isArray(configRes)) {
        configRes.forEach((item: any) => {
          configMap[item.key] = item.value
        })
      }

      const state = {
        defaultModelId: configMap.EMBEDDING_MODEL || "",
        provider: configMap.EMBEDDING_PROVIDER || "openai",
        baseUrl: configMap.EMBEDDING_BASE_URL || "",
        model: configMap.CUSTOM_EMBEDDING_MODEL || "",
        dimensions: configMap.EMBEDDING_DIMENSIONS || "768",
        apiKey: configMap.EMBEDDING_API_KEY || "",
      }

      setDefaultModelId(state.defaultModelId)
      setProvider(state.provider)
      setBaseUrl(state.baseUrl)
      setModel(state.model)
      setDimensions(state.dimensions)
      setApiKey(state.apiKey)
      setInitialState(state)
    } catch (_error) {
      toast.error(t("settings.embedding.loadError"))
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
      baseUrl !== initialState.baseUrl ||
      model !== initialState.model ||
      dimensions !== initialState.dimensions ||
      apiKey !== initialState.apiKey

    setComponentDirty("embedding", isDirty)
  }, [
    defaultModelId,
    provider,
    baseUrl,
    model,
    dimensions,
    apiKey,
    initialState,
    setComponentDirty,
  ])

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)

    try {
      const res: any = await SystemService.testEmbeddingConnection({
        requestBody: {
          provider,
          base_url: baseUrl,
          model,
          api_key: apiKey,
        },
      })
      if (res.success) {
        setTestResult({
          success: true,
          msg: t("settings.embedding.success_connected", {
            dim: res.dimensions,
          }),
        })
        toast.success(
          t("settings.embedding.success_connected", { dim: res.dimensions }),
        )
        return true
      }
      const msg = t("settings.embedding.error_connection")
      setTestResult({ success: false, msg })
      toast.error(msg)
      return false
    } catch (error) {
      const msg = t("settings.embedding.connectionErrorWithMessage", {
        message: t("settings.embedding.error_connection"),
        detail: (error as any).message,
      })
      setTestResult({ success: false, msg })
      toast.error(msg)
      return false
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    // 1. Check if config changed and test connection
    const configChanged =
      provider !== initialState?.provider ||
      baseUrl !== initialState?.baseUrl ||
      model !== initialState?.model ||
      apiKey !== initialState?.apiKey

    if (configChanged) {
      const isOk = await handleTestConnection()
      if (!isOk) {
        throw new Error(t("settings.embedding.connectionTestFailed"))
      }
    }

    setLoading(true)
    try {
      // Just update parameters, don't trigger re-indexing automatically in the global save
      // unless the user clicks the explicit button.
      await Promise.all([
        SystemService.updateSystemConfig({
          requestBody: { key: "EMBEDDING_PROVIDER", value: provider },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "EMBEDDING_BASE_URL", value: baseUrl },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "CUSTOM_EMBEDDING_MODEL", value: model },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "EMBEDDING_DIMENSIONS", value: dimensions },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "EMBEDDING_API_KEY", value: apiKey },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "EMBEDDING_MODEL", value: defaultModelId },
        }),
      ])

      setInitialState({
        defaultModelId,
        provider,
        baseUrl,
        model,
        dimensions,
        apiKey,
      })
    } catch (error) {
      toast.error(t("settings.embedding.error_update"))
      throw error
    } finally {
      setLoading(false)
    }
  }

  // Explicit Activation & Re-index (Manual Action)
  const handleActivateAndReindex = async () => {
    if (!confirm(t("settings.embedding.confirm_switch"))) {
      return
    }

    setLoading(true)
    try {
      await SystemService.applyEmbeddingConfig({
        requestBody: {
          provider,
          base_url: baseUrl,
          model,
          dimensions: parseInt(dimensions || "768", 10),
          api_key: apiKey,
          default_model_id: defaultModelId,
        },
      })
      toast.success(t("settings.embedding.success_updated"))
      setInitialState({
        defaultModelId,
        provider,
        baseUrl,
        model,
        dimensions,
        apiKey,
      })
    } catch (_error) {
      toast.error(t("settings.embedding.error_update"))
    } finally {
      setLoading(false)
    }
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("embedding", handleSave)
    registerResetHandler("embedding", () => fetchConfig())
    return () => unregisterSaveHandler("embedding")
  }, [
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
    provider,
    baseUrl,
    model,
    dimensions,
    apiKey,
    defaultModelId,
    initialState,
  ])

  return (
    <div className="space-y-8">
      {/* Default Model Card */}
      <SettingsCard
        icon={Database}
        title={t("settings.embedding.default_model")}
        description={t("settings.embedding.default_model_desc")}
        iconClassName="text-blue-600 bg-blue-600/10"
        headerExtra={
          loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("common.processing")}
            </div>
          )
        }
      >
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t("settings.embedding.select_default_placeholder")}
          </Label>
          <Select value={defaultModelId} onValueChange={setDefaultModelId}>
            <SelectTrigger className="w-full h-12">
              <SelectValue
                placeholder={t("settings.embedding.select_model_placeholder")}
              />
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
                        <Badge
                          variant="secondary"
                          className="text-[10px] h-4 rounded-none"
                        >
                          {t("chat.modelSelector.platformBadge")}
                        </Badge>
                      </div>
                    </SelectItem>
                  ))}
              </SelectGroup>
              <SelectSeparator />
              <SelectGroup>
                <SelectLabel className="flex items-center gap-2">
                  <Layers className="h-3.5 w-3.5" />
                  {t("chat.modelSelector.customModels")}
                </SelectLabel>
                <SelectItem value={`custom-${provider}-${model}`}>
                  <div className="flex items-center gap-2">
                    <span>{model || t("settings.llm.custom")}</span>
                    <Badge
                      variant="outline"
                      className="text-[10px] h-4 border-blue-500/30 text-blue-600 rounded-none"
                    >
                      {t("chat.modelSelector.customBadge")}
                    </Badge>
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
        iconClassName="text-indigo-600 bg-indigo-600/10"
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
            <div className="space-y-2">
              <Label className="text-sm font-medium">
                {t("settings.modelFields.provider")}
              </Label>
              <Input
                placeholder={t("settings.embedding.providerPlaceholder")}
                value={provider || ""}
                onChange={(e) => setProvider(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">
                {t("settings.modelFields.dimensions")}
              </Label>
              <Input
                type="number"
                placeholder={t("settings.embedding.dimensionsPlaceholder")}
                value={dimensions || ""}
                onChange={(e) => setDimensions(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-sm font-medium">
                {t("settings.modelFields.baseUrl")}
              </Label>
              <Input
                placeholder={t("settings.embedding.baseUrlPlaceholder")}
                value={baseUrl || ""}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-sm font-medium">
                {t("settings.modelFields.modelName")}
              </Label>
              <Input
                placeholder={t("settings.embedding.modelPlaceholder")}
                value={model || ""}
                onChange={(e) => setModel(e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">
              {t("settings.modelFields.apiKey")}
            </Label>
            <div className="relative">
              <Input
                type={showApiKey ? "text" : "password"}
                placeholder={t("settings.embedding.apiKeyPlaceholder")}
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
                {showApiKey ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <div className="flex gap-4">
              <Button
                type="button"
                variant="outline"
                onClick={handleTestConnection}
                disabled={testing}
                className="flex-1 h-11 border-dashed hover:border-indigo-500/50 hover:bg-indigo-500/5 hover:text-indigo-600 transition-all"
              >
                {testing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Shield className="mr-2 h-4 w-4 text-indigo-500" />
                )}
                {t("settings.embedding.test_connection")}
              </Button>

              <Button
                onClick={handleActivateAndReindex}
                disabled={loading}
                className="flex-1 h-11 transition-all gap-2"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {t("settings.embedding.activate_reindex")}
              </Button>
            </div>

            {testResult && (
              <div
                className={`flex items-start gap-3 p-4 rounded-xl border text-sm animate-in fade-in slide-in-from-top-2 duration-300 ${
                  testResult.success
                    ? "bg-green-500/10 text-green-700 border-green-500/20 dark:text-green-400"
                    : "bg-red-500/10 text-red-700 border-red-500/20 dark:text-red-400"
                }`}
              >
                {testResult.success ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-green-500" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0 text-red-500" />
                )}
                <span className="flex-1 leading-relaxed">{testResult.msg}</span>
              </div>
            )}
          </div>
        </div>
      </SettingsCard>
    </div>
  )
}
