import { useCallback, useEffect, useRef, useState } from "react"

export interface ModelStatus {
  id: string
  name: string
  size: string
  size_gb: number
  downloaded: boolean
  available: boolean
  status: string // "idle" | "downloading" | "completed" | "failed"
  progress: number | null
}

export function useModelManager() {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)
  const eventSourceRef = useRef<EventSource | null>(null)
  const backendUrl = "http://127.0.0.1:20160"

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/api/v1/models/status`)
      const data = await res.json()
      setModels(data.models || [])
    } catch (err) {
      console.error("[ModelManager] Failed to fetch model status:", err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const startDownload = useCallback(
    async (modelId: string) => {
      // Immediately set downloading state for responsive UI
      setModels((prev) =>
        prev.map((m) =>
          m.id === modelId ? { ...m, status: "downloading", progress: 0 } : m,
        ),
      )
      try {
        const res = await fetch(`${backendUrl}/api/v1/models/download`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        })
        if (!res.ok) {
          const err = await res.json()
          setModels((prev) =>
            prev.map((m) =>
              m.id === modelId ? { ...m, status: "failed" } : m,
            ),
          )
          throw new Error(err.error || "Download failed")
        }

        // Subscribe to SSE progress
        if (eventSourceRef.current) {
          eventSourceRef.current.close()
        }
        const es = new EventSource(
          `${backendUrl}/api/v1/models/download/progress?model_id=${modelId}`,
        )
        eventSourceRef.current = es

        es.onmessage = (event) => {
          const data = JSON.parse(event.data)
          setModels((prev) =>
            prev.map((m) =>
              m.id === modelId
                ? {
                    ...m,
                    status: data.status,
                    progress: data.progress,
                    downloaded: data.status === "completed",
                    available: data.status === "completed" || m.id === "kokoro",
                  }
                : m,
            ),
          )
          if (data.status === "completed" || data.status === "failed") {
            es.close()
            eventSourceRef.current = null
            // Refresh full status after completion
            setTimeout(() => fetchStatus(), 1000)
          }
        }
      } catch (err: any) {
        console.error("[ModelManager] Download error:", err)
      }
    },
    [fetchStatus],
  )

  // Cleanup
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  return { models, loading, startDownload, refresh: fetchStatus }
}
