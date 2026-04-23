import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Eye, EyeOff, Loader2, XCircle } from "lucide-react"
import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { SystemService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import { useWizard } from "../WizardContext"

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

export function LLMConfigStep() {
  const { t } = useTranslation()
  const { data, setData, setCanProceed } = useWizard()
  const [testing, setTesting] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    msg: string
  } | null>(null)

  // Fetch preset models from backend
  const { data: presetModelsData, isLoading: isLoadingModels } = useQuery({
    queryKey: ["llmPresetModels"],
    queryFn: () => SystemService.getLlmModels(),
  })

  const presetModels: PresetModel[] = (presetModelsData as any)?.models || []

  // Initialize with first preset if empty
  useEffect(() => {
    if (!data.llmProvider && presetModels.length > 0) {
      const firstPreset = presetModels[0]
      setData({
        llmProvider: firstPreset.provider,
        llmBaseUrl: firstPreset.base_url,
        llmModel: firstPreset.model,
        llmVisionModel: firstPreset.vision_model,
        llmTested: false,
      })
    }
  }, [data.llmProvider, presetModels, setData])

  // Update canProceed based on test result
  useEffect(() => {
    setCanProceed(data.llmTested && testResult?.success === true)
  }, [data.llmTested, testResult, setCanProceed])

  // Sync defaultModelId for custom mode when fields change
  useEffect(() => {
    if (selectedModelId === "custom") {
      const newCustomId = `custom-${data.llmProvider}-${data.llmModel}`
      if (data.defaultModelId !== newCustomId && data.llmProvider && data.llmModel) {
        setData({ defaultModelId: newCustomId })
      }
    }
  }, [data.llmProvider, data.llmModel, data.defaultModelId, setData])

  const selectedModelId = data.selectedModelId || ""
  const isCustom = selectedModelId === "custom"

  const handleModelSelect = (value: string) => {
    setTestResult(null)
    
    if (value === "custom") {
      setData({
        selectedModelId: "custom",
        defaultModelId: "", // Will be set on test success or next
        llmProvider: "openai",
        llmBaseUrl: "",
        llmModel: "",
        llmVisionModel: "",
        llmTested: false,
      })
      return
    }

    // Apply preset
    const preset = presetModels.find((m) => m.id === value)
    if (preset) {
      setData({
        selectedModelId: value,
        defaultModelId: value,
        llmProvider: preset.provider,
        llmBaseUrl: preset.base_url,
        llmModel: preset.model,
        llmVisionModel: preset.vision_model,
        llmTested: false,
      })
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
        
        let finalDefaultId = data.selectedModelId
        if (data.selectedModelId === "custom") {
          finalDefaultId = `custom-${data.llmProvider}-${data.llmModel}`
        }

        setData({ 
          llmTested: true,
          defaultModelId: finalDefaultId 
        })
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

  const selectedPreset = presetModels.find((m) => m.id === selectedModelId)

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
        {/* Model Selection */}
        <div className="space-y-2">
          <Label>{t("wizard.llm.selectModel")}</Label>
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
                    : t("wizard.llm.selectModelPlaceholder")
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
              <SelectItem value="custom">
                <span className="font-medium">
                  {t("settings.llm.custom")}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          {!isCustom && selectedPreset?.description && (
            <p className="text-sm text-muted-foreground">
              {selectedPreset.description}
            </p>
          )}
        </div>

        {/* Custom Fields - Only show when custom is selected */}
        {isCustom && (
          <>
            {/* Provider - Text Input for flexibility */}
            <div className="space-y-2">
              <Label>{t("settings.modelFields.provider")}</Label>
              <Input
                value={data.llmProvider || ""}
                onChange={(e) => {
                  setData({ llmProvider: e.target.value, llmTested: false })
                  setTestResult(null)
                }}
                placeholder="openai"
              />
              <p className="text-xs text-muted-foreground">
                {t("settings.modelFields.providerHint")}
              </p>
            </div>

            {/* Base URL */}
            <div className="space-y-2">
              <Label>{t("wizard.llm.baseUrl")}</Label>
              <Input
                value={data.llmBaseUrl || ""}
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
                value={data.llmModel || ""}
                onChange={(e) => {
                  setData({ llmModel: e.target.value, llmTested: false })
                  setTestResult(null)
                }}
                placeholder="gpt-4o"
              />
            </div>

            {/* Vision Model */}
            <div className="space-y-2">
              <Label>{t("settings.modelFields.visionModel")}</Label>
              <Input
                value={data.llmVisionModel || ""}
                onChange={(e) => {
                  setData({ llmVisionModel: e.target.value, llmTested: false })
                  setTestResult(null)
                }}
                placeholder="gpt-4o"
              />
              <p className="text-xs text-muted-foreground">
                {t("settings.modelFields.visionModelDesc")}
              </p>
            </div>
          </>
        )}

        {/* API Key */}
        <div className="space-y-2">
          <Label>{t("wizard.llm.apiKey")}</Label>
          <div className="relative">
            <Input
              type={showApiKey ? "text" : "password"}
              value={data.llmApiKey || ""}
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
              className={`flex items-center gap-2 mt-3 text-sm ${
                testResult.success ? "text-green-600" : "text-red-600"
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
