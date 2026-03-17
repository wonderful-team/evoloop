import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, ChevronDown, ChevronUp, Eye, EyeOff, Loader2, XCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { SystemService, type SystemConfig } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
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

// Preset model type from backend
interface PresetModel {
  id: string
  name: string
  type: "platform" | "custom"
  provider: string
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
  const [advancedMode, setAdvancedMode] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string>("")
  const [testResult, setTestResult] = useState<{
    success: boolean
    msg: string
  } | null>(null)

  // Fetch preset models from backend
  const { data: presetModelsData, isLoading: isLoadingModels } = useQuery({
    queryKey: ["llmPresetModels"],
    queryFn: () => SystemService.getAvailableLlmModels(),
  })

  const presetModels: PresetModel[] = (presetModelsData as any)?.models || []

  // Form for advanced mode
  const form = useForm({
    defaultValues: {
      provider: "openai",
      base_url: "",
      model: "",
      vision_model: "",
      api_key: "",
    },
  })

  // Simple mode form
  const [simpleApiKey, setSimpleApiKey] = useState("")

  // Load initial config
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await SystemService.getSystemConfig()
        const configMap: Record<string, string> = {}
        ;(response as unknown as SystemConfig[]).forEach((item) => {
          configMap[item.key] = item.value
        })

        const currentProvider = configMap.LLM_PROVIDER || ""
        const currentModel = configMap.LLM_MODEL || ""
        const currentBaseUrl = configMap.LLM_BASE_URL || ""

        // Try to find matching preset model
        const matchingPreset = presetModels.find(
          (m) =>
            m.provider === currentProvider &&
            m.model === currentModel &&
            m.base_url === currentBaseUrl
        )

        if (matchingPreset) {
          setSelectedModelId(matchingPreset.id)
        } else if (currentModel) {
          // Custom config - still show simple mode but select "custom"
          setSelectedModelId("custom")
          // User can manually switch to advanced if needed
        }

