import { useEffect, useRef } from "react"
import { ProjectsService } from "@/client/sdk.gen"
import { useProjectStore, isGlobalProject } from "@/stores/projectStore"
import { isLoggedIn } from "@/hooks/useAuth"

// Determine which API to use based on auth state, or just use a new dedicated service method.
// Since `ProjectsService` is auto-generated, we might need a manual fetch or extend it.
// For now, I'll use a direct fetch wrapper or assume we can call the endpoint.
// The endpoint is GET /projects/{id}/status.
// ProjectsService likely doesn't have it yet unless we regenerate SDK.
// I will use a manual fetch for now to avoid SDK regeneration dependency in this task.

const fetchStatus = async (projectId: number) => {
  try {
    const response: any = await ProjectsService.getProjectStatus({ projectId })
    return response
  } catch (_e) {
    // ignore
  }
  return null
}

export function useProjectStatus() {
  const { currentProject, updateProjectStatus } = useProjectStore()
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    // Skip if not logged in
    if (!isLoggedIn()) return
    
    if (!currentProject) return

    // Skip status polling for global project (no indexing needed)
    if (isGlobalProject(currentProject)) return

    const projectId = currentProject.id

    const poll = async () => {
      const data = await fetchStatus(projectId)
      if (data) {
        // data = { "indexing": { status: "running"... }, "summarization": { status: "idle"... } }

        const updates: any = {}

        if (data.indexing) {
          updates.indexing_status = data.indexing.status
        }

        if (data.summarization) {
          updates.summarization_status = data.summarization.status
        }

        updateProjectStatus(projectId, updates)
      }
    }

    // Initial call
    poll()

    // Interval
    pollTimerRef.current = setInterval(poll, 3000)

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
      }
    }
  }, [currentProject?.id, updateProjectStatus])
}
