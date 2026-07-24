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
  Link2,
  Loader2,
  Server,
  Settings2,
  XCircle,
  ZapOff,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

type EmbeddingForm = {
  mode: string
  ggufModel: string
  localUrl: string
  localApiKey: string
  localModel: string
  provider: string
  baseUrl: string
  model: string
  apiKey: string
  dimensions: string
}

const MODE_OPTIONS = ["none", "gguf", "local", "remote"] as const

export function EmbeddingSettings() {
  const { t } = useTranslation()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    msg: string
  } | null>(null)
  const [activeTier, setActiveTier] = useState<string | null>(null)
  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()

  const [form, setForm] = useState<EmbeddingForm>({
    mode: "none",
    ggufModel: "",
    localUrl: "",
    localApiKey: "",
    localModel: "",
    provider: "",
    baseUrl: "",
    model: "",
    apiKey: "",
    dimensions: "",
  })
  const [initial, setInitial] = useState<EmbeddingForm | null>(null)

  const update = (key: keyof EmbeddingForm, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const isNone = form.mode === "none"
  const isGguf = form.mode === "gguf"
  const isLocal = form.mode === "local"
  const isRemote = form.mode === "remote"

  const fetchConfig = async () => {
    try {
      const configRes = await SystemService.getSystemConfig()
      const cfg: Record<string, string> = {}
      if (Array.isArray(configRes)) {
        configRes.forEach((item: any) => {
          cfg[item.key] = item.value
        })
      }
      // Detect mode from config
      let mode = "none"
      if (cfg.EMBEDDING_GGUF_MODEL) mode = "gguf"
      else if (cfg.EMBEDDING_LOCAL_URL) mode = "local"
      else if (cfg.EMBEDDING_PROVIDER) mode = "remote"

      const state: EmbeddingForm = {
        mode,
        ggufModel: cfg.EMBEDDING_GGUF_MODEL || "",
        localUrl: cfg.EMBEDDING_LOCAL_URL || "",
        localApiKey: cfg.EMBEDDING_LOCAL_API_KEY || "",
        localModel: cfg.EMBEDDING_LOCAL_MODEL || "",
        provider: cfg.EMBEDDING_PROVIDER || "",
        baseUrl: cfg.EMBEDDING_BASE_URL || "",
        model: cfg.CUSTOM_EMBEDDING_MODEL || cfg.EMBEDDING_MODEL || "",
        apiKey: cfg.EMBEDDING_API_KEY || "",
        dimensions: cfg.EMBEDDING_DIMENSIONS || "",
      }
      setForm(state)
      setInitial(state)
    } catch {
      toast.error(t("settings.embedding.loadError"))
    }
  }

  useEffect(() => {
    fetchConfig()
    // Fetch active tier status
    SystemService.getEmbeddingTierStatus()
      .then((res: any) => setActiveTier(res.active_tier || null))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!initial) return
    const dirty = JSON.stringify(form) !== JSON.stringify(initial)
    setComponentDirty("embedding", dirty)
  }, [form, initial, setComponentDirty])

  useEffect(() => {
    registerSaveHandler("embedding", async () => {
      const tiers = form.mode === "none" ? "" : form.mode
      await SystemService.applyEmbeddingTierConfig({
        requestBody: {
          tiers,
          gguf_model: form.mode === "gguf" ? form.ggufModel || null : null,
          local_url: form.mode === "local" ? form.localUrl || null : null,
          local_api_key:
            form.mode === "local" ? form.localApiKey || null : null,
          local_model: form.mode === "local" ? form.localModel || null : null,
          provider: form.mode === "remote" ? form.provider || null : null,
          base_url: form.mode === "remote" ? form.baseUrl || null : null,
          model: form.mode === "remote" ? form.model || null : null,
          api_key: form.mode === "remote" ? form.apiKey || null : null,
          dimensions:
            form.mode === "remote" ? Number(form.dimensions) || null : null,
        },
      })
    })
    registerResetHandler("embedding", () => {
      if (initial) setForm({ ...initial })
    })
    return () => {
      unregisterSaveHandler("embedding")
    }
  }, [
    form,
    initial,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  ])

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const tiers = form.mode === "none" ? "" : form.mode
      const res = await SystemService.testEmbeddingTierConnection({
        requestBody: {
          tiers,
          gguf_model: form.mode === "gguf" ? form.ggufModel || null : null,
          local_url: form.mode === "local" ? form.localUrl || null : null,
          local_api_key:
            form.mode === "local" ? form.localApiKey || null : null,
          local_model: form.mode === "local" ? form.localModel || null : null,
          provider: form.mode === "remote" ? form.provider || null : null,
          base_url: form.mode === "remote" ? form.baseUrl || null : null,
          model: form.mode === "remote" ? form.model || null : null,
          api_key: form.mode === "remote" ? form.apiKey || null : null,
          dimensions:
            form.mode === "remote" ? Number(form.dimensions) || null : null,
        },
      })
      const ok = res.success ?? false
      setTestResult({
        success: ok,
        msg: ok
          ? t("settings.embedding.connectedWithDim", {
              dim: res.dimensions || "?",
            })
          : res.error || t("settings.embedding.connection_failed"),
      })
    } catch (e: any) {
      setTestResult({
        success: false,
        msg: t("settings.embedding.connection_error", {
          message: e.message || "",
        }),
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <SettingsCard
      icon={Link2}
      title={t("settings.embedding.title")}
      description={t("settings.embedding.description")}
      iconClassName="text-purple-600 bg-purple-600/10"
    >
      <div className="space-y-6">
        {/* Mode Selector */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">
            {t("settings.embedding.mode")}
          </Label>
          <Select value={form.mode} onValueChange={(v) => update("mode", v)}>
            <SelectTrigger className="h-10">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODE_OPTIONS.map((m) => (
                <SelectItem key={m} value={m}>
                  <span className="flex items-center gap-2">
                    {m === "none" && (
                      <ZapOff className="h-4 w-4 text-muted-foreground" />
                    )}
                    {m === "gguf" && <Cpu className="h-4 w-4 text-amber-500" />}
                    {m === "local" && (
                      <Server className="h-4 w-4 text-blue-500" />
                    )}
                    {m === "remote" && (
                      <Globe className="h-4 w-4 text-green-500" />
                    )}
                    {m === "none" && "Disabled"}
                    {m === "gguf" && "GGUF (llama.cpp)"}
                    {m === "local" && "Local HTTP (LM Studio / Ollama)"}
                    {m === "remote" && "Remote API"}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isNone && (
            <p className="text-xs text-muted-foreground mt-1">
              {t("settings.embedding.none_hint")}
            </p>
          )}
          {activeTier && !isNone && (
            <p className="text-xs text-muted-foreground mt-1">
              {t("settings.embedding.active_tier", { tier: activeTier })}
            </p>
          )}
        </div>

        {isGguf && (
          <div className="space-y-3">
            <Label className="text-sm font-medium">
              {t("settings.embedding.ggufModel")}
            </Label>
            <Input
              placeholder="/path/to/bge-base-zh-v1.5-q4_k_m.gguf"
              value={form.ggufModel}
              onChange={(e) => update("ggufModel", e.target.value)}
              className="h-10 transition-colors focus:border-primary"
            />
            <p className="text-xs text-muted-foreground">
              {t("settings.embedding.gguf_hint", {
                cmd: "uv run python scripts/download_models.py bge-base-zh-v1.5",
              })}
            </p>
          </div>
        )}

        {isLocal && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.localUrl")}
                </Label>
                <Input
                  placeholder="http://localhost:1234/v1"
                  value={form.localUrl}
                  onChange={(e) => update("localUrl", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.localApiKey")}
                </Label>
                <Input
                  placeholder="lm-studio"
                  value={form.localApiKey}
                  onChange={(e) => update("localApiKey", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">
                {t("settings.embedding.localModel")}
              </Label>
              <Input
                placeholder="text-embedding-nomic-embed-text-v1.5"
                value={form.localModel}
                onChange={(e) => update("localModel", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </>
        )}

        {isRemote && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.provider")}
                </Label>
                <Input
                  placeholder="openai"
                  value={form.provider}
                  onChange={(e) => update("provider", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.baseUrl")}
                </Label>
                <Input
                  placeholder="https://api.openai.com/v1"
                  value={form.baseUrl}
                  onChange={(e) => update("baseUrl", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.model")}
                </Label>
                <Input
                  placeholder="text-embedding-3-small"
                  value={form.model}
                  onChange={(e) => update("model", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
              <div className="space-y-3">
                <Label className="text-sm font-medium">
                  {t("settings.embedding.dimensions")}
                </Label>
                <Input
                  placeholder="1536"
                  value={form.dimensions}
                  onChange={(e) => update("dimensions", e.target.value)}
                  className="h-10 transition-colors focus:border-primary"
                />
              </div>
            </div>
            <div className="space-y-3">
              <Label className="text-sm font-medium">
                {t("settings.embedding.apiKey")}
              </Label>
              <Input
                placeholder="sk-..."
                value={form.apiKey}
                onChange={(e) => update("apiKey", e.target.value)}
                className="h-10 transition-colors focus:border-primary"
              />
            </div>
          </>
        )}

        {/* Test */}
        <div className="flex flex-col gap-4">
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={testing || isNone}
            className="w-full h-11 border-dashed hover:border-purple-500/50 hover:bg-purple-500/5 hover:text-purple-600 transition-all"
          >
            {testing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Settings2 className="mr-2 h-4 w-4 text-purple-500" />
            )}
            {t("settings.embedding.test_connection")}
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
