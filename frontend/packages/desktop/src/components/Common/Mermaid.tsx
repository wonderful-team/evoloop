import mermaid from "mermaid"
import { memo, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"

// Initialize mermaid
// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
  fontFamily: "inherit",
  // Suppress global error UI at the bottom of the page
  suppressErrorNotifications: true,
})

export const Mermaid = memo(({ chart }: { chart: string }) => {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const lastValidSvg = useRef<string>("")

  useEffect(() => {
    let isCancelled = false

    const renderChart = async () => {
      const trimmedChart = chart.trim()
      if (!ref.current || !trimmedChart) return

      // Basic validation: Don't try to render if it's just the header (e.g. "graph TD")
      // This avoids frequent flicker/errors during the very start of streaming.
      const lines = trimmedChart.split("\n").filter((l) => l.trim() !== "")
      if (
        lines.length <= 1 &&
        (trimmedChart.includes("graph") || trimmedChart.includes("flowchart"))
      ) {
        return
      }

      try {
        // Pre-check syntax before rendering to avoid Mermaid's internal error DOM injection
        // We do not suppress errors here so that invalid syntax throws and triggers the catch block fallback
        await mermaid.parse(trimmedChart)

        const renderId = `mermaid-${Math.random().toString(36).slice(2, 11)}`
        const { svg } = await mermaid.render(renderId, trimmedChart)

        if (!isCancelled && ref.current) {
          lastValidSvg.current = svg
          ref.current.innerHTML = svg
        }
      } catch (error) {
        // Only show error if we don't have a last valid render to fallback to
        if (!isCancelled && ref.current && !lastValidSvg.current) {
          const _errorMessage =
            error instanceof Error ? error.message : String(error)
          ref.current.innerHTML = `
                        <div class="text-left w-full opacity-60">
                            <div class="text-[11px] text-destructive italic mb-2 font-medium">⚠️ ${t("mermaid.diagramSyntaxError")}</div>
                            <pre class="text-[10px] text-muted-foreground bg-black/5 dark:bg-white/5 p-3 rounded-lg overflow-x-auto border border-border/50 whitespace-pre-wrap break-all font-mono"><code>${chart.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
                        </div>
                    `
        }
      }
    }

    const timer = setTimeout(() => {
      if (!isCancelled) {
        renderChart()
      }
    }, 300)

    return () => {
      isCancelled = true
      clearTimeout(timer)
    }
  }, [chart, t])

  return (
    <div
      ref={ref}
      className="mermaid-container my-4 flex justify-center bg-zinc-950/40 p-4 rounded-xl border border-zinc-800/50 overflow-x-auto min-h-[60px]"
    />
  )
})
