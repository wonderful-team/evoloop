import { useCallback, useEffect, useRef } from "react"
import { toast } from "sonner"
import { useNavigate } from "@tanstack/react-router"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"
import type { VoiceState } from "@/stores/voiceStore"
import { useVoiceStore } from "@/stores/voiceStore"

let listenersInitialized = false

export function useVoiceEvents() {
  const unlistenersRef = useRef<Array<() => void>>([])
  const navigate = useNavigate()

  const setVoiceState = useVoiceStore((s) => s.setVoiceState)
  const setPartialText = useVoiceStore((s) => s.setPartialText)
  const setTtsSentence = useVoiceStore((s) => s.setTtsSentence)
  const appendToken = useVoiceStore((s) => s.appendToken)
  const clearTokenBuffer = useVoiceStore((s) => s.clearTokenBuffer)
  const voiceState = useVoiceStore((s) => s.voiceState)
  const voiceMode = useVoiceStore((s) => s.voiceMode)
  const setVoiceMode = useVoiceStore((s) => s.setVoiceMode)

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
        unlistenDictation = await safeListen(
          "tray-voice-dictation-toggle",
          () => {
            const current = voiceModeRef.current
            setVoiceMode(current === "dictation" ? "off" : "dictation")
          },
        )

        unlistenDialogue = await safeListen(
          "tray-voice-dialogue-toggle",
          () => {
            const current = voiceModeRef.current
            setVoiceMode(current === "dialogue" ? "off" : "dialogue")
          },
        )
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

    if (prev !== "off" && voiceMode !== "off") {
      // Switching between modes — no stop/start, just tell Rust to swap mode
      safeInvoke("switch_voice_mode", { mode: voiceMode }).catch((e) => {
        console.error("[voice] switch_mode failed:", e)
        setVoiceMode("off")
        toast.error("语音模式切换失败")
      })
    } else {
      if (prev !== "off") {
        safeInvoke("stop_voice_session").catch(console.error)
      }
      if (voiceMode !== "off") {
        // Wake word detector must be stopped before voice session (mic conflict)
        safeInvoke("stop_wake_word_listener").catch(() => {})
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
          const errMsg = String(e)
          if (errMsg.includes("麦克风") || errMsg.includes("input device") || errMsg.includes("input config") || errMsg.includes("mic")) {
            toast.error("麦克风不可用，请检查蓝牙耳机或麦克风是否已连接")
          } else {
            toast.error(errMsg)
          }
        })
      }
    }
  }, [voiceMode, setVoiceMode])

  // Show/Hide voice-hud window helpers
  const showHudWindow = useCallback(async () => {
    try {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
      const win = await WebviewWindow.getByLabel("voice-hud")
      if (win) {
        await win.show()
      }
      // Return focus to main window so that Cmd+V (dictation paste) targets the right input
      const mainWin = await WebviewWindow.getByLabel("main")
      await mainWin?.setFocus()
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

  // Show/Hide HUD window when voiceMode toggles (not on every state update)
  const prevShowRef = useRef(voiceMode !== "off")
  useEffect(() => {
    if (!isTauri()) return

    const isActive = voiceMode !== "off"
    if (isActive === prevShowRef.current) return
    prevShowRef.current = isActive

    if (isActive) {
      showHudWindow()
    } else {
      hideHudWindow()
    }
  }, [voiceMode, showHudWindow, hideHudWindow])

  // Sync voice HUD content (state/text) without showing/hiding the window
  const partialText = useVoiceStore((s) => s.partialText)
  const ttsSentence = useVoiceStore((s) => s.ttsSentence)

  useEffect(() => {
    if (!isTauri() || voiceMode === "off") return

    const updateHud = async () => {
      const { emit } = await import("@tauri-apps/api/event")

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
  }, [
    voiceMode,
    voiceState,
    partialText,
    ttsSentence,
  ])

  const initListeners = useCallback(async () => {
    if (!isTauri() || listenersInitialized) return
    listenersInitialized = true

    const unlisteners: Array<() => void> = []

    unlisteners.push(
      await safeListen<{ state: VoiceState }>("voice:state", (event) => {
        setVoiceState(event.payload.state)
        if (
          event.payload.state === "speaking" ||
          event.payload.state === "idle"
        ) {
          clearTokenBuffer()
        }
      }),
    )

    unlisteners.push(
      await safeListen<{ message: string; code?: string }>("voice:error", (event) => {
        console.error("[voice] voice:error event:", event.payload)
        toast.error(event.payload.message)
      }),
    )

    unlisteners.push(
      await safeListen<{ text: string }>("voice:partial", (event) => {
        setPartialText(event.payload.text)
      }),
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

    // Frontend navigation from voice commands — window show/hide and HUD feedback
    // are handled by Rust and the HUD window respectively.
    unlisteners.push(
      await safeListen<{ route: string; feedback?: string }>(
        "voice:navigate",
        async (event) => {
          const route = event.payload.route
          if (!route) return

          if (route === "__SWITCH_PROJECT__") {
            const { useProjectStore } = await import("../stores/projectStore")
            useProjectStore.getState().openProjectSwitcher()
            return
          }

          if (route === "__HIDE_WINDOW__") {
            // Rust hides the main window; HUD shows the feedback.
            return
          }

          navigate({ to: route })
          // 技能录制：导航到学习中心后切换录制状态
          if (route.includes("tab=macros")) {
            const { useRecordingStore } = await import("../stores/recordingStore")
            const state = useRecordingStore.getState()
            if (state.isRecording || state.isPreparing) {
              state.setPostRecordingAction("synthesize")
              state.stopRecording()
            } else {
              state.initiateRecording("global")
            }
          }
        },
      ),
    )

    unlisteners.push(
      await safeListen<{ changes?: Array<{ clarify?: string }> }>(
        "voice:dictation_polished",
        async (event) => {
          const clarify = event.payload.changes?.[0]?.clarify
          if (clarify) {
            safeInvoke("speak", { text: clarify }).catch(console.error)
          } else {
            // Rust side already pastes via dictation_paste() to the active window.
            // Update HUD to show "已粘贴" then return to listening after 1.5s.
            const { emit } = await import("@tauri-apps/api/event")
            await emit("hud-update", {
              mode: "dictation",
              state: "idle" as const,
              text: "pasted",
            })
            setTimeout(() => {
              if (voiceModeRef.current === "dictation") {
                emit("hud-update", {
                  mode: "dictation",
                  state: "listening" as const,
                  text: "",
                }).catch(console.error)
              }
            }, 1500)
          }
        },
      ),
    )

    unlisteners.push(
      await safeListen<Record<string, string>>(
        "system:config_snapshot",
        (event) => {
          const configs = event.payload || {}
          console.log(
            "[system-sync] Config snapshot received from backend:",
            Object.keys(configs).length,
            "keys",
          )
          if (configs.TTS_ENGINE) {
            localStorage.setItem("evoloop_tts_engine", configs.TTS_ENGINE)
            safeInvoke("set_tts_engine", { engine: configs.TTS_ENGINE }).catch(
              console.error,
            )
          }
          if (configs.TTS_VOICE) {
            localStorage.setItem("evoloop_tts_voice", configs.TTS_VOICE)
            safeInvoke("set_tts_voice", { voice: configs.TTS_VOICE }).catch(
              console.error,
            )
          }
          if (configs.TTS_SPEED) {
            localStorage.setItem("evoloop_tts_speed", configs.TTS_SPEED)
            safeInvoke("set_tts_speed", {
              speed: parseFloat(configs.TTS_SPEED) || 1.0,
            }).catch(console.error)
          }
          if (configs.QWEN_TTS_API_KEY)
            localStorage.setItem(
              "evoloop_qwen_tts_key",
              configs.QWEN_TTS_API_KEY,
            )
          if (configs.EVOCLOUD_DEVICE_NAME)
            localStorage.setItem(
              "evoloop_device_name",
              configs.EVOCLOUD_DEVICE_NAME,
            )
        },
      ),
    )

    // Shared state snapshot: project_id, thread_id, TTS config etc.
    unlisteners.push(
      await safeListen<Record<string, string>>(
        "system:state_snapshot",
        (event) => {
          const state = event.payload || {}
          console.log(
            "[shared-state] Snapshot received:",
            Object.keys(state).length,
            "keys",
          )
          // Write TTS config keys from state snapshot too (backward compat)
          if (state.TTS_ENGINE) {
            localStorage.setItem("evoloop_tts_engine", state.TTS_ENGINE)
            safeInvoke("set_tts_engine", { engine: state.TTS_ENGINE }).catch(
              console.error,
            )
          }
          if (state.TTS_VOICE) {
            localStorage.setItem("evoloop_tts_voice", state.TTS_VOICE)
            safeInvoke("set_tts_voice", { voice: state.TTS_VOICE }).catch(
              console.error,
            )
          }
          if (state.TTS_SPEED) {
            localStorage.setItem("evoloop_tts_speed", state.TTS_SPEED)
            safeInvoke("set_tts_speed", {
              speed: parseFloat(state.TTS_SPEED) || 1.0,
            }).catch(console.error)
          }
          if (state.QWEN_TTS_API_KEY)
            localStorage.setItem("evoloop_qwen_tts_key", state.QWEN_TTS_API_KEY)
        },
      ),
    )

    unlisteners.push(
      await safeListen<{ key: string; old_value: string; new_value: string }>(
        "system:config_changed",
        (event) => {
          const { key, new_value } = event.payload || {}
          console.log(
            "[system-sync] Real-time config change pushed:",
            key,
            "->",
            new_value,
          )
          if (key === "TTS_ENGINE") {
            localStorage.setItem("evoloop_tts_engine", new_value)
            safeInvoke("set_tts_engine", { engine: new_value }).catch(
              console.error,
            )
          } else if (key === "TTS_VOICE") {
            localStorage.setItem("evoloop_tts_voice", new_value)
            safeInvoke("set_tts_voice", { voice: new_value }).catch(
              console.error,
            )
          } else if (key === "TTS_SPEED") {
            localStorage.setItem("evoloop_tts_speed", new_value)
            safeInvoke("set_tts_speed", {
              speed: parseFloat(new_value) || 1.0,
            }).catch(console.error)
          } else if (key === "EVOCLOUD_DEVICE_NAME") {
            localStorage.setItem("evoloop_device_name", new_value)
          }
        },
      ),
    )

    unlistenersRef.current = unlisteners
  }, [
    setVoiceState,
    setPartialText,
    setTtsSentence,
    appendToken,
    clearTokenBuffer,
  ])

  // Sync tray icon with voice state
  useEffect(() => {
    if (!isTauri()) return
    safeInvoke("sync_tray_voice_state", {
      mode: voiceState === "idle" ? "off" : voiceState,
      voiceState,
      modelsReady: null, // set by ModelManager when model status loaded
    }).catch(() => {})
  }, [voiceState])

  const startVoiceSession = useCallback(
    async (threadId: string, lang = "zh-CN") => {
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
    },
    [],
  )

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
