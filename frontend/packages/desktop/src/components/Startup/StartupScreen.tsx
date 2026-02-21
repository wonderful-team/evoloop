import { useEffect, useRef, useState } from "react"
import { SystemService } from "@/client/sdk.gen"
import { useTranslation } from "react-i18next"
import { listen } from "@tauri-apps/api/event"
import { Loader2 } from "lucide-react"

interface StartupScreenProps {
    onReady: () => void
}

export default function StartupScreen({ onReady }: StartupScreenProps) {
    const { t } = useTranslation()
    const [logs, setLogs] = useState<string[]>([])
    const logContainerRef = useRef<HTMLDivElement>(null)
    const [isHealthy, setIsHealthy] = useState(false)

    // Auto-scroll logs
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
        }
    }, [logs])

    // Listen for logs
    useEffect(() => {
        let unlistenFn: (() => void) | undefined

        const setupListener = async () => {
            try {
                // Check if we are in a Tauri environment to avoid errors in browser
                // In Tauri v2, window.__TAURI_INTERNALS__ is the indicator
                if (typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
                    unlistenFn = await listen<string>("backend-log", (event) => {
                        setLogs((prev) => [...prev, event.payload])
                    })
                }
            } catch (e) {
                console.warn("Tauri event listener failed (likely running in browser):", e)
            }
        }

        setupListener()

        return () => {
            if (unlistenFn) unlistenFn()
        }
    }, [])

    // Poll for health
    useEffect(() => {
        let intervalId: NodeJS.Timeout

        const checkHealth = async () => {
            try {
                await SystemService.healthCheck()
                setIsHealthy(true)
                clearInterval(intervalId)
                // Add a small delay for user to see success
                setTimeout(() => {
                    onReady()
                }, 800)
            } catch (e) {
                // Ignore connection refused
            }
        }

        intervalId = setInterval(checkHealth, 500)
        return () => clearInterval(intervalId)
    }, [onReady])

    return (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-zinc-950 text-zinc-100">
            <div className="w-full max-w-3xl p-6 space-y-6">
                <div className="flex items-center space-x-4">
                    <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20">
                        {isHealthy ? (
                            <div className="h-3 w-3 rounded-full bg-white animate-ping" />
                        ) : (
                            <Loader2 className="h-8 w-8 text-white animate-spin" />
                        )}
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">EvoLoop</h1>
                        <p className="text-sm text-zinc-400">
                            {isHealthy ? t("startup.backendReady") : t("startup.initializing")}
                        </p>
                    </div>
                </div>

                {/* Terminal Window */}
                <div className="relative rounded-lg border border-zinc-800 bg-black/50 backdrop-blur-xl shadow-2xl">
                    <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/50 px-4 py-2">
                        <div className="flex space-x-2">
                            <div className="h-3 w-3 rounded-full bg-red-500/20 border border-red-500/50" />
                            <div className="h-3 w-3 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                            <div className="h-3 w-3 rounded-full bg-green-500/20 border border-green-500/50" />
                        </div>
                        <div className="text-xs font-medium text-zinc-500 font-mono">system.log</div>
                    </div>

                    <div
                        ref={logContainerRef}
                        className="h-64 overflow-y-auto p-4 font-mono text-xs text-zinc-300 space-y-1 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent"
                    >
                        {logs.length === 0 && (
                            <span className="text-zinc-600 italic">{t("startup.waitingLogs")}</span>
                        )}
                        {logs.map((log, i) => (
                            <div key={i} className="break-all whitespace-pre-wrap border-l-2 border-transparent hover:border-zinc-700 pl-2 transition-colors">
                                <span className="opacity-50 select-none mr-2">
                                    {new Date().toLocaleTimeString().split(' ')[0]}
                                </span>
                                {log}
                            </div>
                        ))}
                        {isHealthy && (
                            <div className="text-green-400 font-bold mt-2">
                                {t("startup.systemCheckPassed")}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
