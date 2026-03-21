import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Eye, EyeOff, Loader2, XCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { SystemService, type SystemConfig } from "@/client"
import { Alert, AlertDescription, AlertTitle } from "@evoloop/shared/components/ui/alert"
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

  // Fetch preset models from backend
  const { data: presetModelsData, isLoading: isLoadingModels } = useQuery({
    queryKey: ["embeddingPresetModels"],
    queryFn: () => SystemService.getAvailableEmbeddingModels(),
  })

  const presetModels: PresetEmbeddingModel[] = (presetModelsData as any)?.models || []

  // Unified form
  const form = useForm({
    defaultValues: {
      selectedModel: "",
      provider: "openai",
      base_url: "",
      model: "",
      dimensions: "768",
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

        const currentProvider = configMap.EMBEDDING_PROVIDER || ""
        const currentModel = configMap.EMBEDDING_MODEL || ""
        const currentBaseUrl = configMap.EMBEDDING_BASE_URL || ""
        const currentDimensions = configMap.EMBEDDING_DIMENSIONS || "768"
        const currentApiKey = configMap.EMBEDDING_API_KEY || ""

        // Try to find matching preset model
        const matchingPreset = presetModels.find(
          (m) =>
            m.provider === currentProvider &&
            m.model === currentModel &&
            m.base_url === currentBaseUrl
        )

        if (matchingPreset) {
          form.reset({
            selectedModel: matchingPreset.id,
            provider: matchingPreset.provider,
            base_url: currentBaseUrl,
            model: currentModel,
            dimensions: currentDimensions,
            api_key: currentApiKey,
          })
        } else if (currentModel) {
          // Custom config
          form.reset({
            selectedModel: "custom",
            provider: currentProvider || "openai",
            base_url: currentBaseUrl,
            model: currentModel,
            dimensions: currentDimensions,
            api_key: currentApiKey,
          })
        }
      } catch (error) {
        console.error("Failed to load embedding config", error)
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
      form.setValue("dimensions", "768")
      return
    }

    // Apply preset model config
    const preset = presetModels.find((m) => m.id === value)
    if (preset) {
      form.setValue("provider", preset.provider)
      form.setValue("base_url", preset.base_url)
      form.setValue("model", preset.model)
      form.setValue("dimensions", String(preset.dimensions))
    }
  }

  const onTestConnection = async () => {
    const values = form.getValues()
    setTesting(true)
    setTestResult(null)

    const preset = presetModels.find((m) => m.id === values.selectedModel)
    const actualProvider = preset ? preset.provider : values.provider
    const actualBaseUrl = preset ? preset.base_url : values.base_url
    const actualModel = preset ? preset.model : values.model

    try {
      const res: any = await SystemService.testEmbeddingConnection({
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
          msg: t("settings.embedding.success_connected", {
            dim: res.dimensions,
          }),
        })
        toast.success(
          t("settings.embedding.success_connected", { dim: res.dimensions }),
        )
      } else {
        setTestResult({
          success: false,
          msg: t("settings.embedding.error_connection"),
        })
        toast.error(t("settings.embedding.error_connection"))
      }
    } catch (error) {
      setTestResult({
        success: false,
        msg: t("settings.embedding.error_connection"),
      })
      toast.error(
        `${t("settings.embedding.error_connection")}: ${(error as any).message}`,
      )
    } finally {
      setTesting(false)
    }
  }

  const onSubmit = async () => {
    if (!confirm(t("settings.embedding.confirm_switch"))) {
      return
    }

    const values = form.getValues()
    setLoading(true)

    const preset = presetModels.find((m) => m.id === values.selectedModel)
    const actualProvider = preset ? preset.provider : values.provider
    const actualBaseUrl = preset ? preset.base_url : values.base_url
    const actualModel = preset ? preset.model : values.model

    try {
      await SystemService.applyEmbeddingConfig({
        requestBody: {
          provider: actualProvider,
          base_url: actualBaseUrl,
          model: actualModel,
          dimensions: parseInt(values.dimensions || "768", 10),
          api_key: values.api_key,
          project_id: undefined,
        },
      })
      toast.success(t("settings.embedding.success_updated"))
      setTestResult(null)
    } catch (_error) {
      toast.error(t("settings.embedding.error_update"))
    } finally {
      setLoading(false)
    }
  }

  const selectedPreset = presetModels.find((m) => m.id === selectedModelId)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.embedding.title")}</CardTitle>
        <CardDescription>{t("settings.embedding.description")}</CardDescription>
        <Alert variant="destructive" className="mt-4">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("settings.embedding.warning")}</AlertTitle>
          <AlertDescription>{t("settings.embedding.warning_desc")}</AlertDescription>
        </Alert>
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
                  <FormLabel>{t("settings.embedding.select_model")}</FormLabel>
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
                              : t("settings.embedding.select_model_placeholder")
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
                <div className="grid grid-cols-3 gap-3">
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
                  <FormField
                    control={form.control}
                    name="dimensions"
                    render={({ field }) => (
                      <FormItem className="space-y-1">
                        <FormLabel className="text-xs">{t("settings.modelFields.dimensions")}</FormLabel>
                        <FormControl>
                          <Input type="number" placeholder="768" {...field} className="h-8" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="model"
                  render={({ field }) => (
                    <FormItem className="space-y-1">
                      <FormLabel className="text-xs">{t("settings.modelFields.modelName")}</FormLabel>
                      <FormControl>
                        <Input placeholder="text-embedding-3-small" {...field} className="h-8" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            {/* API Key */}
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
                  disabled={testing || loading || !selectedModelId}
                >
                  {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("settings.embedding.test_connection")}
                </Button>

                <Button
                  type="button"
                  onClick={onSubmit}
                  disabled={loading || testing || !selectedModelId}
                  className="bg-red-600 hover:bg-red-700 text-white"
                >
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("settings.embedding.apply_btn")}
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
