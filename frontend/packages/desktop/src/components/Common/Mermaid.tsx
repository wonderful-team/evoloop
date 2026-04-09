
import mermaid from "mermaid"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"

// Initialize mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
    fontFamily: "inherit",
})

export const Mermaid = ({ chart }: { chart: string }) => {
    const { t } = useTranslation()
    const ref = useRef<HTMLDivElement>(null)
    const id = useRef(`mermaid-${Math.random().toString(36).slice(2)}`)

    useEffect(() => {
        if (ref.current) {
            mermaid.render(id.current, chart).then(({ svg }) => {
                if (ref.current) {
                    ref.current.innerHTML = svg
                }
            }).catch((error) => {
                console.error("Mermaid rendering error:", error)
                if (ref.current) {
                    const errorMessage = error instanceof Error ? error.message : String(error)
                    ref.current.innerHTML = `
                        <div class="text-left w-full">
                            <div class="text-red-400 text-xs font-medium mb-2">${t("mermaid.renderError")}</div>
                            <div class="text-red-400/70 text-xs mb-2">${errorMessage.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
                            <pre class="text-xs text-muted-foreground bg-black/30 p-2 rounded overflow-x-auto"><code>${chart.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>
                        </div>
                    `
                }
            })
        }
    }, [chart])

    return <div ref={ref} className="mermaid my-4 flex justify-center bg-zinc-950/50 p-4 rounded-lg border border-zinc-800" />
}