        form.reset({
          provider: currentProvider || "openai",
          base_url: currentBaseUrl,
          model: currentModel,
          vision_model: configMap.VISION_MODEL || "",
          api_key: configMap.LLM_API_KEY || "",
        })
        setSimpleApiKey(configMap.LLM_API_KEY || "")
      } catch (error) {
        console.error("Failed to load LLM config", error)
      }
    }
    if (presetModels.length > 0) {
      fetchConfig()
    }
  }, [presetModels.length])

  // Handle model selection in simple mode
  const handleModelSelect = (modelId: string) => {
    setSelectedModelId(modelId)
    setTestResult(null)

    if (modelId === "custom") {
      setAdvancedMode(true)
      // Only set provider if not already set, otherwise keep current
      const currentProvider = form.getValues("provider")
      if (!currentProvider) {
        form.setValue("provider", "openai")
      }
      return
    }

    const preset = presetModels.find((m) => m.id === modelId)
    if (preset) {
      form.setValue("provider", preset.provider)
      form.setValue("base_url", preset.base_url)
      form.setValue("model", preset.model)
      form.setValue("vision_model", preset.vision_model)
    }
  }

  // Sync simpleApiKey to form when switching to advanced mode
  useEffect(() => {
    if (advancedMode && simpleApiKey) {
      form.setValue("api_key", simpleApiKey)
    }
  }, [advancedMode, simpleApiKey])

  // Handle switching back to simple mode - try to match current config to preset
  const handleModeSwitch = () => {
    const newMode = !advancedMode
    setAdvancedMode(newMode)
    setTestResult(null)

    if (!newMode) {
      // Switching to simple mode - try to find matching preset
      const values = form.getValues()
      const matchingPreset = presetModels.find(
        (m) =>
          m.provider === values.provider &&
          m.model === values.model &&
          m.base_url === values.base_url
      )
      if (matchingPreset) {
        setSelectedModelId(matchingPreset.id)
      } else if (values.model) {
        setSelectedModelId("custom")
      } else {
        setSelectedModelId("")
      }
      // Sync API key back to simple mode
      if (values.api_key) {
        setSimpleApiKey(values.api_key)
      }
    }
  }

  const onTestConnection = async () => {
    const values = form.getValues()
    setTesting(true)
    setTestResult(null)
    try {
      const res: any = await SystemService.testLlmConnection({
        requestBody: {
          provider: values.provider,
          base_url: values.base_url,
          model: values.model,
          api_key: values.api_key || simpleApiKey,
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
      setTestResult({ success: false, msg: t("settings.llm.connection_error") })
      toast.error(
        `${t("settings.llm.connection_error")}: ${(error as any).message}`,
      )
    } finally {
      setTesting(false)
    }
  }

  const onSubmit = async () => {
    const values = form.getValues()
    setLoading(true)
    try {
      await SystemService.applyLlmConfig({
        requestBody: {
          provider: values.provider,
          base_url: values.base_url,
          model: values.model,
          vision_model: values.vision_model,
          api_key: values.api_key || simpleApiKey,
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

  const selectedPreset = presetModels.find((m) => m.id === selectedModelId)

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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleModeSwitch}
          >
            {advancedMode ? t("common.simple") : t("common.advanced")}
            {advancedMode ? (
              <ChevronUp className="ml-1 h-4 w-4" />
            ) : (
              <ChevronDown className="ml-1 h-4 w-4" />
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Simple Mode */}
        {!advancedMode && (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                {t("settings.llm.select_model")}
              </label>
              <Select
                value={selectedModelId}
                onValueChange={handleModelSelect}
                disabled={isLoadingModels}
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={
                      isLoadingModels
                        ? t("common.loading")
                        : t("settings.llm.select_model_placeholder")
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {presetModels.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      <div className="flex flex-col">
                        <span>{model.name}</span>
                        {model.description && (
                          <span className="text-xs text-muted-foreground">
                            {model.description}
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                {selectedPreset?.description}
              </p>
            </div>

            {selectedModelId && selectedModelId !== "custom" && (
              <div className="space-y-2">
                <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                  {t("settings.modelFields.apiKey")}
                </label>
                <div className="relative">
                  <Input
                    type={showApiKey ? "text" : "password"}
                    placeholder="sk-..."
                    value={simpleApiKey}
                    onChange={(e) => setSimpleApiKey(e.target.value)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-0 top-0 h-9 w-9 text-muted-foreground hover:bg-transparent"
                    onClick={() => setShowApiKey(!showApiKey)}
                  >
                    {showApiKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">
                  {t("settings.modelFields.apiKeyDesc")}
                </p>
              </div>
            )}

            <div className="flex items-center gap-4 pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={onTestConnection}
                disabled={testing || loading || !selectedModelId}
              >
                {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("settings.llm.test_connection")}
              </Button>

              <Button
                type="button"
                onClick={onSubmit}
                disabled={loading || testing || !selectedModelId}
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("settings.llm.apply_btn")}
              </Button>
            </div>
          </div>
        )}

        {/* Advanced Mode */}
        {advancedMode && (
          <Form {...form}>
            <form className="space-y-4">
              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("settings.modelFields.provider")}</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      defaultValue={field.value}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="openai">OpenAI</SelectItem>
                        <SelectItem value="anthropic">Anthropic</SelectItem>
                        <SelectItem value="ollama">Ollama</SelectItem>
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
                      <FormLabel>{t("settings.modelFields.baseUrl")}</FormLabel>
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
                      <FormLabel>{t("settings.modelFields.modelName")}</FormLabel>
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
                name="vision_model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("settings.modelFields.visionModel")}</FormLabel>
                    <FormControl>
                      <Input placeholder="gpt-4o" {...field} />
                    </FormControl>
                    <FormDescription>
                      {t("settings.modelFields.visionModelDesc")}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("settings.modelFields.apiKey")}</FormLabel>
                    <div className="relative">
                      <FormControl>
                        <Input
                          type={showApiKey ? "text" : "password"}
                          placeholder="sk-..."
                          {...field}
                        />
                      </FormControl>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="absolute right-0 top-0 h-9 w-9 text-muted-foreground hover:bg-transparent"
                        onClick={() => setShowApiKey(!showApiKey)}
                      >
                        {showApiKey ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                    <FormDescription>
                      {t("settings.modelFields.apiKeyDesc")}
                    </FormDescription>
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

                <Button type="button" onClick={onSubmit} disabled={loading || testing}>
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("settings.llm.apply_btn")}
                </Button>
              </div>
            </form>
          </Form>
        )}

        {/* Test Result */}
        {testResult && (
          <div
            className={`mt-4 flex items-center gap-2 text-sm ${testResult.success ? "text-green-600" : "text-red-600"}`}
          >
            {testResult.success ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            {testResult.msg}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
