import i18n from "@evoloop/shared/i18n"
import {createFileRoute} from "@tanstack/react-router"
import {invoke} from "@tauri-apps/api/core"
import {emit, listen, type UnlistenFn} from "@tauri-apps/api/event"
import {getCurrentWindow, LogicalPosition, LogicalSize,} from "@tauri-apps/api/window"
import {useCallback, useEffect, useRef, useState} from "react"
import {useTranslation} from "react-i18next"
import {LearningService} from "@/client/sdk.gen"
import {isTauri} from "@/lib/tauri"
import {type ExtractRegion, MarkerSelectionView,} from "@/components/Overlay/MarkerSelectionView"

export const Route = createFileRoute("/android-marker-overlay")({
  component: () => {
    if (!isTauri()) {
      return (
        <div className="flex items-center justify-center h-screen text-muted-foreground">
          {i18n.t("overlay.androidOnly")}
        </div>
      )
    }
    return <AndroidMarkerOverlay />
  },
})

interface WindowBounds {
  x: number
  y: number
  width: number
  height: number
}

function AndroidMarkerOverlay() {
  const { t } = useTranslation()
  const [isExtractMode, setIsExtractMode] = useState(false)
  const [isSelecting, setIsSelecting] = useState(false)
  const [extractRegions, setExtractRegions] = useState<ExtractRegion[]>([])
  const hasDragged = useRef(false)
  const preExtractPosition = useRef<{ x: number; y: number } | null>(null)

  // Selection state
  const [selectionStart, setSelectionStart] = useState({ x: 0, y: 0 })
  const [selectionEnd, setSelectionEnd] = useState({ x: 0, y: 0 })
  const [currentMousePos, setCurrentMousePos] = useState({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  // Mirror window bounds (scrcpy window)
  const [mirrorBounds, setMirrorBounds] = useState<WindowBounds | null>(null)

  // Listen for session info from main window
  const sessionIdRef = useRef<string | null>(null)
  const recordingStartTimeRef = useRef<number | null>(null)
  const threadIdRef = useRef<string | null>(null)
  const deviceIdRef = useRef<string | null>(null)

  useEffect(() => {
    // Ensure the HTML body is transparent so the window transparency works
    document.body.style.background = "transparent"
    document.body.style.overflow = "hidden"
    document.documentElement.style.overflow = "hidden"

    // Move overlay to the top-right corner by default
    const initPosition = async () => {
      try {
        const { currentMonitor } = await import("@tauri-apps/api/window")
        const monitor = await currentMonitor()
        if (monitor) {
          const win = getCurrentWindow()
          const x = monitor.size.width / monitor.scaleFactor - 100
          await win.setPosition(new LogicalPosition(x, 50))
          await win.show()
        }
      } catch (e) {
        console.log("[AndroidMarkerOverlay] Failed to set initial position", e)
      }
    }
    initPosition()
  }, [])

  // [Scheme C] Setup listener for session info from main window
  useEffect(() => {
    let unlisten: UnlistenFn | undefined

    const setupListener = async () => {
      unlisten = await listen<{
        sessionId: string
        recordingStartTime: number | null
        threadId: string | null
        deviceId?: string | null
      }>("android-marker-session", (event) => {
        sessionIdRef.current = event.payload.sessionId
        recordingStartTimeRef.current = event.payload.recordingStartTime
        threadIdRef.current = event.payload.threadId
        deviceIdRef.current = event.payload.deviceId || null
        console.log(
          "[AndroidMarkerOverlay] Session info received:",
          event.payload,
        )
      })

      // [FIX] Emit ready event to notify main window that we're listening
      // This handles the race condition where main window emits before we're ready
      await emit("android-marker-ready", {})
      console.log("[AndroidMarkerOverlay] Emitted ready event")
    }

    setupListener()

    return () => {
      if (unlisten) unlisten()
    }
  }, [])

  // Track mouse position for crosshair - relative to the (already resized) window
  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isExtractMode) return

      // Mouse coordinates are already relative to the window (which matches scrcpy bounds)
      const x = e.clientX
      const y = e.clientY

      setCurrentMousePos({ x, y })
      if (isSelecting) {
        setSelectionEnd({ x, y })
      }
    },
    [isSelecting, isExtractMode],
  )

  // Handle window dragging or selection
  const handleMouseDown = useCallback(
    async (e: React.MouseEvent) => {
      if (isExtractMode) {
        e.preventDefault()
        e.stopPropagation()
        setIsSelecting(true)
        // Coordinates are screen-relative because we are full-screen (0,0)
        setSelectionStart({ x: e.clientX, y: e.clientY })
        setSelectionEnd({ x: e.clientX, y: e.clientY })
        return
      }

      // Use Tauri's native dragging for smooth, jitter-free OS-level window movement
      try {
        const win = getCurrentWindow()
        await win.startDragging()
      } catch (err) {
        console.log("[AndroidMarkerOverlay] Failed to start dragging:", err)
      }
    },
    [isExtractMode, mirrorBounds],
  )

  const handleMouseUp = useCallback(async () => {
    if (isSelecting) {
      setIsSelecting(false)

      // Use mirror bounds for coordinate calculation if available
      const bounds = mirrorBounds
      if (!bounds) {
        console.error("[AndroidMarkerOverlay] No mirror bounds available")
        return
      }

      // Coordinates are already screen-relative since we are full-screen
      const x1 = Math.min(selectionStart.x, selectionEnd.x)
      const y1 = Math.min(selectionStart.y, selectionEnd.y)
      const x2 = Math.max(selectionStart.x, selectionEnd.x)
      const y2 = Math.max(selectionStart.y, selectionEnd.y)

      // Clamp to mirror bounds specifically
      const clampedX1 = Math.max(bounds.x, x1)
      const clampedY1 = Math.max(bounds.y, y1)
      const clampedX2 = Math.min(bounds.x + bounds.width, x2)
      const clampedY2 = Math.min(bounds.y + bounds.height, y2)

      const isPointClick =
        clampedX2 - clampedX1 < 10 || clampedY2 - clampedY1 < 10
      const startTime = recordingStartTimeRef.current
      const relativeTimestamp = startTime ? Date.now() - startTime : 0

      // Calculate relative coordinates (0-1 range) within the mirror window
      const region: ExtractRegion = {
        id: `extract_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: relativeTimestamp,
        x: (clampedX1 - bounds.x) / bounds.width,
        y: (clampedY1 - bounds.y) / bounds.height,
        width: isPointClick ? 0.02 : (clampedX2 - clampedX1) / bounds.width,
        height: isPointClick ? 0.02 : (clampedY2 - clampedY1) / bounds.height,
      }

      setExtractRegions((prev) => [...prev, region])
      await saveRegionToBackend(region)

      setIsExtractMode(false)
      setMirrorBounds(null) // Clear bounds when exiting
      // Notify main window to resume recording interaction events
      await emit("marking-stopped", {})
      try {
        const win = getCurrentWindow()
        await win.setSize(new LogicalSize(64, 64))
        if (preExtractPosition.current) {
          await win.setPosition(
            new LogicalPosition(
              preExtractPosition.current.x,
              preExtractPosition.current.y,
            ),
          )
        }
      } catch (e) {
        console.log("[AndroidMarkerOverlay] Failed to resize window:", e)
      }

      return
    }
  }, [isSelecting, selectionStart, selectionEnd, mirrorBounds])

  const saveRegionToBackend = async (region: ExtractRegion) => {
    const sessionId = sessionIdRef.current
    const threadId = threadIdRef.current

    if (!sessionId || !threadId) {
      console.error(
        "[AndroidMarkerOverlay] No session ID or thread ID available",
      )
      return
    }

    try {
      // [Scheme C] Coordinates are now relative to the mirror window (0-1 range)
      await LearningService.persistDomEvents({
        requestBody: {
          session_id: sessionId,
          thread_id: threadId,
          events: [
            {
              timestamp: region.timestamp,
              event_type: "region_extract",
              selector: `android://screen/${region.x.toFixed(4)}/${region.y.toFixed(4)}`,
              target_text: "Android region extraction",
              coordinates: {
                x: region.x,
                y: region.y,
                width: region.width,
                height: region.height,
              },
            },
          ],
        },
      })

      await emit("android-region-marked", { region })
      console.log(
        "[AndroidMarkerOverlay] Region extract event saved to TraceEvent:",
        region,
      )
    } catch (error) {
      console.error(
        "[AndroidMarkerOverlay] Failed to save region extract event:",
        error,
      )
    }
  }

  useEffect(() => {
    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("mouseup", handleMouseUp)
    return () => {
      window.removeEventListener("mousemove", handleMouseMove)
      window.removeEventListener("mouseup", handleMouseUp)
    }
  }, [handleMouseMove, handleMouseUp])

  const handleClick = useCallback(async () => {
    if (hasDragged.current) {
      hasDragged.current = false
      return
    }

    if (isExtractMode) {
      setIsExtractMode(false)
      setMirrorBounds(null)
      // Notify main window to resume recording interaction events
      await emit("marking-stopped", {})
      try {
        const win = getCurrentWindow()
        await win.setSize(new LogicalSize(64, 64))
        if (preExtractPosition.current) {
          await win.setPosition(
            new LogicalPosition(
              preExtractPosition.current.x,
              preExtractPosition.current.y,
            ),
          )
        }
      } catch (e) {
        console.log("[AndroidMarkerOverlay] Failed to resize window:", e)
      }
      return
    }

    // [Scheme C] Get mirror window bounds before expanding
    const deviceId = deviceIdRef.current
    console.log("[AndroidMarkerOverlay] Device ID from ref:", deviceId)

    if (!deviceId) {
      console.error("[AndroidMarkerOverlay] No device ID available")
      alert(
        t(
          "overlay.errorDeviceInfo",
          "Unable to get device info, please restart recording",
        ),
      )
      return
    }

    try {
      // [Scheme C] Get the scrcpy window bounds for active area detection
      const bounds: WindowBounds = await invoke("get_mirror_window_bounds", {
        deviceId,
      })
      console.log("[AndroidMarkerOverlay] Got mirror window bounds:", bounds)
      setMirrorBounds(bounds)

      const win = getCurrentWindow()
      const pos = await win.outerPosition()
      preExtractPosition.current = { x: pos.x, y: pos.y }

      // Expand to full screen (more reliable on macOS for stacking/rendering)
      await win.setSize(
        new LogicalSize(window.screen.width, window.screen.height),
      )
      await win.setPosition(new LogicalPosition(0, 0))
      await win.setAlwaysOnTop(true)
      await win.setIgnoreCursorEvents(false)

      // [FIX] Bring window to front
      await win.setFocus()

      // Notify main window to stop recording interaction events
      await emit("marking-started", {})

      setIsExtractMode(true)
    } catch (e) {
      console.error("[AndroidMarkerOverlay] Failed to expand window:", e)
      alert(
        t(
          "overlay.errorMirrorWindow",
          "Unable to detect mirror window or insufficient permissions. Please ensure the scrcpy window is open and restart the app.",
        ),
      )
    }
  }, [isExtractMode])

  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (e.key === "Escape" && isExtractMode) {
        setIsExtractMode(false)
        setIsSelecting(false)
        setMirrorBounds(null)
        // Notify main window to resume recording interaction events
        await emit("marking-stopped", {})
        try {
          const win = getCurrentWindow()
          await win.setSize(new LogicalSize(64, 64))
          if (preExtractPosition.current) {
            await win.setPosition(
              new LogicalPosition(
                preExtractPosition.current.x,
                preExtractPosition.current.y,
              ),
            )
          }
        } catch (err) {
          console.log("[AndroidMarkerOverlay] Failed to resize window:", err)
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isExtractMode])

  return (
    <MarkerSelectionView
      theme="purple"
      isExtractMode={isExtractMode}
      isSelecting={isSelecting}
      selectionStart={selectionStart}
      selectionEnd={selectionEnd}
      currentMousePos={currentMousePos}
      extractRegions={extractRegions}
      containerRef={containerRef}
      backgroundOverlay={
        <>
          {mirrorBounds && (
            <div
              className="absolute bg-black/20 pointer-events-none"
              style={{
                left: mirrorBounds.x,
                top: mirrorBounds.y,
                width: mirrorBounds.width,
                height: mirrorBounds.height,
              }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-br from-purple-900/5 to-pink-900/5 pointer-events-none" />
        </>
      }
      onMouseDown={handleMouseDown}
      onExit={handleClick}
      onFloatingBallClick={handleClick}
    />
  )
}
