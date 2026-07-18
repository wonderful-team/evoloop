import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  CheckCircle2,
  Cpu,
  Globe,
  Link2,
  Loader2,
  Server,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

type EmbeddingForm = {
  tiers: string
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

export function EmbeddingSettings() {
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

  const [form, setForm] = useState<EmbeddingForm>({
    tiers: "gguf,local,remote",
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

  const fetchConfig = async () => {
    try {
      const configRes = await SystemService.getSystemConfig()
      const cfg: Record<string, string> = {}
      if (Array.isArray(configRes)) {
        configRes.forEach((item: any) => {
          cfg[item.key] = item.value
        })
      }
      const state: EmbeddingForm = {
        tiers: cfg.EMBEDDING_TIERS || "gguf,local,remote",
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
  }, [])

  useEffect(() => {
    if (!initial) return
    const dirty = JSON.stringify(form) !== JSON.stringify(initial)
    setComponentDirty("embedding", dirty)
  }, [form, initial, setComponentDirty])

  useEffect(() => {
    registerSaveHandler("embedding", async () => {
      await SystemService.applyEmbeddingTierConfig({
        requestBody: {
          tiers: form.tiers,
          gguf_model: form.ggufModel || null,
          local_url: form.localUrl || null,
          local_api_key: form.localApiKey || null,
          local_model: form.localModel || null,
          provider: form.provider || null,
          base_url: form.baseUrl || null,
          model: form.model || null,
          api_key: form.apiKey || null,
          dimensions: Number(form.dimensions) || null,
        },
      })
    })
    registerResetHandler("embedding", () => {
      if (initial) setForm({ ...initial })
    })
    return () => {
      unregisterSaveHandler("embedding")
    }
  }, [form, initial, registerSaveHandler, unregisterSaveHandler, registerResetHandler])

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await SystemService.testEmbeddingTierConnection({
        requestBody: {
          tiers: form.tiers,
          gguf_model: form.ggufModel || null,
          local_url: form.localUrl || null,
          local_api_key: form.localApiKey || null,
          local_model: form.localModel || null,
          provider: form.provider || null,
          base_url: form.baseUrl || null,
          model: form.model || null,
          api_key: form.apiKey || null,
          dimensions: Number(form.dimensions) || null,
        },
      })
      const ok = res.success ?? false
      setTestResult({
        success: ok,
        msg: ok
          ? t("settings.embedding.connectedWithDim", { dim: res.dimensions || "?" })
          : (res.error || t("settings.embedding.connection_failed")),
      })
    } catch (e: any) {
      setTestResult({
        success: false,
        msg: t("settings.embedding.connection_error", { message: e.message || "" }),
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
      iconClassName="text-purple-500"
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>{t("settings.embedding.tiers")}</Label>
          <Input
            placeholder="gguf,local,remote"
            value={form.tiers}
            onChange={(e) => update("tiers", e.target.value)}
          />
        </div>

        <div className="rounded-md bg-muted/20 p-3 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Cpu className="h-4 w-4 text-amber-500" />
            {t("settings.embedding.tierGguf")}
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.ggufModel")}</Label>
            <Input
              placeholder="/path/to/bge-base-zh-v1.5-q4_k_m.gguf"
              value={form.ggufModel}
              onChange={(e) => update("ggufModel", e.target.value)}
            />
          </div>
        </div>

        <div className="rounded-md bg-muted/20 p-3 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Server className="h-4 w-4 text-blue-500" />
            {t("settings.embedding.tierLocal")}
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.localUrl")}</Label>
            <Input
              placeholder="http://localhost:1234/v1"
              value={form.localUrl}
              onChange={(e) => update("localUrl", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.localApiKey")}</Label>
            <Input
              placeholder="lm-studio"
              value={form.localApiKey}
              onChange={(e) => update("localApiKey", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.localModel")}</Label>
            <Input
              placeholder="text-embedding-nomic-embed-text-v1.5"
              value={form.localModel}
              onChange={(e) => update("localModel", e.target.value)}
            />
          </div>
        </div>

        <div className="rounded-md bg-muted/20 p-3 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Globe className="h-4 w-4 text-green-500" />
            {t("settings.embedding.tierRemote")}
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.provider")}</Label>
            <Input
              placeholder="openai"
              value={form.provider}
              onChange={(e) => update("provider", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.baseUrl")}</Label>
            <Input
              placeholder="https://api.openai.com/v1"
              value={form.baseUrl}
              onChange={(e) => update("baseUrl", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.model")}</Label>
            <Input
              placeholder="text-embedding-3-small"
              value={form.model}
              onChange={(e) => update("model", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.apiKey")}</Label>
            <Input
              placeholder="sk-..."
              value={form.apiKey}
              onChange={(e) => update("apiKey", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.embedding.dimensions")}</Label>
            <Input
              placeholder="1536"
              value={form.dimensions}
              onChange={(e) => update("dimensions", e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-1">
          <Button variant="outline" size="sm" onClick={handleTest} disabled={testing}>
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
            {t("settings.embedding.test_connection")}
          </Button>
          {testResult && (
            <Badge variant={testResult.success ? "secondary" : "destructive"} className="gap-1">
              {testResult.success ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
              {testResult.msg}
            </Badge>
          )}
        </div>
      </div>
    </SettingsCard>
  )
}
