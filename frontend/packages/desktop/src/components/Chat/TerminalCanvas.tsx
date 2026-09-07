/**
 * TerminalCanvas – Full-screen xterm.js terminal view.
 *
 * Uses @xterm/xterm directly (no xterm-for-react wrapper) so it is compatible
 * with React 19.  The component:
 *   1. Mounts a real xterm Terminal into a DOM div via an imperative ref.
 *   2. Replays the full `terminalHistoryBuffer` from the store on mount.
 *   3. Incrementally appends new output as the buffer grows.
 *   4. Forwards all keyboard input to the `/terminal/input` endpoint so the
 *      server-side PTY receives Tab, arrow keys, Ctrl+C, etc.
 */

import { useTheme } from "@evoloop/shared/components/theme-provider"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { useChatStore } from "@/stores/chatStore"

const DARK_THEME = {
  background: "#1a1b26",
  foreground: "#c0caf5",
  cursor: "#c0caf5",
  selectionBackground: "rgba(122, 162, 247, 0.3)",
  selectionInactiveBackground: "rgba(122, 162, 247, 0.15)",
  black: "#15161e",
  red: "#f7768e",
  green: "#9ece6a",
  yellow: "#e0af68",
  blue: "#7aa2f7",
  magenta: "#bb9af7",
  cyan: "#7dcfff",
  white: "#a9b1d6",
  brightBlack: "#414868",
  brightRed: "#f7768e",
  brightGreen: "#9ece6a",
  brightYellow: "#e0af68",
  brightBlue: "#7aa2f7",
  brightMagenta: "#bb9af7",
  brightCyan: "#7dcfff",
  brightWhite: "#c0caf5",
}

const LIGHT_THEME = {
  background: "#f9fafb", // slate 50
  foreground: "#1f2937", // gray 800
  cursor: "#1f2937",
  selectionBackground: "rgba(37, 99, 235, 0.25)",
  selectionInactiveBackground: "rgba(37, 99, 235, 0.15)",
  black: "#111827",
  red: "#dc2626",
  green: "#16a34a",
  yellow: "#ca8a04",
  blue: "#2563eb",
  magenta: "#9333ea",
  cyan: "#0891b2",
  white: "#e5e7eb",
  brightBlack: "#4b5563",
  brightRed: "#ef4444",
  brightGreen: "#22c55e",
  brightYellow: "#eab308",
  brightBlue: "#3b82f6",
  brightMagenta: "#a855f7",
  brightCyan: "#06b6d4",
  brightWhite: "#ffffff",
}

export function TerminalCanvas() {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<import("@xterm/xterm").Terminal | null>(null)
  const fitAddonRef = useRef<import("@xterm/addon-fit").FitAddon | null>(null)
  const writtenLengthRef = useRef(0)

  const { resolvedTheme } = useTheme()
  const buffer = useChatStore((s) => s.terminalHistoryBuffer)
  const sendRawTerminalInput = useChatStore((s) => s.sendRawTerminalInput)

  // ── Mount / Unmount ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    let aborted = false
    let disposable: import("@xterm/xterm").IDisposable | null = null

    ;(async () => {
      const { Terminal } = await import("@xterm/xterm")
      const { FitAddon } = await import("@xterm/addon-fit")

      if (aborted) return

      const initialTheme = resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME

      const term = new Terminal({
        scrollback: 50_000,
        theme: initialTheme,
        fontFamily:
          '"Fira Code", "Cascadia Code", Menlo, Monaco, "Courier New", monospace',
        fontSize: 13,
        lineHeight: 1.4,
        cursorBlink: true,
        allowTransparency: false,
        convertEol: true,
      })

      const fitAddon = new FitAddon()
      term.loadAddon(fitAddon)

      term.open(containerRef.current!)
      fitAddon.fit()

      termRef.current = term
      fitAddonRef.current = fitAddon
      if (import.meta.env.DEV) {
        ;(window as any).__terminal = term
      }

      // Write any buffered history that arrived before mount
      const currentBuffer = useChatStore.getState().terminalHistoryBuffer
      if (currentBuffer) {
        term.write(currentBuffer)
        writtenLengthRef.current = currentBuffer.length
      } else {
        // Welcoming starting banner for terminal session initialization feedback
        term.writeln(`\x1b[1;36m${t("chat.terminal.welcomeBanner")}\x1b[0m`)
      }

      term.focus()

      disposable = term.onData((data: string) => {
        sendRawTerminalInput(data)
      })
    })()

    const observer = new ResizeObserver(() => {
      fitAddonRef.current?.fit()
    })
    if (containerRef.current) {
      observer.observe(containerRef.current)
    }

    return () => {
      aborted = true
      observer.disconnect()
      disposable?.dispose()
      termRef.current?.dispose()
      termRef.current = null
      fitAddonRef.current = null
      writtenLengthRef.current = 0
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync resolvedTheme changes ──────────────────────────────────────────────
  useEffect(() => {
    const term = termRef.current
    if (term) {
      term.options.theme = resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME
    }
  }, [resolvedTheme])

  // ── Incremental buffer rendering ──────────────────────────────────────────
  useEffect(() => {
    const term = termRef.current
    if (!term) return

    const newPart = buffer.slice(writtenLengthRef.current)
    if (newPart) {
      term.write(newPart)
      writtenLengthRef.current = buffer.length
    }
  }, [buffer])

  return (
    <div ref={containerRef} className="w-full h-full overflow-hidden px-4" />
  )
}
