import { useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { useActionRecorder } from "@/hooks/useActionRecorder"
import { useGlobalRecorder } from "@/hooks/useGlobalRecorder"
import { useScreenRecordingPermission } from "@/hooks/useScreenRecordingPermission"
import { handleApiError } from "@/interceptors"
import {
  safeEmit,
  safeGetCurrentWindow,
  safeInvoke,
  safeListen,
} from "@/lib/tauri"
import { useRecordingStore } from "@/stores/recordingStore"

export function GlobalRecorderManager() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const {
    isRecording,
    activeThreadId,
    isDesktopRecording,
    setEventCount,
    setSessionId,
    setVideoPath,
    postRecordingAction,
    stopRecording,
    isPreparing,
    countdown,
    recordingSource,
    recordingSourceSessionId,
    deviceResolution,
    recordingStartTime,
  } = useRecordingStore()

  const busyRef = useRef(false)

  // Sync static translations to tray
  useEffect(() => {
    safeInvoke("sync_tray_translations", {
      showText: t("learning.tray.show"),
      quitText: t("learning.tray.quit"),
    }).catch(() => {})
  }, [i18n.language, t])

  useEffect(() => {
    safeInvoke("sync_tray_recording_state", {
      isRecording,
      startText: t("learning.tray.startRecording"),
      stopText: t("learning.tray.stopRecording"),
    }).catch(() => {})
  }, [isRecording, i18n.language, t])

  // Sync countdown to tray
  useEffect(() => {
    safeInvoke("sync_tray_countdown", {
      isPreparing,
      countdown,
    }).catch(() => {})
  }, [isPreparing, countdown])

  // Listen for tray events
  useEffect(() => {
    console.log("[GlobalRecorderManager] Setting up tray listener")
    let active = true
    let unlistenFn: (() => void) | undefined
    const setup = async () => {
      const fn = await safeListen("tray-record-toggle", () => {
        console.log("[GlobalRecorderManager] Tray toggle received")
        const state = useRecordingStore.getState()
        if (state.isRecording) {
          // Ignore toggle if it happens within 5 seconds of starting (debounce Bartender/Hidden Bar phantom clicks)
          if (
            state.recordingStartTime &&
            Date.now() - state.recordingStartTime < 5000
          ) {
            console.warn(
              "[GlobalRecorderManager] Ignoring tray toggle due to 5-second debounce window.",
            )
            return
          }
          state.setPostRecordingAction("synthesize")
          state.stopRecording()
        } else if (state.isPreparing) {
          // Cancel the countdown if user clicks during preparation
          state.setIsPreparing(false)
          state.setCountdown(0)
          console.log(
            "[GlobalRecorderManager] Recording preparation cancelled from tray",
          )
        } else {
          // Start countdown preparation
          state.initiateRecording("global")
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
  }, [])

  // Listen for watchdog auto-stop (timeout / size limit)
  useEffect(() => {
    let active = true
    let unlistenFn: (() => void) | undefined
    const setup = async () => {
      const fn = await safeListen<string>(
        "recording-auto-stopped",
        (event) => {
          const reason = event.payload
          console.warn(
            "[GlobalRecorderManager] Recording auto-stopped by watchdog:",
            reason,
          )

          const state = useRecordingStore.getState()
          if (!state.isRecording) return

          // Show appropriate toast
          if (reason === "timeout") {
            toast.warning(t("learning.recordingAutoStoppedTimeout"))
          } else if (reason === "size_limit") {
            toast.warning(t("learning.recordingAutoStoppedSize"))
          } else {
            toast.warning(t("learning.recordingAutoStopped"))
          }

          // Trigger the same graceful stop flow as a manual tray stop
          state.setPostRecordingAction("synthesize")
          state.stopRecording()
        },
      )
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

  // We use the hooks here, but control them via the store's state
  const {
    hasPermission: hasVideoPermission,
    requestPermission: requestVideoPermission,
  } = useScreenRecordingPermission()

  // Use delayed persistence - events stay local until user confirms "Synthesize"
  // [FIX] Isolate recording: Disable Mac recorders if source is mobile
  const isDesktopSource = recordingSource === "desktop"

  // [v3 Unified] All recordings now use real-time persistence to backend
  // Events are sent via /global/events and /dom/events APIs
  const domRecorder = useActionRecorder({
    threadId: activeThreadId || "global",
    enabled: isDesktopSource,
    scope: isDesktopRecording ? "both" : "dom",
    autoFlushInterval: 500, // 500ms batch flush
    batchSize: 50,
  })

  const [mirrorBounds, setMirrorBounds] = useState<{
    x: number
    y: number
    width: number
    height: number
  } | null>(null)

  const isMarkingRef = useRef(false)

  useEffect(() => {
    let active = true
    let unlistenStartedFn: (() => void) | undefined
    let unlistenStoppedFn: (() => void) | undefined
    const setup = async () => {
      const fnStarted = await safeListen("marking-started", () => {
        isMarkingRef.current = true
      })
      const fnStopped = await safeListen("marking-stopped", () => {
        isMarkingRef.current = false
      })
      if (!active) {
        fnStarted()
        fnStopped()
      } else {
        unlistenStartedFn = fnStarted
        unlistenStoppedFn = fnStopped
      }
    }
    setup()
    return () => {
      active = false
      if (unlistenStartedFn) unlistenStartedFn()
      if (unlistenStoppedFn) unlistenStoppedFn()
    }
  }, [])

  const globalRecorder = useGlobalRecorder({
    threadId: activeThreadId || "global",
    sessionId: isDesktopSource
      ? domRecorder.sessionId
      : recordingSourceSessionId,
    enabled:
      (isDesktopSource && isDesktopRecording) ||
      (!isDesktopSource && isRecording),
    autoFlushInterval: 500, // 500ms batch flush
    batchSize: 50,
    startTime: recordingStartTime,
    transformEvent: (event) => {
      // [v4] Skip interaction events if we are currently marking a region
      if (isMarkingRef.current) return null

      // [FIX] Deduplication: skip events on the main EvoLoop window to avoid double recording with domRecorder
      if (isDesktopSource && event.window_title === "EvoLoop") {
        return null
      }

      // Coordinate transformation for mobile mirror window
      if (
        !isDesktopSource &&
        recordingSource === "mobile" &&
        mirrorBounds &&
        deviceResolution
      ) {
        if (event.event_type === "mouse_click" && event.position) {
          const [x, y] = event.position
          // Check if inside mirror bounds
          if (
            x >= mirrorBounds.x &&
            x <= mirrorBounds.x + mirrorBounds.width &&
            y >= mirrorBounds.y &&
            y <= mirrorBounds.y + mirrorBounds.height
          ) {
            // Convert to relative (0-1)
            const relX = (x - mirrorBounds.x) / mirrorBounds.width
            const relY = (y - mirrorBounds.y) / mirrorBounds.height

            // Convert to device pixels
            const pixelX = relX * deviceResolution.width
            const pixelY = relY * deviceResolution.height

            console.log(
              `[GlobalRecorderManager] Transformed mirror click: (${x},${y}) -> (${pixelX},${pixelY})`,
            )

            return {
              ...event,
              position: [pixelX, pixelY],
              source: "mobile", // [FIX] Tag as mobile so backend stores with correct source
            }
          }
          // Clicked outside mirror window during mobile recording - skip capture
          return null
        }
      }

      return event
    },
  })

  const recordingStartedRef = useRef(false)
  const pendingStopRef = useRef(false)

  // Sync event count to store and tray
  useEffect(() => {
    // [FIX] Avoid double counting: when in desktop mode, only count global events
    // [v3] For mobile, we also rely on globalRecorder for mirror window clicks
    const totalEvents =
      isDesktopRecording || recordingSource === "mobile"
        ? globalRecorder.eventCount
        : domRecorder.eventCount
    setEventCount(totalEvents)
    // Sync to tray
    safeInvoke("sync_tray_event_count", { count: totalEvents }).catch(() => {})
  }, [
    domRecorder.eventCount,
    globalRecorder.eventCount,
    isDesktopRecording,
    recordingSource,
    setEventCount,
  ])

  // Sync session ID to store (for dialogs)
  useEffect(() => {
    if (isDesktopSource && domRecorder.sessionId) {
      setSessionId(domRecorder.sessionId)
    } else if (!isDesktopSource && recordingSourceSessionId) {
      // [FIX] Sync mobile session ID to global sessionId to trigger synthesis dialog
      setSessionId(recordingSourceSessionId)
    }
  }, [
    domRecorder.sessionId,
    isDesktopSource,
    recordingSourceSessionId,
    setSessionId,
  ])

  // Helper to stop native recorders (extracted to prevent swallowing during busy state)
  const stopRecorders = async () => {
    busyRef.current = true
    recordingStartedRef.current = false
    console.log("[GlobalRecorderManager] Stopping recorders...")
    try {
      let totalEventsCount = 0
      if (isDesktopRecording || recordingSource === "mobile") {
        const res = await globalRecorder.stopRecording()
        if (res) totalEventsCount += res.eventCount
      }
      const domRes = await domRecorder.stopRecording()
      if (domRes) totalEventsCount += domRes.eventCount

      // Stop screen recording - Skip if we are recording mobile specifically
      let vPath: string | null = null
      if (useRecordingStore.getState().recordingSource === "desktop") {
        try {
          vPath = await safeInvoke<string>("stop_screen_recording")
          console.log(
            "[GlobalRecorderManager] Screen recording stopped:",
            vPath,
          )
        } catch (videoErr) {
          console.warn(
            "[GlobalRecorderManager] Screen recording stop failed:",
            videoErr,
          )
        }
      } else {
        console.log(
          "[GlobalRecorderManager] Mobile recording mode - stopping backend mirror session",
        )
        const mobSessionId =
          useRecordingStore.getState().recordingSourceSessionId
        if (mobSessionId) {
          try {
            const res = await LearningService.stopMirrorSession({
              requestBody: { session_id: mobSessionId },
            })
            vPath = res.video_path || null
            // [FIX] Add Android events count from backend to result total
            const androidEventCount = res.event_count || 0
            totalEventsCount += androidEventCount
            console.log(
              "[GlobalRecorderManager] Mobile mirror session stopped, video path:",
              vPath,
              "android events:",
              androidEventCount,
            )
          } catch (mobErr) {
            console.error(
              "[GlobalRecorderManager] Failed to stop mobile mirror session:",
              mobErr,
            )
          }
        }
      }

      // Set the video path in the store so the synthesizer can find it
      if (vPath) {
        setVideoPath(vPath)
      }

      // [v3 Unified] Events are now persisted in real-time via /global/events and /dom/events
      // No need to cache locally - just ensure final flush is complete
      // Final flush happens in stopRecording() of each recorder
      console.log(
        "[GlobalRecorderManager] Recording stopped, events persisted via real-time API",
      )

      if (totalEventsCount === 0) {
        // If video exists but no events, or video is tiny, it's likely a permission issue
        toast.warning(t("learning.noEvents"))
        setSessionId(null)
        setVideoPath(null)
        busyRef.current = false
        return
      }

      // Note: Keyframe extraction now happens after events are persisted in MultimodalSynthesizeDialog
      // We'll trigger it there once user confirms synthesis

      toast.success(
        t("learning.recordingStopped", { count: totalEventsCount }),
      )

      if (useRecordingStore.getState().recordingSource === "mobile") {
        const mobSessionId =
          useRecordingStore.getState().recordingSourceSessionId
        if (mobSessionId) {
          setSessionId(mobSessionId)
        }
      } else {
        if (domRes?.sessionId) setSessionId(domRes.sessionId)
      }

      // If it was triggered from tray, navigate to learning center
      if (postRecordingAction === "synthesize") {
        navigate({ to: "/learning" })
      }

      // [FIX] Show and focus main window when recording stops
      try {
        await safeInvoke("show_main_window")
      } catch (showErr) {
        console.warn(
          "[GlobalRecorderManager] Failed to show/focus main window:",
          showErr,
        )
      }
    } catch (e) {
      console.error("Failed to stop recording", e)
    } finally {
      // Don't clear videoPath immediately - let the UI (MultimodalSynthesizeDialog) use it first
      // It will be cleared on next recording start
      busyRef.current = false
    }
  }

  // Effect to Start/Stop based on store state
  useEffect(() => {
    const manageRecording = async () => {
      const now = performance.now()
      console.log(`[GlobalRecorderManager] manageRecording triggered at ${now}ms`, {
        isRecording,
        isDesktopRecording,
        activeThreadId,
        domRecIsRec: domRecorder.isRecording,
        isDesktopSource,
        busy: busyRef.current,
        pendingStop: pendingStopRef.current,
      })
      // START
      if (isRecording) {
        if (!domRecorder.isRecording && !busyRef.current) {
          busyRef.current = true
          pendingStopRef.current = false
          try {
            // Permission is now handled at the Button level OR as a final safeguard here
            if (hasVideoPermission === false) {
              console.error(
                "[GlobalRecorderManager] Final safeguard: screen recording permission missing",
              )
              // Button should have handled this, but if tray or other trigger hit:
              requestVideoPermission()
              stopRecording()
              busyRef.current = false
              return
            }

            // [FIX] Hide main window BEFORE starting the recording process to prevent it from being captured
            try {
              const win = await safeGetCurrentWindow()
              if (win) {
                await win.hide()
                console.log("[GlobalRecorderManager] Main window hidden successfully before recording start")
              }
            } catch (hideErr) {
              console.warn(
                "[GlobalRecorderManager] Failed to hide main window early:",
                hideErr,
              )
            }

            console.log(
              `[GlobalRecorderManager] Starting recorders... isDesktopSource=${isDesktopSource}`,
            )
            if (isDesktopSource) {
              await domRecorder.startRecording()
            }

            if ((isDesktopRecording && isDesktopSource) || !isDesktopSource) {
              // Fetch mirror bounds for coordinate transformation if recording mobile
              if (!isDesktopSource && recordingSource === "mobile") {
                try {
                  const deviceId =
                    useRecordingStore.getState().recordingSourceDeviceId
                  if (deviceId) {
                    const bounds = await safeInvoke<any>(
                      "get_mirror_window_bounds",
                      { deviceId },
                    )
                    setMirrorBounds(bounds)
                    console.log(
                      "[GlobalRecorderManager] Mirror bounds for transformation:",
                      bounds,
                    )
                  }
                } catch (e) {
                  console.warn(
                    "[GlobalRecorderManager] Failed to fetch mirror bounds:",
                    e,
                  )
                }
              }
              await globalRecorder.startRecording()
            }

            // [FIX] Track that we started recording even if desktop recorders are isolated
            recordingStartedRef.current = true

            // Start screen video recording - Skip if we are recording mobile specifically
            if (useRecordingStore.getState().recordingSource === "desktop") {
              try {
                const path = await safeInvoke<string>("start_screen_recording")
                setVideoPath(path)
                console.log(
                  "[GlobalRecorderManager] Screen recording started:",
                  path,
                )

                // [v3 Unified] Pass session info to standalone desktop marker overlay
                const currentStartTime =
                  useRecordingStore.getState().recordingStartTime
                console.log(
                  "[GlobalRecorderManager] Emitting session to marker overlay:",
                  {
                    sessionId: domRecorder.sessionId,
                    recordingStartTime: currentStartTime,
                    threadId: activeThreadId,
                  },
                )
                await safeEmit("desktop-marker-session", {
                  sessionId: domRecorder.sessionId,
                  recordingStartTime: currentStartTime,
                  threadId: activeThreadId,
                })
              } catch (videoErr) {
                console.error(
                  "[GlobalRecorderManager] Screen recording failed:",
                  videoErr,
                )
                toast.error(
                  t("learning.videoRecordingFailed", { error: videoErr }),
                )
              }
            } else {
              console.log(
                "[GlobalRecorderManager] Mobile recording mode - skipping desktop screen recording",
              )
            }

            toast.info(t("learning.recordingStarted"))
          } catch (e) {
            console.error("Failed to start recording", e)
            // If it's a benefit error (403), the global interceptor already showed a Modal/Toast.
            // We only show the generic "Recording failed" if it's NOT a benefit error.
            if (!handleApiError(e)) {
              toast.error(t("learning.recordingFailed"))
            }
            stopRecording()
          } finally {
            busyRef.current = false
            console.log(`[GlobalRecorderManager] Start finished. pendingStop: ${pendingStopRef.current}`)
            if (pendingStopRef.current) {
              pendingStopRef.current = false
              console.log("[GlobalRecorderManager] Executing queued stop action")
              stopRecorders()
            }
          }
        }
      }
      // STOP
      else {
        // [FIX] Enter stop logic if either domRecorder is active OR we previously started a recording (incl mobile)
        if (domRecorder.isRecording || recordingStartedRef.current) {
          if (busyRef.current) {
            console.warn(`[GlobalRecorderManager] Stop requested during busy state at ${now}ms. Queuing stop.`)
            pendingStopRef.current = true
            return
          }
          await stopRecorders()
        }
      }
    }

    manageRecording()
  }, [
    isRecording,
    isDesktopRecording,
    activeThreadId,
    postRecordingAction,
    navigate,
  ]) // eslint-disable-line

  return null // Headless
}
