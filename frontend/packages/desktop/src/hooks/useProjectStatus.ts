import { useEffect } from "react"
import { ProjectsService } from "@/client/sdk.gen"
import { isLoggedIn } from "@/hooks/useAuth"
import { useSystemEvent } from "@/hooks/useSystemEvent"
import { isGlobalProject, useProjectStore } from "@/stores/projectStore"

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

  useEffect(() => {
    if (!isLoggedIn()) return
    if (!currentProject) return
    if (isGlobalProject(currentProject)) return

    const projectId = currentProject.id

    // Initial fetch for full status (including summarization and wiki)
    fetchStatus(projectId).then((data) => {
      if (data) {
        const updates: any = {}
        if (data.indexing) {
          updates.indexing_status = data.indexing.status
        }
        if (data.summarization) {
          updates.summarization_status = data.summarization.status
        }
        if (data.wiki) {
          updates.wiki_status = data.wiki.status
        }
        updateProjectStatus(projectId, updates)
      }
    })
  }, [currentProject?.id, updateProjectStatus])

  useSystemEvent("indexing.status", (event) => {
    if (!currentProject) return
    if (isGlobalProject(currentProject)) return

    const matchesProject = event.data.project_id === currentProject.id
    // Backend now emits repo-level events; trust project_id match or fall back
    // to repo_id if the active project carries it in the future.
    const matchesRepo =
      event.data.repo_id !== undefined &&
      (currentProject as any).repo_id === event.data.repo_id

    if (!matchesProject && !matchesRepo) return

    updateProjectStatus(currentProject.id, {
      indexing_status: event.data.status,
    })
  })
}
