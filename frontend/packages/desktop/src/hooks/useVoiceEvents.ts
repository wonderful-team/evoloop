import { useCallback, useEffect, useRef } from "react"
import { toast } from "sonner"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"
import type { VoiceState } from "@/stores/voiceStore"
import { useVoiceStore } from "@/stores/voiceStore"
import {
  useTauriVoiceShortcut,
  useTauriVoiceShortcutSettings,
} from "./useTauriVoiceShortcut"

let listenersInitialized = false

export function useVoiceEvents() {
  const unlistenersRef = useRef<Array<() => void>>([])

  const setVoiceState = useVoiceStore((s) => s.setVoiceState)
  const setPartialText = useVoiceStore((s) => s.setPartialText)
  const setRouteResult = useVoiceStore((s) => s.setRouteResult)
  const setTtsSentence = useVoiceStore((s) => s.setTtsSentence)
  const appendToken = useVoiceStore((s) => s.appendToken)
  const clearTokenBuffer = useVoiceStore((s) => s.clearTokenBuffer)
  const setDictationResult = useVoiceStore((s) => s.setDictationResult)
  const voiceState = useVoiceStore((s) => s.voiceState)
  const voiceMode = useVoiceStore((s) => s.voiceMode)
  const setVoiceMode = useVoiceStore((s) => s.setVoiceMode)
  const cycleVoiceMode = useVoiceStore((s) => s.cycleVoiceMode)

  const { shortcutEnabled } = useTauriVoiceShortcutSettings()

  // Register global shortcut F12 handler
  useTauriVoiceShortcut({
    enabled: shortcutEnabled,
    onPress: cycleVoiceMode,
  })

  // Register Tray Menu voice toggles
  const voiceModeRef = useRef(voiceMode)
  useEffect(() => {
    voiceModeRef.current = voiceMode
  }, [voiceMode])

  useEffect(() => {
    if (!isTauri()) return

    let unlistenDictation: (() => void) | undefined
    let unlistenDialogue: (() => void) | undefined

    const setupTrayListeners = async () => {
      try {
        unlistenDictation = await safeListen("tray-voice-dictation-toggle", () => {
          const current = voiceModeRef.current
          setVoiceMode(current === "dictation" ? "off" : "dictation")
        })

        unlistenDialogue = await safeListen("tray-voice-dialogue-toggle", () => {
          const current = voiceModeRef.current
          setVoiceMode(current === "dialogue" ? "off" : "dialogue")
        })
      } catch (e) {
        console.error("[voice-events] Tray voice listeners error:", e)
      }
    }

    setupTrayListeners()

    return () => {
      unlistenDictation?.()
      unlistenDialogue?.()
    }
  }, [setVoiceMode])

  // Sync voice session state when voiceMode changes globally
  const prevVoiceModeRef = useRef(voiceMode)
  useEffect(() => {
    const prev = prevVoiceModeRef.current
    prevVoiceModeRef.current = voiceMode

    if (prev === voiceMode) return

    if (prev !== "off") {
      safeInvoke("stop_voice_session").catch(console.error)
    }

    if (voiceMode !== "off") {
      const threadId = crypto.randomUUID()
      safeInvoke("start_voice_session", {
        threadId,
        lang: "zh-CN",
        mode: voiceMode,
        ttsEngine: localStorage.getItem("evoloop_tts_engine") || "edge-tts",
        ttsVoice: localStorage.getItem("evoloop_tts_voice") || undefined,
      }).catch((e) => {
        console.error("[voice] start failed:", e)
        setVoiceMode("off")
        toast.error(String(e))
      })
    }
  }, [voiceMode, setVoiceMode])

  // Show/Hide voice-hud window helpers
  const showHudWindow = useCallback(async () => {
    try {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
      const win = await WebviewWindow.getByLabel("voice-hud")
      if (win) {
        await win.show()
        await win.setAlwaysOnTop(true)
      }
    } catch (e) {
      console.error("[voice-hud] Failed to show HUD window:", e)
    }
  }, [])

  const hideHudWindow = useCallback(async () => {
    try {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
      const win = await WebviewWindow.getByLabel("voice-hud")
      if (win) {
        await win.hide()
      }
    } catch (e) {
      console.error("[voice-hud] Failed to hide HUD window:", e)
    }
  }, [])

  // Sync voice HUD state globally across all pages
  const partialText = useVoiceStore((s) => s.partialText)
  const ttsSentence = useVoiceStore((s) => s.ttsSentence)

  useEffect(() => {
    if (!isTauri()) return

    const updateHud = async () => {
      const { emit } = await import("@tauri-apps/api/event")

      if (voiceMode === "off") {
        await emit("hud-update", { mode: "off", state: "idle", text: "" })
        await hideHudWindow()
        return
      }

      await showHudWindow()

      let displayText = ""
      if (voiceMode === "dictation") {
        displayText = partialText
      } else if (voiceMode === "dialogue") {
        displayText = voiceState === "speaking" ? ttsSentence : partialText
      }

      await emit("hud-update", {
        mode: voiceMode,
        state: voiceState,
        text: displayText,
      })
    }

    updateHud().catch(console.error)
  }, [voiceMode, voiceState, partialText, ttsSentence, showHudWindow, hideHudWindow])

  const initListeners = useCallback(async () => {
    if (!isTauri() || listenersInitialized) return
    listenersInitialized = true

    const unlisteners: Array<() => void> = []

    unlisteners.push(
      await safeListen<{ state: VoiceState }>("voice:state", (event) => {
        setVoiceState(event.payload.state)
        if (event.payload.state === "speaking" || event.payload.state === "idle") {
          clearTokenBuffer()
        }
      }),
    )

    unlisteners.push(
      await safeListen<{ text: string }>("voice:partial", (event) => {
        setPartialText(event.payload.text)
      }),
    )

    unlisteners.push(
      await safeListen<Record<string, unknown>>(
        "voice:route_result",
        (event) => {
          setRouteResult(event.payload)
        },
      ),
    )

    unlisteners.push(
      await safeListen<{ sentence: string }>("voice:tts_boundary", (event) => {
        setTtsSentence(event.payload.sentence)
      }),
    )

    unlisteners.push(
      await safeListen<{ token: string }>("voice:token", (event) => {
        appendToken(event.payload.token)
      }),
    )

    unlisteners.push(
      await safeListen<{ polished_text: string; changes?: any[] }>(
        "voice:dictation_polished",
        (event) => {
          const clarify = event.payload.changes?.[0]?.clarify
          if (clarify) {
            // CLARIFY: don't paste, speak clarification instead
            import("@/hooks/useTTS").then(({ speak }) => {
              speak(clarify)
            })
          } else {
            setDictationResult(event.payload.polished_text)
          }
        },
      ),
    )

    unlisteners.push(
      await safeListen<{ message: string }>("voice:log", (event) => {
        toast.info(event.payload.message, { duration: 3000 })
      }),
    )

    unlistenersRef.current = unlisteners
  }, [setVoiceState, setPartialText, setRouteResult, setTtsSentence, appendToken, clearTokenBuffer, setDictationResult])

  // Sync tray icon with voice state
  useEffect(() => {
    if (!isTauri()) return
    safeInvoke("sync_tray_voice_state", {
      mode: voiceState === "idle" ? "off" : voiceState,
      voiceState,
    }).catch(() => {})
  }, [voiceState])

  const startVoiceSession = useCallback(async (threadId: string, lang = "zh-CN") => {
    try {
      await safeInvoke<void>("start_voice_session", {
        threadId,
        lang,
        mode: "dialogue",
        ttsEngine: localStorage.getItem("evoloop_tts_engine") || "edge-tts",
        ttsVoice: localStorage.getItem("evoloop_tts_voice") || undefined,
      })
    } catch (e) {
      console.error("[voice-events] start session failed:", e)
      throw e
    }
  }, [])

  const stopVoiceSession = useCallback(async () => {
    try {
      await safeInvoke("stop_voice_session")
    } catch (e) {
      console.error("[voice-events] stop session failed:", e)
    }
  }, [])

  const triggerBargeIn = useCallback(async () => {
    try {
      await safeInvoke("trigger_voice_barge_in")
    } catch (e) {
      console.error("[voice-events] barge-in failed:", e)
    }
  }, [])

  useEffect(() => {
    initListeners()
    return () => {
      for (const unlisten of unlistenersRef.current) {
        unlisten()
      }
      listenersInitialized = false
    }
  }, [initListeners])

  return {
    startVoiceSession,
    stopVoiceSession,
    triggerBargeIn,
  }
}
