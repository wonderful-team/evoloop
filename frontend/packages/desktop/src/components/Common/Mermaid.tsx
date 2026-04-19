
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

    useEffect(() => {
        let isCancelled = false

        const renderChart = async () => {
            if (!ref.current || !chart.trim()) return

            try {
                // Ensure unique ID for every render attempt to avoid conflicts in Mermaid v10/v11
                const renderId = `mermaid-${Math.random().toString(36).slice(2, 11)}`
                
                // Clear previous content or show loading state if needed
                // ref.current.innerHTML = '<div class="animate-pulse">Rendering...</div>';

                const { svg } = await mermaid.render(renderId, chart)
                
                if (!isCancelled && ref.current) {
                    ref.current.innerHTML = svg
                }
            } catch (error) {
                if (!isCancelled && ref.current) {
                    console.warn("Mermaid rendering failed (likely partial content):", error)
                    
                    // Only show detailed error if it looks like a final/complete chart
                    // Otherwise keep previous successful render or show nothing during streaming
                    const errorMessage = error instanceof Error ? error.message : String(error)
                    ref.current.innerHTML = `
                        <div class="text-left w-full">
                            <div class="text-red-400 text-xs font-medium mb-1">${t("mermaid.renderError", "Mermaid Render Error")}</div>
                            <pre class="text-[10px] text-muted-foreground bg-black/30 p-2 rounded overflow-x-auto border border-red-500/20"><code>${chart.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>
                            <div class="text-[9px] text-red-400/50 mt-1">${errorMessage.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
                        </div>
                    `
                }
            }
        }

        renderChart()

        return () => {
            isCancelled = true
        }
    }, [chart, t])

    return (
        <div 
            ref={ref} 
            className="mermaid-container my-4 flex justify-center bg-zinc-950/40 p-4 rounded-xl border border-zinc-800/50 overflow-x-auto" 
        />
    )
}
