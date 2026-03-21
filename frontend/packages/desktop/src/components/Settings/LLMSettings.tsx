import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Eye, EyeOff, Loader2, XCircle } from "lucide-react"
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

  // Unified form - selectedModel stores the model ID or "custom"
  const form = useForm({
    defaultValues: {
      selectedModel: "",  // preset model id or "custom"
      provider: "openai", // actual provider for custom mode
      base_url: "",
      model: "",
      vision_model: "",
      api_key: "",
    },
  })

  const selectedModelId = form.watch("selectedModel")
  const isCustom = selectedModelId === "custom"

  // Load initial config
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await SystemService.getSystemConfig()
        const configMap: Record<string, string> = {}
        if (Array.isArray(response)) {
          ;(response as unknown as SystemConfig[]).forEach((item) => {
            configMap[item.key] = item.value
          })
        }

        const currentProvider = configMap.LLM_PROVIDER || ""
        const currentModel = configMap.LLM_MODEL || ""
        const currentBaseUrl = configMap.LLM_BASE_URL || ""
        const currentVisionModel = configMap.VISION_MODEL || ""
        const currentApiKey = configMap.LLM_API_KEY || ""

        // Try to find matching preset model
        const matchingPreset = presetModels.find(
          (m) =>
            m.provider === currentProvider &&
            m.model === currentModel &&
            m.base_url === currentBaseUrl
        )

        if (matchingPreset) {
          // Use preset model
          form.reset({
            selectedModel: matchingPreset.id,
            provider: matchingPreset.provider,
            base_url: currentBaseUrl,
            model: currentModel,
            vision_model: currentVisionModel,
            api_key: currentApiKey,
          })
        } else if (currentModel) {
          // Custom config
          form.reset({
            selectedModel: "custom",
            provider: currentProvider || "openai",
            base_url: currentBaseUrl,
            model: currentModel,
            vision_model: currentVisionModel,
            api_key: currentApiKey,
          })
        }
      } catch (error) {
        console.error("Failed to load LLM config", error)
      }
    }
    if (presetModels.length > 0) {
      fetchConfig()
    }
  }, [presetModels.length, form])

  // Handle model selection
  const handleModelSelect = (value: string) => {
    setTestResult(null)
    form.setValue("selectedModel", value)

    if (value === "custom") {
      // Clear custom fields for user to fill
      form.setValue("provider", "openai")
      form.setValue("base_url", "")
      form.setValue("model", "")
      form.setValue("vision_model", "")
      return
    }

    // Apply preset model config
    const preset = presetModels.find((m) => m.id === value)
    if (preset) {
      form.setValue("provider", preset.provider)
      form.setValue("base_url", preset.base_url)
      form.setValue("model", preset.model)
      form.setValue("vision_model", preset.vision_model)
    }
  }

  const onTestConnection = async () => {
    const values = form.getValues()
    setTesting(true)
    setTestResult(null)

    // Get actual provider - either from preset or custom
    const preset = presetModels.find((m) => m.id === values.selectedModel)
    const actualProvider = preset ? preset.provider : values.provider
    const actualBaseUrl = preset ? preset.base_url : values.base_url
    const actualModel = preset ? preset.model : values.model

    try {
      const res: any = await SystemService.testLlmConnection({
        requestBody: {
          provider: actualProvider,
          base_url: actualBaseUrl,
          model: actualModel,
          api_key: values.api_key,
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

    // Get actual config - either from preset or custom
    const preset = presetModels.find((m) => m.id === values.selectedModel)
    const actualProvider = preset ? preset.provider : values.provider
    const actualBaseUrl = preset ? preset.base_url : values.base_url
    const actualModel = preset ? preset.model : values.model
    const actualVisionModel = preset ? preset.vision_model : values.vision_model

    try {
      await SystemService.applyLlmConfig({
        requestBody: {
          provider: actualProvider,
          base_url: actualBaseUrl,
          model: actualModel,
          vision_model: actualVisionModel,
          api_key: values.api_key,
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
        <CardTitle>{t("settings.llm.title")}</CardTitle>
        <CardDescription>{t("settings.llm.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form className="space-y-4">
            {/* Model Selection */}
            <FormField
              control={form.control}
              name="selectedModel"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("settings.llm.select_model")}</FormLabel>
                  <Select
                    value={field.value}
                    onValueChange={handleModelSelect}
                    disabled={isLoadingModels}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue
                          placeholder={
                            isLoadingModels
                              ? t("common.loading")
                              : t("settings.llm.select_model_placeholder")
                          }
                        />
                      </SelectTrigger>
                    </FormControl>
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
                      <SelectItem value="custom">
                        <span className="font-medium">{t("settings.llm.custom")}</span>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {!isCustom && selectedPreset?.description && (
                    <FormDescription>{selectedPreset.description}</FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Custom Configuration Fields - Only show when custom is selected */}
            {isCustom && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <FormField
                    control={form.control}
                    name="provider"
                    render={({ field }) => (
                      <FormItem className="space-y-1">
                        <FormLabel className="text-xs">{t("settings.modelFields.provider")}</FormLabel>
                        <FormControl>
                          <Input placeholder="openai" {...field} className="h-8" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="base_url"
                    render={({ field }) => (
                      <FormItem className="space-y-1">
                        <FormLabel className="text-xs">{t("settings.modelFields.baseUrl")}</FormLabel>
                        <FormControl>
                          <Input placeholder="https://api.openai.com/v1" {...field} className="h-8" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <FormField
                    control={form.control}
                    name="model"
                    render={({ field }) => (
                      <FormItem className="space-y-1">
                        <FormLabel className="text-xs">{t("settings.modelFields.modelName")}</FormLabel>
                        <FormControl>
                          <Input placeholder="gpt-4o" {...field} className="h-8" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="vision_model"
                    render={({ field }) => (
                      <FormItem className="space-y-1">
                        <FormLabel className="text-xs">{t("settings.modelFields.visionModel")}</FormLabel>
                        <FormControl>
                          <Input placeholder="gpt-4o" {...field} className="h-8" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>
            )}

            {/* API Key - Show when any model is selected */}
            {selectedModelId && (
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
            )}

            {/* Action Buttons */}
            {selectedModelId && (
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
                  type="button"
                  onClick={onSubmit}
                  disabled={loading || testing}
                >
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("settings.llm.apply_btn")}
                </Button>
              </div>
            )}

            {/* Test Result */}
            {testResult && (
              <div
                className={`flex items-center gap-2 text-sm ${testResult.success ? "text-green-600" : "text-red-600"}`}
              >
                {testResult.success ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                {testResult.msg}
              </div>
            )}
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}
