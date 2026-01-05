
import { useEffect, useRef } from 'react'
import { useProjectStore } from '@/stores/projectStore'


// Determine which API to use based on auth state, or just use a new dedicated service method.
// Since `ProjectsService` is auto-generated, we might need a manual fetch or extend it.
// For now, I'll use a direct fetch wrapper or assume we can call the endpoint.
// The endpoint is GET /projects/{id}/status.
// ProjectsService likely doesn't have it yet unless we regenerate SDK.
// I will use a manual fetch for now to avoid SDK regeneration dependency in this task.

const fetchStatus = async (projectId: number) => {
    const token = localStorage.getItem('access_token')
    const headers: Record<string, string> = {}
    if (token) {
        headers['Authorization'] = `Bearer ${token}`
    }

    // TODO: Use configured base URL
    // We can piggyback on EvoLoopApi or just use fetch
    // Let's assume relative path works due to proxy, or use absolute if needed.
    // Ideally use EvoLoopApi.request but it's private/protected maybe?

    // Quick workaround: Use fetch with same base logic as SDK
    // But `ProjectsService` uses `OpenAPI.BASE`...

    // Let's try to assume `/api/v1` is proxied or available.
    // Or better: Use `ProjectsService` if we could (but we can't efficiently regen right now).

    // Fallback: use fetch against the backend URL.
    try {
        const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/projects/${projectId}/status`, {
            headers
        })
        if (response.ok) {
            return await response.json()
        }
    } catch (e) {
        // ignore
    }
    return null
}

export function useProjectStatus() {
    const { currentProject, updateProjectStatus } = useProjectStore()
    const pollTimerRef = useRef<NodeJS.Timeout | null>(null)

    useEffect(() => {
        if (!currentProject) return

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
    }, [currentProject?.id])
}
