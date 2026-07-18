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
import {
  CheckCircle2,
  Cpu,
  Globe,
  Loader2,
  Server,
  Settings2,
  XCircle,
  Zap,
  ZapOff,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

type LightningForm = {
  mode: string
  llmModel: string
  baseUrl: string
  apiKey: string
  contextWindow: string
}

const MODE_OPTIONS = ["none", "llama.cpp", "lm-studio", "ollama"] as const

export function LightningSettings() {
  const { t } = useTranslation()
  const [testing, setTesting] = useState(false)
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

  const [form, setForm] = useState<LightningForm>({
    mode: "none",
    llmModel: "",
    baseUrl: "",
    apiKey: "",
    contextWindow: "8192",
  })
  const [initial, setInitial] = useState<LightningForm | null>(null)

  const update = (key: keyof LightningForm, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const fetchConfig = async () => {
    try {
      const configRes = await SystemService.getSystemConfig()
      const cfg: Record<string, string> = {}
      if (Array.isArray(configRes)) {
        configRes.forEach((item: any) => {
          cfg[item.key] = item.value
        })
      }
      const state: LightningForm = {
        mode: cfg.LIGHTNING_MODE || "none",
        llmModel: cfg.LIGHTNING_LLM_MODEL || "",
        baseUrl: cfg.LIGHTNING_BASE_URL || "",
        apiKey: cfg.LIGHTNING_API_KEY || "",
        contextWindow: cfg.LIGHTNING_CTX || "8192",
      }
      setForm(state)
      setInitial(state)
    } catch {
      toast.error(t("settings.lightning.loadError"))
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  useEffect(() => {
    if (!initial) return
    const dirty =
      form.mode !== initial.mode ||
      form.llmModel !== initial.llmModel ||
      form.baseUrl !== initial.baseUrl ||
      form.apiKey !== initial.apiKey ||
      form.contextWindow !== initial.contextWindow
    setComponentDirty("lightning", dirty)
  }, [form, initial, setComponentDirty])

  useEffect(() => {
    registerSaveHandler("lightning", async () => {
      await SystemService.applyLightningConfig({
        requestBody: {
          mode: form.mode,
          llm_model: form.llmModel || null,
          base_url: form.baseUrl || null,
          api_key: form.apiKey || null,
          context_window: Number(form.contextWindow) || null,
        },
      })
    })
    registerResetHandler("lightning", () => {
      if (initial) setForm({ ...initial })
    })
    return () => {
      unregisterSaveHandler("lightning")
    }
  }, [form, initial, registerSaveHandler, unregisterSaveHandler, registerResetHandler])

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await SystemService.testLightningConnection({
        requestBody: {
          mode: form.mode,
          llm_model: form.llmModel || null,
          base_url: form.baseUrl || null,
          api_key: form.apiKey || null,
          context_window: Number(form.contextWindow) || null,
        },
      })
      setTestResult({
        success: res.llm_ok,
        msg: res.llm_ok
          ? t("settings.lightning.connected")
          : (res.llm_reply || t("settings.lightning.connection_failed")),
      })
    } catch (e: any) {
      setTestResult({
        success: false,
        msg: t("settings.lightning.connection_error", { message: e.message || "" }),
      })
    } finally {
      setTesting(false)
    }
  }

  const showHttp = form.mode === "lm-studio" || form.mode === "ollama"
  const showGGUF = form.mode === "llama.cpp"
  const isNone = form.mode === "none"

  return (
    <SettingsCard
      icon={Zap}
      title={t("settings.lightning.title")}
      description={t("settings.lightning.description")}
      iconClassName="text-amber-600 bg-amber-600/10"
    >
      <div className="space-y-6">
        {/* Mode Selector */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">{t("settings.lightning.mode")}</Label>
          <Select value={form.mode} onValueChange={(v) => update("mode", v)}>
            <SelectTrigger className="h-10">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODE_OPTIONS.map((m) => (
                <SelectItem key={m} value={m}>
                  <span className="flex items-center gap-2">
                    {m === "none" && <ZapOff className="h-4 w-4 text-muted-foreground" />}
                    {m === "llama.cpp" && <Cpu className="h-4 w-4 text-amber-500" />}
                    {m === "lm-studio" && <Server className="h-4 w-4 text-blue-500" />}
                    {m === "ollama" && <Globe className="h-4 w-4 text-green-500" />}
                    {m}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isNone && (
            <p className="text-xs text-muted-foreground mt-1">{t("settings.lightning.none_hint")}</p>
          )}
        </div>

        {showGGUF && (
          <>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.lightning.llmModel")}</Label>
              <Input
                placeholder={t("settings.lightning.llmModelPlaceholder")}
                value={form.llmModel}
                onChange={(e) => update("llmModel", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
              <p className="text-xs text-muted-foreground">
                {t("settings.lightning.gguf_hint", { cmd: "uv run python scripts/download_models.py qwen3-4b-instruct-2507" })}
              </p>
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.lightning.contextWindow")}</Label>
              <Input
                type="number"
                value={form.contextWindow}
                onChange={(e) => update("contextWindow", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </>
        )}

        {showHttp && (
          <>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.lightning.baseUrl")}</Label>
              <Input
                placeholder={form.mode === "ollama" ? "http://localhost:11434/v1" : "http://localhost:1234/v1"}
                value={form.baseUrl}
                onChange={(e) => update("baseUrl", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.lightning.apiKey")}</Label>
              <Input
                placeholder={form.mode === "ollama" ? "" : "lm-studio"}
                value={form.apiKey}
                onChange={(e) => update("apiKey", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">{t("settings.lightning.llmModel")}</Label>
              <Input
                placeholder={t("settings.lightning.llmModelPlaceholder")}
                value={form.llmModel}
                onChange={(e) => update("llmModel", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </>
        )}

        {/* Test Connection */}
        <div className="flex flex-col gap-4">
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={testing || isNone}
            className="w-full h-11 border-dashed hover:border-amber-500/50 hover:bg-amber-500/5 hover:text-amber-600 transition-all"
          >
            {testing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Settings2 className="mr-2 h-4 w-4 text-amber-500" />
            )}
            {t("settings.lightning.test_connection")}
          </Button>

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
  )
}
