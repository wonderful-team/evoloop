import { useEffect, useRef, useState } from "react"
import { SystemService } from "@/client/sdk.gen"
import { useTranslation } from "react-i18next"
import { listen } from "@tauri-apps/api/event"
import { cn } from "@evoloop/shared/lib/utils"
import icon from "/assets/images/evoloop-icon.svg"

interface StartupScreenProps {
    onReady: () => void
}

// 启动页面模式：true = 终端窗口（开发模式），false = 简洁 LOGO + 进度条（正常模式）
// 通过 .env 中的 VITE_STARTUP_DEBUG_MODE 配置，默认为 false
const isDebugMode = import.meta.env.DEV && import.meta.env.VITE_STARTUP_DEBUG_MODE === "true"

export default function StartupScreen({ onReady }: StartupScreenProps) {
    const { t } = useTranslation()
    const [logs, setLogs] = useState<string[]>([])
    const logContainerRef = useRef<HTMLDivElement>(null)
    const [isHealthy, setIsHealthy] = useState(false)
    
    // 进度条相关状态（用于简洁模式）
    const [progress, setProgress] = useState(0)
    const [statusText, setStatusText] = useState("")
    const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)

    // 模拟进度增长（简洁模式）
    useEffect(() => {
        if (isDebugMode) return // 调试模式不使用模拟进度

        const statusMessages = [
            { threshold: 0, text: t("startup.status.connecting") },
            { threshold: 20, text: t("startup.status.initializing") },
            { threshold: 40, text: t("startup.status.loadingModules") },
            { threshold: 60, text: t("startup.status.preparingAI") },
            { threshold: 80, text: t("startup.status.finalizing") },
            { threshold: 100, text: t("startup.status.ready") },
        ]

        let currentProgress = 0
        progressIntervalRef.current = setInterval(() => {
            // 模拟渐进增长，但不超过 95%（等待真实健康检查）
            if (currentProgress < 95 && !isHealthy) {
                // 增长速度随进度变慢
                const increment = Math.max(1, (100 - currentProgress) / 20)
                currentProgress = Math.min(95, currentProgress + increment)
                setProgress(currentProgress)

                // 更新状态文本
                const message = statusMessages
                    .slice()
                    .reverse()
                    .find(m => currentProgress >= m.threshold)
                if (message) {
                    setStatusText(message.text)
                }
            }
        }, 200)

        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current)
            }
        }
    }, [isHealthy, t])

    // 健康检查完成后，进度条直接到 100%
    useEffect(() => {
        if (isHealthy) {
            setProgress(100)
            setStatusText(t("startup.status.ready"))
        }
    }, [isHealthy, t])

    // Auto-scroll logs (调试模式)
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
        }
    }, [logs])

    // Listen for logs (调试模式)
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
                // Log error for debugging but don't spam console
                if (e instanceof Error && !e.message?.includes('Network Error')) {
                    console.error('Health check failed:', e)
                }
            }
        }

        intervalId = setInterval(checkHealth, 500)
        return () => clearInterval(intervalId)
    }, [onReady])

    // ===== 简洁模式：LOGO + 进度条 =====
    const renderSimpleUI = () => (
        <div className="flex flex-col items-center justify-center w-full max-w-sm space-y-8 p-8">
            {/* Logo 区域 */}
            <div className="relative">
                <div className={cn(
                    "relative flex h-24 w-24 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20 transition-all duration-500",
                    isHealthy && "scale-110"
                )}>
                    <img 
                        src={icon} 
                        alt="EvoLoop" 
                        className={cn(
                            "size-14 transition-all duration-500",
                            !isHealthy && "animate-pulse"
                        )} 
                    />
                </div>
                {/* 脉冲动画环 */}
                {!isHealthy && (
                    <>
                        <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-ping" style={{ animationDuration: '2s' }} />
                        <div className="absolute -inset-2 rounded-3xl bg-primary/5 animate-pulse" style={{ animationDuration: '3s' }} />
                    </>
                )}
            </div>

            {/* 标题和状态 */}
            <div className="text-center space-y-3">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    {t("app.name")}
                </h1>
                <p className={cn(
                    "text-sm font-medium transition-colors duration-300",
                    isHealthy ? "text-primary" : "text-muted-foreground"
                )}>
                    {isHealthy 
                        ? t("startup.backendReady")
                        : statusText || t("startup.initializing")
                    }
                </p>
            </div>

            {/* 进度条 */}
            <div className="w-full space-y-3">
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div 
                        className={cn(
                            "h-full rounded-full transition-all duration-300 ease-out",
                            isHealthy ? "bg-primary" : "bg-primary/70"
                        )}
                        style={{ width: `${progress}%` }}
                    />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{t("startup.loading")}</span>
                    <span>{Math.round(progress)}%</span>
                </div>
            </div>

            {/* 提示文本 */}
            <p className="text-xs text-muted-foreground/70 text-center max-w-xs">
                {t("startup.hint")}
            </p>
        </div>
    )

    // ===== 调试模式：终端窗口 =====
    const renderDebugUI = () => (
        <div className="w-full max-w-3xl p-6 space-y-6">
            <div className="flex items-center space-x-4">
                <div className="relative flex h-16 w-16 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
                    <img src={icon} alt="EvoLoop" className="size-10" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-foreground">{t("app.name")}</h1>
                    <p className="text-sm text-muted-foreground">
                        {isHealthy ? t("startup.backendReady") : t("startup.initializing")}
                    </p>
                </div>
            </div>

            {/* Terminal Window */}
            <div className="relative rounded-xl border border-border bg-card/50 backdrop-blur-xl shadow-sm overflow-hidden">
                <div className="flex items-center justify-between border-b border-border bg-muted/50 px-4 py-2">
                    <div className="flex space-x-2">
                        <div className="h-3 w-3 rounded-full bg-destructive/80" />
                        <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
                        <div className="h-3 w-3 rounded-full bg-green-500/80" />
                    </div>
                    <div className="text-xs font-medium text-muted-foreground font-mono">{t("startup.logTitle")}</div>
                </div>

                <div
                    ref={logContainerRef}
                    className="h-64 overflow-y-auto p-4 font-mono text-xs text-foreground/80 space-y-1 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent"
                >
                    {logs.length === 0 && (
                        <span className="text-muted-foreground italic">{t("startup.waitingLogs")}</span>
                    )}
                    {logs.map((log, i) => (
                        <div key={i} className="break-all whitespace-pre-wrap border-l-2 border-transparent hover:border-muted-foreground/30 pl-2 transition-colors">
                            <span className="opacity-50 select-none mr-2">
                                {new Date().toLocaleTimeString().split(' ')[0]}
                            </span>
                            {log}
                        </div>
                    ))}
                    {isHealthy && (
                        <div className="text-primary font-semibold mt-2">
                            {t("startup.systemCheckPassed")}
                        </div>
                    )}
                </div>
            </div>

            {/* 调试模式标签 */}
            <div className="flex justify-center">
                <span className="px-3 py-1 rounded-full bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 text-xs font-medium border border-yellow-500/20">
                    {t("startup.devMode")}
                </span>
            </div>
        </div>
    )

    return (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background text-foreground">
            {isDebugMode ? renderDebugUI() : renderSimpleUI()}
        </div>
    )
}
