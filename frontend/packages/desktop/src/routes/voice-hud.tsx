import { createFileRoute } from "@tanstack/react-router"
import { LogicalPosition } from "@tauri-apps/api/dpi"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow, primaryMonitor } from "@tauri-apps/api/window"
import { AnimatePresence, motion } from "framer-motion"
import {
  Check,
  Loader2,
  MessageSquare,
  Mic,
  Sparkles,
  Volume2,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { isTauri } from "@/lib/tauri"

export const Route = createFileRoute("/voice-hud")({
  component: () => {
    const { t } = useTranslation()
    if (!isTauri()) {
      return (
        <div className="flex items-center justify-center h-screen text-muted-foreground bg-background">
          {t("voiceHud.desktopOnly")}
        </div>
      )
    }
    return <VoiceHUD />
  },
})

interface HUDState {
  mode: "off" | "dictation" | "dialogue"
  state: "idle" | "listening" | "processing" | "speaking" | "interrupted"
  text?: string
}

function VoiceHUD() {
  const { t } = useTranslation()
  const [hudState, setHudState] = useState<HUDState>({
    mode: "off",
    state: "idle",
    text: "",
  })

  useEffect(() => {
    // Make document and root background transparent
    const win = getCurrentWindow()

    document.body.style.background = "transparent"
    const rootEl = document.getElementById("root")
    if (rootEl) {
      rootEl.style.background = "transparent"
    }

    // Position it at the bottom-center of primary monitor
    primaryMonitor()
      .then((monitor) => {
        if (monitor) {
          const scaleFactor = monitor.scaleFactor || 1
          const monitorWidth = monitor.size.width / scaleFactor
          const monitorHeight = monitor.size.height / scaleFactor

          const hudWidth = 300
          const hudHeight = 70

          const x = Math.round((monitorWidth - hudWidth) / 2)
          const y = Math.round(monitorHeight * 0.85 - hudHeight) // 15% from bottom

          win.setPosition(new LogicalPosition(x, y)).catch(console.error)
        }
      })
      .catch(console.error)

    const unlistenPromise = listen<HUDState>("hud-update", (event) => {
      setHudState(event.payload)
    })

    // Rust controls the main window show/hide, but HUD handles the feedback
    // because it is visible even when the main window is hidden/trayed.
    const unlistenNavPromise = listen<{ route: string; feedback?: string }>(
      "voice:navigate",
      async (event) => {
        const feedback = event.payload.feedback
        if (feedback) {
          const { emit } = await import("@tauri-apps/api/event")
          await emit("hud-update", {
            mode: "dialogue",
            state: "idle",
            text: feedback,
          })
          // Reset to listening after 2s
          setTimeout(() => {
            emit("hud-update", {
              mode: "dialogue",
              state: "listening",
              text: "",
            }).catch(console.error)
          }, 2000)
        }
      },
    )

    return () => {
      unlistenPromise.then((fn) => fn())
      unlistenNavPromise.then((fn) => fn())
    }
  }, [])

  const { mode, state, text } = hudState

  if (mode === "off") {
    return null
  }

  // Determine HUD label, icon, and colors
  let label = ""
  let icon = <Mic className="w-5 h-5 text-blue-400 animate-pulse" />
  let bgGradient = "from-zinc-900/95 to-black/95"
  let borderGlow = "border-zinc-800/80 shadow-[0_0_15px_rgba(0,0,0,0.5)]"

  if (mode === "dictation") {
    if (state === "listening") {
      label = t("voiceHud.dictationListening")
      icon = (
        <div className="relative flex items-center justify-center w-6 h-6">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <Mic className="relative w-4 h-4 text-blue-400" />
        </div>
      )
      bgGradient = "from-blue-950/90 to-zinc-950/95"
      borderGlow = "border-blue-500/30 shadow-[0_0_20px_rgba(59,130,246,0.2)]"
    } else if (state === "processing") {
      label = text || t("voiceHud.polishing")
      icon = (
        <Sparkles
          className="w-4 h-4 text-amber-400 animate-spin"
          style={{ animationDuration: "3s" }}
        />
      )
      bgGradient = "from-amber-950/90 to-zinc-950/95"
      borderGlow = "border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.2)]"
    } else if (state === "idle" && text === "pasted") {
      label = t("voiceHud.pasted")
      icon = <Check className="w-4 h-4 text-emerald-400" />
      bgGradient = "from-emerald-950/90 to-zinc-950/95"
      borderGlow = "border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.2)]"
    } else {
      label = t("voiceHud.dictation")
      icon = <Mic className="w-4 h-4 text-blue-400" />
    }
  } else if (mode === "dialogue") {
    if (state === "listening") {
      label = t("voiceHud.dialogueListening")
      icon = (
        <div className="relative flex items-center justify-center w-6 h-6">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75" />
          <MessageSquare className="relative w-4 h-4 text-purple-400" />
        </div>
      )
      bgGradient = "from-purple-950/90 to-zinc-950/95"
      borderGlow = "border-purple-500/30 shadow-[0_0_20px_rgba(168,85,247,0.2)]"
    } else if (state === "processing") {
      label = text || t("voiceHud.thinking")
      icon = <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
      bgGradient = "from-zinc-950/90 to-purple-950/90"
      borderGlow = "border-purple-500/20 shadow-[0_0_20px_rgba(168,85,247,0.15)]"
    } else if (state === "speaking") {
      label = t("voiceHud.speaking")
      icon = <Volume2 className="w-4 h-4 text-emerald-400 animate-bounce" />
      bgGradient = "from-emerald-950/90 to-zinc-950/95"
      borderGlow = "border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.2)]"
    } else if (state === "idle" && text) {
      // Feedback confirmation (e.g. "已回到主界面")
      label = text
      icon = <Check className="w-4 h-4 text-emerald-400" />
      bgGradient = "from-emerald-950/90 to-zinc-950/95"
      borderGlow = "border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.2)]"
    } else {
      label = t("voiceHud.dialogue")
      icon = <MessageSquare className="w-4 h-4 text-purple-400" />
    }
  }

  return (
    <div className="flex items-center justify-center w-full h-full p-2 select-none pointer-events-none bg-transparent">
      <div className="pointer-events-auto cursor-move" data-tauri-drag-region>
        <AnimatePresence mode="wait">
          <motion.div
            key={`${mode}-${state}`}
            initial={{ opacity: 0, y: 15, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -15, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 350, damping: 25 }}
            className={`flex items-center gap-3 px-5 py-3 rounded-full border bg-gradient-to-r ${bgGradient} ${borderGlow} text-white max-w-[280px] w-full backdrop-blur-md`}
            data-tauri-drag-region
          >
            <div className="flex-shrink-0" data-tauri-drag-region>{icon}</div>
            <div className="flex-grow min-w-0" data-tauri-drag-region>
              <p className="text-sm font-medium tracking-wide truncate text-zinc-100" data-tauri-drag-region>
                {label}
              </p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
