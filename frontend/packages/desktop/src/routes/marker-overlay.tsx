import i18n from "@evoloop/shared/i18n"
import {createFileRoute} from "@tanstack/react-router"
import {emit, listen, type UnlistenFn} from "@tauri-apps/api/event"
import {getCurrentWindow, LogicalPosition, LogicalSize,} from "@tauri-apps/api/window"
import {useCallback, useEffect, useRef, useState} from "react"
import {LearningService} from "@/client/sdk.gen"
import {isTauri} from "@/lib/tauri"
import {type ExtractRegion, MarkerSelectionView,} from "@/components/Overlay/MarkerSelectionView"

export const Route = createFileRoute("/marker-overlay")({
  component: () => {
    if (!isTauri()) {
      return (
        <div className="flex items-center justify-center h-screen text-muted-foreground">
          {i18n.t("overlay.desktopOnly")}
        </div>
      )
    }
    return <MarkerOverlay />
  },
})

function MarkerOverlay() {
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

  // Listen for session info from main window
  const sessionIdRef = useRef<string | null>(null)
  const recordingStartTimeRef = useRef<number | null>(null)
  const threadIdRef = useRef<string | null>(null)

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
        console.log("[MarkerOverlay] Failed to set initial position", e)
      }
    }
    initPosition()
  }, [])

  useEffect(() => {
    let unlisten: UnlistenFn | undefined

    const setupListener = async () => {
      unlisten = await listen<{
        sessionId: string
        recordingStartTime: number | null
        threadId: string | null
      }>("desktop-marker-session", (event) => {
        sessionIdRef.current = event.payload.sessionId
        recordingStartTimeRef.current = event.payload.recordingStartTime
        threadIdRef.current = event.payload.threadId
        console.log("[MarkerOverlay] Session info received:", event.payload)
      })
    }

    setupListener()

    return () => {
      if (unlisten) unlisten()
    }
  }, [])

  // Track mouse position for crosshair
  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      setCurrentMousePos({ x: e.clientX, y: e.clientY })
      if (isSelecting) {
        setSelectionEnd({ x: e.clientX, y: e.clientY })
      }
    },
    [isSelecting],
  )

  // Handle window dragging
  const handleMouseDown = useCallback(
    async (e: React.MouseEvent) => {
      if (isExtractMode) {
        e.preventDefault()
        e.stopPropagation()
        setIsSelecting(true)
        setSelectionStart({ x: e.clientX, y: e.clientY })
        setSelectionEnd({ x: e.clientX, y: e.clientY })
        return
      }

      // Use Tauri's native dragging for smooth, jitter-free OS-level window movement
      try {
        const win = getCurrentWindow()
        await win.startDragging()
      } catch (err) {
        console.log("[MarkerOverlay] Failed to start dragging:", err)
      }
    },
    [isExtractMode],
  )

  const handleMouseUp = useCallback(async () => {
    if (isSelecting) {
      setIsSelecting(false)

      const screenWidth = window.screen.width
      const screenHeight = window.screen.height

      const x1 = Math.min(selectionStart.x, selectionEnd.x)
      const y1 = Math.min(selectionStart.y, selectionEnd.y)
      const x2 = Math.max(selectionStart.x, selectionEnd.x)
      const y2 = Math.max(selectionStart.y, selectionEnd.y)

      const isPointClick = x2 - x1 < 10 || y2 - y1 < 10
      const startTime = recordingStartTimeRef.current
      const relativeTimestamp = startTime ? Date.now() - startTime : 0

      const region: ExtractRegion = {
        id: `extract_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: relativeTimestamp,
        x: x1 / screenWidth,
        y: y1 / screenHeight,
        width: isPointClick ? 0.02 : (x2 - x1) / screenWidth,
        height: isPointClick ? 0.02 : (y2 - y1) / screenHeight,
      }

      setExtractRegions((prev) => [...prev, region])
      await saveRegionToBackend(region)

      setIsExtractMode(false)
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
        console.log("[MarkerOverlay] Failed to resize window:", e)
      }

      // Notify main window to resume recording interaction events
      await emit("marking-stopped", {})

      return
    }
  }, [isSelecting, selectionStart, selectionEnd])

  const saveRegionToBackend = async (region: ExtractRegion) => {
    const sessionId = sessionIdRef.current
    const threadId = threadIdRef.current

    if (!sessionId || !threadId) {
      console.error("[MarkerOverlay] No session ID or thread ID available")
      return
    }

    try {
      // [Scheme A] Save region_extract event to TraceEvent table instead of annotations
      await LearningService.persistDomEvents({
        requestBody: {
          session_id: sessionId,
          thread_id: threadId,
          events: [
            {
              timestamp: region.timestamp,
              event_type: "region_extract",
              selector: `screen://${region.x.toFixed(4)}/${region.y.toFixed(4)}`,
              target_text: "Screen region extraction",
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

      await emit("desktop-region-marked", { region })
      console.log(
        "[MarkerOverlay] Region extract event saved to TraceEvent:",
        region,
      )
    } catch (error) {
      console.error(
        "[MarkerOverlay] Failed to save region extract event:",
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
        console.log("[MarkerOverlay] Failed to resize window:", e)
      }
      // Notify main window to resume recording interaction events
      await emit("marking-stopped", {})
      return
    }

    setIsExtractMode(true)
    try {
      const win = getCurrentWindow()
      const pos = await win.outerPosition()
      preExtractPosition.current = { x: pos.x, y: pos.y }

      await win.setSize(
        new LogicalSize(window.screen.width, window.screen.height),
      )
      await win.setPosition(new LogicalPosition(0, 0))
      await win.setIgnoreCursorEvents(false)

      // [FIX] Bring window to front
      await win.setFocus()

      // Notify main window to stop recording interaction events
      await emit("marking-started", {})
    } catch (e) {
      console.log("[MarkerOverlay] Failed to expand window:", e)
    }
  }, [isExtractMode])

  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (e.key === "Escape" && isExtractMode) {
        setIsExtractMode(false)
        setIsSelecting(false)
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
          console.log("[MarkerOverlay] Failed to resize window:", err)
        }
        // Notify main window to resume recording interaction events
        await emit("marking-stopped", {})
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isExtractMode])

  return (
    <MarkerSelectionView
      theme="blue"
      isExtractMode={isExtractMode}
      isSelecting={isSelecting}
      selectionStart={selectionStart}
      selectionEnd={selectionEnd}
      currentMousePos={currentMousePos}
      extractRegions={extractRegions}
      containerRef={containerRef}
      backgroundOverlay={
        <div className="absolute inset-0 bg-gradient-to-br from-blue-900/10 to-purple-900/10 pointer-events-none" />
      }
      onMouseDown={handleMouseDown}
      onExit={handleClick}
      onFloatingBallClick={handleClick}
    />
  )
}
