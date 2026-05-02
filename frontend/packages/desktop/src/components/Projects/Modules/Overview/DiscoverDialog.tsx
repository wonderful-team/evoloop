import { Button } from "@evoloop/shared/components/ui/button"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { Loader2, RefreshCw, Search, Shield } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { OpenAPI } from "@/client/core/OpenAPI"
import { ProjectProfilesService } from "@/client/sdk.gen"

interface DiscoverDialogProps {
  projectId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  onDiscovered?: () => void
}

export function DiscoverDialog({
  projectId,
  open,
  onOpenChange,
  onDiscovered,
}: DiscoverDialogProps) {
  const { t } = useTranslation()
  const [recordSecrets, setRecordSecrets] = useState(false)
  const [phase, setPhase] = useState<string>("idle")
  const [logs, setLogs] = useState<string[]>([])
  const eventSourceRef = useRef<EventSource | null>(null)

  // Clean up EventSource on unmount or close
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!open) {
      // Reset state when dialog closes
      setPhase("idle")
      setLogs([])
      setRecordSecrets(false)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [open])

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, msg].slice(-50))
  }

  const connectStream = (threadId: string) => {
    // Desktop uses Cookie Session; Cookie is sent automatically via withCredentials.
    const url = `${OpenAPI.BASE}/api/v1/stream/chat/${threadId}`
    const es = new EventSource(url, { withCredentials: true })
    eventSourceRef.current = es

    es.addEventListener("open", () => {
      addLog(t("projects.profile.stream.connected"))
    })

    es.addEventListener("status", (e) => {
      try {
        const data = JSON.parse(e.data)
        const status = data.status || ""
        if (status.includes("explor")) setPhase("exploring")
        else if (status.includes("install")) setPhase("installing")
        else if (status.includes("generat")) setPhase("generating")
        addLog(`[Status] ${status}`)
      } catch {
        // ignore
      }
    })

    es.addEventListener("stream", (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === "tool_start") {
          const name = data.data?.toolName || data.data?.displayName || "Tool"
          addLog(`→ ${name}`)
          if (name.toLowerCase().includes("setup")) setPhase("installing")
          if (name.toLowerCase().includes("write")) setPhase("generating")
        } else if (data.type === "tool_complete") {
          addLog(`✓ ${data.data?.toolName || "Tool"} complete`)
        } else if (data.type === "thinking") {
          const msg = data.message || ""
          if (msg.length < 100) addLog(`💭 ${msg}`)
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("error", (e: any) => {
      if (e.data) {
        try {
          const data = JSON.parse(e.data)
          if (data.error) {
            addLog(`Error: ${data.error}`)
          }
        } catch {
          // ignore
        }
      }
    })

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        // Connection closed — could be done or error
        setPhase((prev) => {
          if (prev !== "completed" && prev !== "error") {
            // Assume completed if we got this far without explicit error
            return "completed"
          }
          return prev
        })
        eventSourceRef.current = null
      }
    }
  }

  useEffect(() => {
    if (phase === "completed") {
      toast.success(t("projects.profile.discoveryCompleted"))
      onDiscovered?.()
      // Delay close so user sees final state
      const timer = setTimeout(() => {
        onOpenChange(false)
      }, 1500)
      return () => clearTimeout(timer)
    }
    if (phase === "error") {
      toast.error(t("projects.profile.discoveryFailed"))
    }
  }, [phase, onDiscovered, onOpenChange, t])

  const handleDiscover = async () => {
    setPhase("starting")
    addLog(t("projects.profile.startingDiscovery"))

    try {
      const result = await ProjectProfilesService.discoverProfile({
        projectId,
        requestBody: {
          record_secrets: recordSecrets,
        },
      })

      const threadId = result.thread_id
      if (!threadId) {
        throw new Error("No thread_id returned")
      }

      addLog(`${t("projects.profile.threadCreated")}: ${threadId}`)
      connectStream(threadId)
    } catch (err: any) {
      setPhase("error")
      addLog(`Error: ${err.message || String(err)}`)
    }
  }

  const isRunning = !["idle", "completed", "error"].includes(phase)
  const canStart = ["idle", "error"].includes(phase)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            {t("projects.profile.discoverTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("projects.profile.discoverDescription")}
          </DialogDescription>
        </DialogHeader>

        {canStart ? (
          <div className="space-y-4 py-4">
            {/* Option: Record Secrets */}
            <div className="flex items-start space-x-3 rounded-md border p-3">
              <Checkbox
                id="record-secrets"
                checked={recordSecrets}
                onCheckedChange={(checked) =>
                  setRecordSecrets(checked === true)
                }
              />
              <div className="space-y-1 leading-none">
                <label
                  htmlFor="record-secrets"
                  className="flex items-center gap-1.5 text-sm font-medium cursor-pointer"
                >
                  <Shield className="h-4 w-4 text-amber-500" />
                  {t("projects.profile.recordSecrets")}
                </label>
                <p className="text-xs text-muted-foreground">
                  {t("projects.profile.recordSecretsDescNew")}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3 py-4">
            {/* Progress indicator */}
            <div className="flex items-center gap-3">
              {!(phase === "completed" || phase === "error") && (
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
              )}
              {phase === "completed" && (
                <div className="h-5 w-5 rounded-full bg-green-500 flex items-center justify-center">
                  <svg
                    className="h-3 w-3 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={3}
                    role="img"
                    aria-label={t("projects.profile.phase.completed")}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                </div>
              )}
              <span className="text-sm font-medium capitalize">
                {phase === "starting" && t("projects.profile.phase.starting")}
                {phase === "exploring" && t("projects.profile.phase.exploring")}
                {phase === "installing" &&
                  t("projects.profile.phase.installing")}
                {phase === "generating" &&
                  t("projects.profile.phase.generating")}
                {phase === "completed" && t("projects.profile.phase.completed")}
                {phase === "error" && t("projects.profile.phase.error")}
              </span>
            </div>

            {/* Log output */}
            <div className="h-48 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs space-y-1">
              {logs.map((log, i) => (
                <div key={i} className="text-muted-foreground">
                  {log}
                </div>
              ))}
              {isRunning && (
                <div className="text-muted-foreground animate-pulse">...</div>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          {canStart ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t("common.cancel")}
              </Button>
              <Button onClick={handleDiscover} disabled={!canStart}>
                <RefreshCw className="h-4 w-4 mr-1" />
                {t("projects.profile.startDiscovery")}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isRunning}
            >
              {isRunning ? t("common.close") : t("common.done")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
