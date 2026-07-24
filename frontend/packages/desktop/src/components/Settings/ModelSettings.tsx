import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Globe,
  Loader2,
  Server,
  Sparkles,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { SystemService } from "@/client"
import { EmbeddingSettings } from "./EmbeddingSettings"
import { LightningSettings } from "./LightningSettings"
import { LLMSettings } from "./LLMSettings"
import { SettingsCard } from "./SettingsCard"

interface ModelOption {
  id: string
  name: string
  source: string
  status: string
  model_name: string
  base_url?: string | null
}

const SOURCE_ICONS: Record<string, typeof Cpu> = {
  evocloud: Sparkles,
  "lm-studio": Server,
  ollama: Globe,
  gguf: Cpu,
  custom: Brain,
}

const SOURCE_LABELS: Record<string, string> = {
  evocloud: "Cloud",
  "lm-studio": "LM Studio",
  ollama: "Ollama",
  gguf: "Local",
  custom: "Custom",
}

export function ModelSettings() {
  const { t } = useTranslation()
  const [models, setModels] = useState<ModelOption[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [status, setStatus] = useState<"idle" | "testing" | "ok" | "error">(
    "idle",
  )

  useEffect(() => {
    loadModels()
  }, [])

  const saveModel = async (modelId: string) => {
    const model = models.find((m) => m.id === modelId)
    if (!model) return
    // Save the selected model as the default LLM model
    try {
      await SystemService.applyLlmConfig({
        requestBody: {
          provider: model.source,
          provider_type: "openai",
          base_url: model.base_url || null,
          model: model.model_name,
          api_key: model.source === "lm-studio" ? "lm-studio" : null,
        },
      })
    } catch (e) {
      console.error("Failed to save model selection:", e)
    }
  }

  const loadModels = async () => {
    setLoading(true)
    try {
      const [discovered, configRes] = await Promise.all([
        SystemService.discoverModels().catch(() => ({ models: [] })),
        SystemService.getSystemConfig().catch(() => []),
      ])

      const cfg: Record<string, string> = {}
      if (Array.isArray(configRes)) {
        configRes.forEach((item: any) => {
          cfg[item.key] = item.value
        })
      }

      const list: ModelOption[] = (discovered.models || []).map((m: any) => ({
        id: m.id,
        name: m.name,
        source: m.source,
        status: m.status || "unknown",
        model_name: m.model_name,
        base_url: m.base_url,
      }))

      // Also add from existing custom config
      if (cfg.CUSTOM_LLM_MODEL && cfg.LLM_BASE_URL) {
        const exists = list.some(
          (m) => m.source === "custom" && m.model_name === cfg.CUSTOM_LLM_MODEL,
        )
        if (!exists) {
          list.push({
            id: `custom:${cfg.CUSTOM_LLM_MODEL}`,
            name: `${cfg.CUSTOM_LLM_MODEL} (Custom)`,
            source: "custom",
            status: "available",
            model_name: cfg.CUSTOM_LLM_MODEL,
            base_url: cfg.LLM_BASE_URL,
          })
        }
      }

      setModels(list)

      // Restore previous selection or default to first
      const saved = cfg.LLM_MODEL || ""
      const match = list.find((m) => m.id === saved || m.model_name === saved)
      if (match) {
        setSelectedId(match.id)
      } else if (list.length > 0) {
        setSelectedId(list[0].id)
      }
    } catch (e) {
      console.error("Failed to load models", e)
    } finally {
      setLoading(false)
    }
  }

  const selectedModel = models.find((m) => m.id === selectedId)

  const handleTest = async () => {
    if (!selectedModel) return
    setTesting(true)
    setStatus("testing")
    try {
      if (selectedModel.source === "evocloud") {
        // Test via existing connection
        setStatus("ok")
        return
      }
      const baseUrl = selectedModel.base_url || ""
      const modelName = selectedModel.model_name
      const apiKey = selectedModel.source === "lm-studio" ? "lm-studio" : ""
      const res = await SystemService.testLlmConnection({
        requestBody: {
          provider: selectedModel.source,
          provider_type: "openai",
          base_url: baseUrl,
          model: modelName,
          api_key: apiKey,
        },
      })
      setStatus(res.success ? "ok" : "error")
    } catch {
      setStatus("error")
    } finally {
      setTesting(false)
    }
  }

  const sourceIcon = selectedModel
    ? SOURCE_ICONS[selectedModel.source] || Brain
    : Brain
  const IconComponent = sourceIcon

  return (
    <div className="space-y-6">
      {/* Default View: Model Selector */}
      <SettingsCard
        icon={Brain}
        title={t("settings.models.default_view.title")}
        description={t("settings.models.default_view.description")}
        iconClassName="text-primary"
      >
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("common.loading")}
            </div>
          ) : (
            <>
              <div className="space-y-3">
                <Select
                  value={selectedId}
                  onValueChange={(id) => {
                    setSelectedId(id)
                    saveModel(id)
                  }}
                >
                  <SelectTrigger className="h-12 text-base">
                    <SelectValue
                      placeholder={t(
                        "settings.models.default_view.select_placeholder",
                      )}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => {
                      const SrcIcon = SOURCE_ICONS[m.source] || Brain
                      const color =
                        m.source === "evocloud"
                          ? "text-blue-500"
                          : m.source === "lm-studio"
                            ? "text-amber-500"
                            : m.source === "ollama"
                              ? "text-green-500"
                              : m.source === "gguf"
                                ? "text-purple-500"
                                : "text-muted-foreground"
                      return (
                        <SelectItem key={m.id} value={m.id}>
                          <span className="flex items-center gap-2">
                            <SrcIcon className={`h-4 w-4 ${color}`} />
                            <span>{m.name}</span>
                            <Badge
                              variant="outline"
                              className="ml-auto text-[10px] px-1.5 py-0"
                            >
                              {SOURCE_LABELS[m.source] || m.source}
                            </Badge>
                          </span>
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>

              {selectedModel && (
                <div className="rounded-lg bg-muted/30 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      <IconComponent className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{selectedModel.name}</span>
                      <Badge variant="secondary" className="text-[10px]">
                        {SOURCE_LABELS[selectedModel.source] ||
                          selectedModel.source}
                      </Badge>
                    </div>
                    <Badge
                      variant={
                        status === "ok"
                          ? "secondary"
                          : status === "error"
                            ? "destructive"
                            : "outline"
                      }
                      className="gap-1"
                    >
                      {status === "testing" && (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      )}
                      {status === "ok" && (
                        <CheckCircle2 className="h-3 w-3 text-green-500" />
                      )}
                      {status === "error" && <XCircle className="h-3 w-3" />}
                      {status === "idle" && (
                        <ChevronRight className="h-3 w-3" />
                      )}
                      {status === "testing"
                        ? t("common.testing")
                        : status === "ok"
                          ? t("common.connected")
                          : status === "error"
                            ? t("common.disconnected")
                            : t("settings.models.default_view.untested")}
                    </Badge>
                  </div>
                  {selectedModel.base_url && (
                    <p className="text-xs text-muted-foreground truncate">
                      {selectedModel.base_url}
                    </p>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleTest}
                    disabled={testing}
                    className="w-full h-9"
                  >
                    {testing ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {t("settings.models.default_view.test_connection")}
                  </Button>
                </div>
              )}

              {models.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  {t("settings.models.default_view.no_models")}
                </p>
              )}
            </>
          )}
        </div>
      </SettingsCard>

      {/* Advanced Settings (collapsible) */}
      <Collapsible className="border rounded-lg">
        <CollapsibleTrigger className="flex w-full items-center justify-between p-4 text-sm font-medium hover:bg-muted/20 transition-colors">
          <span>{t("settings.models.advanced.title")}</span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-6 px-4 pb-4">
            <LLMSettings />
            <LightningSettings />
            <EmbeddingSettings />
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
