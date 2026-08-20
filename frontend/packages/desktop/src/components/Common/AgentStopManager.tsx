import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AgentService } from "@/client/sdk.gen"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"
import { useDutyStore } from "@/stores/dutyStore"
import { useAgentStore } from "@/stores/agentStore"
import { useProjectStore } from "@/stores/projectStore"
import { useChatStore } from "@/stores/chatStore"

/**
 * 全局 Agent 停止管理器（headless，仿 GlobalRecorderManager / CustomerServiceDutyManager）。
 *
 * 统一处理"Esc ×2"停止触发：
 * - Rust 全局快捷键（`agent-stop-requested` 事件）：值守/语音后台运行时，主界面隐藏也能触发。
 * - 窗口内 Esc ×2（键盘监听）：主界面有焦点时触发（作为全局的补充）。
 *
 * 收到触发后：
 * - 调后端 `POST /agent/stop`，带当前上下文（project_id / thread_id）——
 *   只停当前用户的活跃 Agent（member 由后端 token 解析），而非全局全停。
 * - 恢复各端状态：Web 发送状态复位、值守 store 复位、语音（由 useVoiceEvents 处理打断）。
 */
export function AgentStopManager() {
  const { t } = useTranslation()

  // 窗口内 Esc ×2 检测（主界面有焦点时生效）
  useEffect(() => {
    let lastEsc = 0
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return
      const now = Date.now()
      if (now - lastEsc < 500) {
        lastEsc = 0
        triggerStop()
      } else {
        lastEsc = now
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [t])

  const triggerStop = async () => {
    try {
      // 值守模式（globalEnabled）：无参全停（所有会话 + 宏 + 值守）。
      // Web 窗口：带当前上下文（project_id / thread_id），只停当前会话所在项目。
      const isDuty = useDutyStore.getState().globalEnabled
      const project = useProjectStore.getState().currentProject
      const threadId = useChatStore.getState().threadId
      await AgentService.stopAllAgent(
        isDuty
          ? {}
          : {
              projectId: project?.id ?? undefined,
              threadId: threadId ?? undefined,
            },
      )
      // Web：复位状态恢复发送（clearContent 置 status=idle，而非 stopAgent 重复调后端）
      useAgentStore.getState().clearContent()
      // 值守：复位全局 store（后端已 stop_global）
      useDutyStore.getState().setGlobalState(false, false)
      toast.info(t("agentStop.stopped"))
    } catch {
      toast.error(t("agentStop.failed"))
    }
  }

  // 启动 Rust 全局监听 + 监听全局触发事件
  useEffect(() => {
    if (!isTauri()) return
    let active = true
    let unlistenFn: (() => void) | undefined

    const setup = async () => {
      try {
        await safeInvoke("start_agent_stop_listener")
      } catch {
        // 静默（非桌面或无权限）
      }
      const fn = await safeListen("agent-stop-requested", () => {
        triggerStop()
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
      safeInvoke("stop_agent_stop_listener").catch(() => {})
    }
  }, [t])

  return null // Headless
}
