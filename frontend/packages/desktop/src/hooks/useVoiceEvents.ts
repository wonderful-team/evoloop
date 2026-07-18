import { useCallback, useEffect, useRef } from "react"
import { toast } from "sonner"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"
import type { VoiceState } from "@/stores/voiceStore"
import { useVoiceStore } from "@/stores/voiceStore"

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
      await safeListen<{ polished_text: string }>(
        "voice:dictation_polished",
        (event) => {
          setDictationResult(event.payload.polished_text)
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
