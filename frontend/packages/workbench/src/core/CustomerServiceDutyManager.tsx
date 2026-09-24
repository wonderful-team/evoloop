import {useEffect} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {SystemService} from "@/client/sdk.gen"
import {isTauri, safeInvoke, safeListen} from "@/lib/tauri"
import {systemSSEClient} from "@/lib/SystemSSEClient"
import {useDutyStore} from "@/stores/dutyStore"

/**
 * 托盘值守管理器（headless，仿 GlobalRecorderManager）。
 * 监听托盘"自主值守"点击 → 切换全局 enabled（全局总闸，§8.5.4）。
 * 状态唯一来源 = 后端全局 customer_service_duty.enabled。
 */
export function CustomerServiceDutyManager() {
  const { t, i18n } = useTranslation()

  // 同步静态文案到托盘（active 取 store 当前值，避免与状态同步竞争归零）
  useEffect(() => {
    if (!isTauri()) return
    safeInvoke("sync_tray_duty_state", {
      active: useDutyStore.getState().globalEnabled,
      startText: t("settings.duty.title"),
      stopText: t("settings.duty.stopLabel"),
    }).catch(() => {})
  }, [i18n.language, t])

  // 同步当前值守状态到托盘（同时填充全局 store，供懒加载组件读取）。
  // 主推送走 system SSE（duty_state_changed，后端 PUT 时广播）；
  // 60s 轮询仅兜底断线漏事件。托盘 IPC 有 diff 门闩，状态没变不重复发。
  useEffect(() => {
    let active = true
    let lastTray: { active: boolean; lang: string } | null = null
    const sync = async () => {
      try {
        const res = (await SystemService.getCustomerServiceDuty()) as Record<
          string,
          unknown
        >
        if (!active) return
        const enabled = Boolean(res.enabled)
        const wecom = Array.isArray(res.channels)
          ? (res.channels as string[]).includes("wecom")
          : false
        // 填充全局 store（懒加载组件从 store 读，避免 chunk 冲突）
        useDutyStore.getState().setGlobalState(enabled, wecom)
        if (!isTauri()) return
        const next = { active: enabled, lang: i18n.language }
        if (
          !lastTray ||
          lastTray.active !== next.active ||
          lastTray.lang !== next.lang
        ) {
          lastTray = next
          await safeInvoke("sync_tray_duty_state", {
            active: enabled,
            startText: t("settings.duty.title"),
            stopText: t("settings.duty.stopLabel"),
          })
        }
      } catch {
        // 忽略（后端可能未就绪）
      }
    }
    sync()
    const iv = setInterval(sync, 60000)
    const sse = systemSSEClient
    sse.on("duty_state_changed", sync)
    return () => {
      active = false
      clearInterval(iv)
      sse.off("duty_state_changed", sync)
    }
  }, [i18n.language, t])

  // 监听托盘点击
  useEffect(() => {
    if (!isTauri()) return
    let active = true
    let unlistenFn: (() => void) | undefined

    const showHud = async (
      state: "idle" | "processing",
      text: string,
    ) => {
      const { emit } = await import("@tauri-apps/api/event")
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
      const win = await WebviewWindow.getByLabel("voice-hud")
      if (win) await win.show()
      await emit("hud-update", {
        mode: "dialogue" as const,
        state: state as "idle" | "processing",
        text,
      })
    }

    const hideHud = async () => {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
      const win = await WebviewWindow.getByLabel("voice-hud")
      if (win) await win.hide()
    }

    const setup = async () => {
      const fn = await safeListen("tray-duty-toggle", async () => {
        try {
          const res = (await SystemService.getCustomerServiceDuty()) as Record<
            string,
            unknown
          >
          const next = !res.enabled

          // 停止值守：主界面可能已隐藏，用 voice-hud 窗口显示进度反馈
          if (!next) {
            await showHud("processing", t("settings.duty.stopping"))
          } else {
            await showHud("idle", t("settings.duty.started"))
          }

          await SystemService.updateCustomerServiceDuty({
            requestBody: { enabled: next, channels: res.channels ?? [] },
          })

          await safeInvoke("sync_tray_duty_state", {
            active: next,
            startText: t("settings.duty.title"),
            stopText: t("settings.duty.stopLabel"),
          })

          // 停止完成：HUD 显示"已停止"，短暂停留后隐藏
          if (!next) {
            await showHud("idle", t("settings.duty.stopped"))
          }
          setTimeout(() => {
            hideHud()
          }, 2000)
          toast.success(
            next ? t("settings.duty.enabled") : t("settings.duty.disabled"),
          )
        } catch {
          await hideHud()
          toast.error(t("settings.duty.saveError"))
        }
      })
      if (!active) {
        fn()
      } else {
        unlistenFn = fn
      }
    }
    setup()
    return () => {
      active = false
      if (unlistenFn) unlistenFn()
    }
  }, [t])

  return null // Headless
}
