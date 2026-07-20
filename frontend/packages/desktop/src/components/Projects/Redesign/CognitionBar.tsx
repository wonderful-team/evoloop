import { Button } from "@evoloop/shared/components/ui/button"
import { useParams } from "@tanstack/react-router"
import { CheckCircle2, Cpu, Loader2, RefreshCw, Zap } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { ProjectsService } from "@/client"
import { systemSSEClient } from "@/lib/SystemSSEClient"

export function CognitionBar() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const [pipelinePhase, setPipelinePhase] = useState<number>(3) // Phase 1..4
  const [status, setStatus] = useState<string>("completed")
  const [coverage] = useState<number>(98)
  const [isTriggering, setIsTriggering] = useState<boolean>(false)

  useEffect(() => {
    if (!projectId) return

    // Subscribe to backend SSE status changes
    const sse = systemSSEClient as any
    const unsub = sse.subscribe?.("indexing_status_changed", (data: any) => {
      if (data?.project_id === Number(projectId)) {
        if (data?.status) setStatus(data.status)
        if (data?.phase) setPipelinePhase(data.phase)
      }
    })

    return () => unsub?.()
  }, [projectId])

  const handleTriggerIncrementalScan = async () => {
    if (!projectId) return
    setIsTriggering(true)
    try {
      await ProjectsService.runIndexingEndpoint({
        requestBody: { project_id: Number(projectId) },
      })
      toast.success("已触发出增量脏检查与索引刷新")
    } catch {
      toast.error("触发索引刷新失败")
    } finally {
      setIsTriggering(false)
    }
  }

  const phases = [
    { num: 1, label: "Phase 1: 增量脏检查" },
    { num: 2, label: "Phase 2: 符号与结构提取" },
    { num: 3, label: "Phase 3: 依赖图与 Leiden 聚类" },
    { num: 4, label: "Phase 4: 拓扑与 AppMap 骨架" },
  ]

  const noDragStyle = { WebkitAppRegion: "no-drag" } as React.CSSProperties

  return (
    <div
      data-tauri-drag-region
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      className="h-10 border-b border-border bg-card px-4 flex items-center justify-between shrink-0 text-xs select-none relative z-20"
    >
      {/* Left: Pipeline 4-Phase Step Indicators */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-1.5 font-semibold text-primary"
          style={noDragStyle}
        >
          <Cpu className="h-3.5 w-3.5" />
          <span>AI 代码库管道</span>
        </div>

        <div className="h-3.5 w-[1px] bg-border" />

        <div className="flex items-center gap-2">
          {phases.map((p) => {
            const isCompleted = p.num < pipelinePhase || status === "completed"
            const isCurrent = p.num === pipelinePhase && status === "indexing"
            return (
              <div
                key={p.num}
                className="flex items-center gap-1 cursor-pointer hover:opacity-80 transition-opacity"
                style={noDragStyle}
                title={p.label}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />
                ) : isCurrent ? (
                  <Loader2 className="h-3 w-3 animate-spin text-blue-500 shrink-0" />
                ) : (
                  <span className="h-3 w-3 rounded-full border border-muted-foreground/30 flex items-center justify-center text-[9px] text-muted-foreground shrink-0">
                    {p.num}
                  </span>
                )}
                <span
                  className={
                    isCompleted
                      ? "text-foreground font-medium"
                      : isCurrent
                      ? "text-blue-500 font-medium"
                      : "text-muted-foreground/60"
                  }
                >
                  {p.label}
                </span>
                {p.num < 4 && <span className="text-muted-foreground/30 ml-1">→</span>}
              </div>
            )
          })}
        </div>
      </div>

      {/* Right: Symbol Coverage & Incremental Refresh Button */}
      <div className="flex items-center gap-3" style={noDragStyle}>
        <div className="flex items-center gap-1 text-muted-foreground">
          <Zap className="h-3 w-3 text-amber-500" />
          <span>符号索引覆盖率: <strong className="text-foreground">{coverage}%</strong></span>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2.5 text-xs gap-1.5 shadow-xs cursor-pointer"
          onClick={handleTriggerIncrementalScan}
          disabled={isTriggering}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isTriggering ? "animate-spin" : ""}`} />
          <span>增量刷新</span>
        </Button>
      </div>
    </div>
  )
}
