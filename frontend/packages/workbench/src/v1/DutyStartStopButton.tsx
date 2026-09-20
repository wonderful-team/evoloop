import { useCallback, useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Loader2, Play, Square } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@evoloop/shared/components/ui/button"
import { SystemService } from "@/client"
import { DEMO } from "./demoData"
import {
  getDemoRunning,
  setDemoRunning,
} from "./demoRuntime"

/**
 * Floating duty start/stop button (bottom-right FAB).
 * Toggles the global customer_service_duty.enabled gate — same switch
 * as the settings page, surfaced as a floating action for the operator.
 */
export function DutyStartStopButton({
  onRitual,
  variant = "floating",
}: {
  onRitual?: (phase: "start" | "stop" | "done") => void
  variant?: "floating" | "inline"
} = {}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [channels, setChannels] = useState<string[]>([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const sync = useCallback(async () => {
    if (DEMO) {
      setEnabled(getDemoRunning())
      return
    }
    try {
      const res = (await SystemService.getCustomerServiceDuty()) as Record<
        string,
        unknown
      >
      setEnabled(Boolean(res.enabled))
      setChannels(Array.isArray(res.channels) ? (res.channels as string[]) : [])
    } catch {
      setEnabled(false)
    }
  }, [])

  useEffect(() => {
    sync()
  }, [sync])

  async function toggle() {
    if (enabled === null) return
    const next = !enabled
    setBusy(true)
    setError("")
    onRitual?.(next ? "start" : "stop")
    try {
      if (DEMO) {
        setDemoRunning(next)
        setEnabled(next)
        await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
        await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
        setTimeout(() => onRitual?.("done"), next ? 1500 : 900)
        return
      }
      await SystemService.updateCustomerServiceDuty({
        requestBody: { enabled: next, channels },
      })
      setEnabled(next)
      setTimeout(() => onRitual?.("done"), next ? 1500 : 900)
      await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (variant === "inline") {
    return (
      <Button
        size="sm"
        variant={enabled ? "destructive" : "default"}
        className={`h-7 px-3 gap-1.5 text-xs rounded-md shadow-2xs font-medium cursor-pointer transition-all ${
          enabled ? "animate-pulse" : ""
        }`}
        disabled={busy}
        title={
          enabled
            ? t("dutyBoard.switch.stop", "暂停自主值守")
            : t("dutyBoard.switch.start", "开启自主值守")
        }
        onClick={toggle}
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : enabled ? (
          <Square className="h-3.5 w-3.5 fill-current" />
        ) : (
          <Play className="h-3.5 w-3.5 fill-current ml-0.5" />
        )}
        <span>{enabled ? "暂停值守" : "开启值守"}</span>
      </Button>
    )
  }

  return (
    <div className="absolute bottom-[62px] right-5 z-40 flex flex-col items-end gap-2">
      {error && (
        <div className="rounded-md bg-background px-3 py-1.5 text-xs text-red-600 shadow-lg">
          {error}
        </div>
      )}
      <Button
        size="lg"
        variant={enabled ? "destructive" : "default"}
        className={`h-12 w-12 rounded-full shadow-lg hover:shadow-xl transition-shadow cursor-pointer ${enabled ? "animate-pulse" : ""}`}
        disabled={busy}
        title={
          enabled
            ? t("dutyBoard.switch.stop", "暂停自主值守")
            : t("dutyBoard.switch.start", "开启自主值守")
        }
        onClick={toggle}
      >
        {busy ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : enabled ? (
          <Square className="h-5 w-5" />
        ) : (
          <Play className="h-5 w-5 ml-0.5" />
        )}
      </Button>
    </div>
  )
}


/** Full-screen boot/halt ritual overlay for the duty workbench. */
export function DutyRitualOverlay({ phase }: { phase: "start" | "stop" }) {
  const starting = phase === "start"
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative flex flex-col items-center gap-5">
        {/* pulsing rings — both rituals get the ring cascade */}
        <div className="relative h-24 w-24 flex items-center justify-center">
          <span
            className="absolute inset-0 rounded-full border-2 border-primary/60"
            style={{ animation: "dutyRing 1.2s ease-out infinite" }}
          />
          <span
            className="absolute inset-0 rounded-full border border-primary/40"
            style={{
              animation: "dutyRing 1.2s ease-out 0.4s infinite",
            }}
          />
          <span
            className={`h-8 w-8 rounded-full ${
              starting ? "bg-primary animate-pulse" : "bg-muted-foreground/60"
            }`}
          />
        </div>
        <div className="text-center space-y-1.5">
          <div className="text-sm font-bold tracking-[0.3em] text-foreground">
            {starting ? "值守启动中" : "值守已停止"}
          </div>
          <div className="text-[11px] text-muted-foreground tracking-wider">
            {starting ? "唤醒 Agent · 建立执行会话" : "现场已冻结 · 任务保持待命"}
          </div>
        </div>
      </div>
      <style>{`
        @keyframes dutyRing {
          0% { transform: scale(0.6); opacity: 0.9; }
          100% { transform: scale(1.6); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
