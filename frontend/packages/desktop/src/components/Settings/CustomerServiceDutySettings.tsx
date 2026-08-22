import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Switch } from "@evoloop/shared/components/ui/switch"
import { Input } from "@evoloop/shared/components/ui/input"
import { Headset, Loader2, Play, Square } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"

interface GlobalDutyConfig {
  enabled: boolean
  channels: string[]
  poll_interval?: number
}

/**
 * 全局客服值守配置（GeneralSettings 底部）。
 * 总开关 = 播放/停止主按钮（开启值守 / 停止值守）。
 * 渠道选择为开启前置配置。MCP 不在前端配置（系统启动时已连接）。
 */
export default function CustomerServiceDutySettings() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [config, setConfig] = useState<GlobalDutyConfig>({
    enabled: false,
    channels: [],
    poll_interval: 60,
  })

  const fetchConfig = useCallback(async () => {
    setLoading(true)
    try {
      const res = (await SystemService.getCustomerServiceDuty()) as Record<
        string,
        unknown
      >
      setConfig({
        enabled: Boolean(res.enabled),
        channels: Array.isArray(res.channels) ? (res.channels as string[]) : [],
        poll_interval:
          typeof res.poll_interval === "number" ? res.poll_interval : 60,
      })
    } catch {
      toast.error(t("settings.duty.loadError"))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchConfig()
  }, [fetchConfig])

  const handleSave = async (next: GlobalDutyConfig) => {
    setSaving(true)
    try {
      // 仅"启用企微渠道"（wecom 从无到有）时校验企业微信就绪；
      // 开启值守 / 项目参与不做 GUI 检测（依赖渠道已启用）
      const enablingWecom =
        next.channels.includes("wecom") && !config.channels.includes("wecom")
      if (enablingWecom) {
        const v = (await SystemService.validateCustomerServiceDuty()) as Record<
          string,
          unknown
        >
        if (!v.ok) {
          const reasons = Array.isArray(v.errors) ? (v.errors as string[]) : []
          toast.error(
            reasons.join("\n") || t("settings.duty.validationFailed"),
          )
          return
        }
      }
      await SystemService.updateCustomerServiceDuty({
        requestBody: {
          enabled: next.enabled,
          channels: next.channels,
          poll_interval: next.poll_interval,
        },
      })
      setConfig(next)
      // 仅提示启停变化；纯渠道变更不打扰
      if (next.enabled !== config.enabled) {
        toast.success(
          next.enabled
            ? t("settings.duty.enabled")
            : t("settings.duty.disabled"),
        )
      } else {
        toast.success(t("settings.duty.saved"))
      }
    } catch {
      toast.error(t("settings.duty.saveError"))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Headset className="h-4 w-4 text-muted-foreground" />
          {t("settings.duty.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 播放/停止主按钮（主操作） */}
        <div className="flex items-center gap-3">
          {config.enabled ? (
              <Button
                  variant="destructive"
                  size="lg"
                  disabled={saving}
                  onClick={() => handleSave({ ...config, enabled: false })}
              >
                {saving ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                    <Square className="h-5 w-5" />
                )}
                {t("settings.duty.stopDuty")}
              </Button>
          ) : (
              <Button
                  size="lg"
                  className="gap-2"
                  disabled={saving || config.channels.length === 0}
                  onClick={() => handleSave({ ...config, enabled: true })}
              >
                {saving ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                    <Play className="h-5 w-5" />
                )}
                {t("settings.duty.startDuty")}
              </Button>
          )}
          <p className="text-xs text-muted-foreground">
            {config.enabled
                ? t("settings.duty.runningDesc")
                : t("settings.duty.stoppedDesc")}
          </p>
        </div>

        {/* 渠道选择（配置项） */}
        <div className="border-t pt-4">
          <span className="text-sm font-medium">
            {t("settings.duty.channelsLabel")}
          </span>
          <div className="mt-2 space-y-2">
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">企业微信</p>
                <p className="text-xs text-muted-foreground">
                  {t("settings.duty.wecomDesc")}
                </p>
              </div>
              <Switch
                checked={config.channels.includes("wecom")}
                onCheckedChange={(v) => {
                  const next = v
                    ? [...config.channels, "wecom"]
                    : config.channels.filter((c) => c !== "wecom")
                  handleSave({ ...config, channels: next })
                }}
                disabled={saving}
              />
            </div>
          </div>
        </div>

        {/* 轮巡兜底间隔（秒）：推送失效时按此频率轮巡，缺省 60 */}
        <div className="border-t pt-4">
          <span className="text-sm font-medium">
            {t("settings.duty.pollIntervalLabel")}
          </span>
          <div className="mt-2 flex items-center gap-3">
            <Input
              type="number"
              min={60}
              max={3600}
              step={60}
              value={config.poll_interval ?? 60}
              onChange={(e) => {
                const n = Number(e.target.value)
                if (Number.isInteger(n) && n >= 60 && n <= 3600) {
                  handleSave({ ...config, poll_interval: n })
                }
              }}
              className="h-9 max-w-[160px]"
              disabled={saving}
            />
            <p className="text-xs text-muted-foreground">
              {t("settings.duty.pollIntervalHint")}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
