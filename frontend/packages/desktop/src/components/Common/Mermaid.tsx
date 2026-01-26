
import mermaid from "mermaid"
import { useEffect, useRef } from "react"

// Initialize mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
    fontFamily: "inherit",
})

export const Mermaid = ({ chart }: { chart: string }) => {
    const ref = useRef<HTMLDivElement>(null)
    const id = useRef(`mermaid-${Math.random().toString(36).slice(2)}`)

    useEffect(() => {
        if (ref.current) {
            try {
                mermaid.render(id.current, chart).then(({ svg }) => {
                    if (ref.current) {
                        ref.current.innerHTML = svg
                    }
                })
            } catch (error) {
                console.error("Mermaid rendering error:", error)
                if (ref.current) {
                    ref.current.innerHTML = `<div class="text-red-500 text-xs p-2 border border-red-500 rounded bg-red-500/10">Failed to render diagram</div>`
                }
            }
        }
    }, [chart])

    return <div ref={ref} className="mermaid my-4 flex justify-center bg-zinc-950/50 p-4 rounded-lg border border-zinc-800" />
}
