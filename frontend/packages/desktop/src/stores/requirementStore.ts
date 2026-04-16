import { create } from "zustand"
import { toast } from "sonner"
import i18n from "@evoloop/shared/i18n"
import { ProjectRequirementsService } from "@/client"

export interface RequirementDocument {
  id: string
  file_name: string
  file_type: string
  file_size: number
  status: "pending" | "analyzed" | "confirmed" | "breakdown_completed"
  created_at: number
  updated_at: number
  analysis_count: number
}

export interface AnalysisResult {
  id: string
  status: "draft" | "pending_confirmation" | "confirmed" | "breakdown_completed"
  version: number
  data: {
    title?: string
    summary?: string
    functional_requirements?: Array<{
      id: string
      description: string
      priority: string
      category: string
      acceptance_criteria: string[]
    }>
    non_functional_requirements?: Array<{
      id: string
      description: string
      type: string
    }>
    user_stories?: Array<{
      id: string
      role: string
      action: string
      benefit: string
      acceptance_criteria: string[]
    }>
    technical_suggestions?: Array<{
      area: string
      suggestion: string
      rationale: string
    }>
    risks?: Array<{
      description: string
      impact: string
      mitigation: string
    }>
    dependencies?: string[]
  }
  user_edited: boolean
  confirmed_at: number | null
  created_at: number
  tasks_count: number
  synced_tasks: number
}

export interface RequirementTask {
  id: string
  title: string
  description: string
  priority: string
  estimated_hours: number
  category: string
  tags: string[]
  requirement_refs: string[]
  acceptance_criteria: string[]
  sync_status: "pending" | "syncing" | "synced" | "failed"
  sync_error: string | null
  evocloud_task_id: number | null
  synced_at: number | null
  created_at: number
}

export interface AnalysisTasksResult {
  analysis_id: string
  document_id: string
  project_id: number
  sync_stats: {
    pending: number
    syncing: number
    synced: number
    failed: number
    total: number
  }
  tasks: RequirementTask[]
  requirement_mapping: {
    by_requirement: Record<string, string[]>
    by_task: Record<string, string[]>
    unmapped_tasks: string[]
  }
}

export interface SyncProgress {
  analysis_id: string
  progress: {
    total: number
    synced: number
    failed: number
    syncing: number
    pending: number
    percentage: number
    is_complete: boolean
    has_failures: boolean
  }
  last_updated: number | null
}

export interface DocumentDetail extends RequirementDocument {
  raw_content_preview?: string
  analyses: AnalysisResult[]
}

interface RequirementState {
  documents: RequirementDocument[]
  isLoading: boolean
  isUploading: boolean
  currentDocument: DocumentDetail | null
  isLoadingDetail: boolean
  currentTasks: AnalysisTasksResult | null
  syncProgress: SyncProgress | null
  isLoadingTasks: boolean

  fetchDocuments: (projectId: number) => Promise<void>
  uploadDocument: (projectId: number, file: File) => Promise<string | null>
  fetchDocumentDetail: (projectId: number, docId: string) => Promise<void>
  deleteDocument: (projectId: number, docId: string) => Promise<void>
  confirmAnalysis: (
    projectId: number,
    docId: string,
    analysisId: string,
    modifications?: Partial<AnalysisResult["data"]>
  ) => Promise<boolean>
  requestAnalysisChanges: (
    projectId: number,
    docId: string,
    analysisId: string,
    feedback: string
  ) => Promise<boolean>
  fetchAnalysisTasks: (
    projectId: number,
    docId: string,
    analysisId: string
  ) => Promise<void>
  fetchSyncProgress: (
    projectId: number,
    docId: string,
    analysisId: string
  ) => Promise<void>
  formatFileSize: (bytes: number) => string
  getStatusText: (status: string) => string
  getStatusColor: (status: string) => string
  getTaskSyncStatusColor: (status: string) => string
}

export const useRequirementStore = create<RequirementState>((set, get) => ({
  documents: [],
  isLoading: false,
  isUploading: false,
  currentDocument: null,
  isLoadingDetail: false,
  currentTasks: null,
  syncProgress: null,
  isLoadingTasks: false,

  fetchDocuments: async (projectId: number) => {
    set({ isLoading: true })
    try {
      const resp: any = await ProjectRequirementsService.listProjectRequirements({ projectId })

      const items = (resp.data || []).map((item: any) => ({
        ...item,
        created_at: item.created_at ? new Date(item.created_at).getTime() : 0,
        updated_at: item.updated_at ? new Date(item.updated_at).getTime() : 0,
      }))

      set({ documents: items })
    } catch (error) {
      console.error("Failed to fetch requirement documents:", error)
      toast.error(i18n.t("requirements.toast.fetchError"))
    } finally {
      set({ isLoading: false })
    }
  },

  uploadDocument: async (projectId: number, file: File) => {
    set({ isUploading: true })
    try {
      const data: any = await ProjectRequirementsService.uploadRequirementDocument({
        projectId,
        formData: { file },
      })

      toast.success(i18n.t("requirements.toast.uploadSuccess"))
      await get().fetchDocuments(projectId)

      return data.thread_id
    } catch (error) {
      console.error("Failed to upload document:", error)
      toast.error(i18n.t("requirements.toast.uploadError"))
      return null
    } finally {
      set({ isUploading: false })
    }
  },

  fetchDocumentDetail: async (projectId: number, docId: string) => {
    set({ isLoadingDetail: true })
    try {
      const data: any = await ProjectRequirementsService.getRequirementDetail({
        projectId,
        docId,
      })

      const mappedDetail: DocumentDetail = {
        ...data,
        created_at: data.created_at ? new Date(data.created_at).getTime() : 0,
        updated_at: data.updated_at ? new Date(data.updated_at).getTime() : 0,
        analyses: (data.analyses || []).map((a: any) => ({
          ...a,
          confirmed_at: a.confirmed_at ? new Date(a.confirmed_at).getTime() : null,
        })),
      }

      set({ currentDocument: mappedDetail })
    } catch (error) {
      console.error("Failed to fetch document detail:", error)
      toast.error(i18n.t("requirements.toast.fetchDetailError"))
    } finally {
      set({ isLoadingDetail: false })
    }
  },

  deleteDocument: async (projectId: number, docId: string) => {
    try {
      await ProjectRequirementsService.deleteRequirementDocument({
        projectId,
        docId,
      })

      toast.success(i18n.t("requirements.toast.deleteSuccess"))
      await get().fetchDocuments(projectId)

      if (get().currentDocument?.id === docId) {
        set({ currentDocument: null })
      }
    } catch (error) {
      console.error("Failed to delete document:", error)
      toast.error(i18n.t("requirements.toast.deleteError"))
    }
  },

  confirmAnalysis: async (
    projectId: number,
    docId: string,
    analysisId: string,
    modifications?: Partial<AnalysisResult["data"]>
  ) => {
    try {
      // NOTE: These specific endpoints (/confirm, /feedback) are missing from the backend routes
      // but were present in the original manual fetch implementation. 
      // Keep as manual fetch for now or replace if/when added to SDK.
      const res = await fetch(
        `/api/v1/projects/${projectId}/requirements/${docId}/analyses/${analysisId}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ modifications }),
        }
      )
      if (!res.ok) throw new Error("Failed to confirm analysis")

      toast.success(i18n.t("requirements.toast.confirmSuccess"))
      await get().fetchDocumentDetail(projectId, docId)
      return true
    } catch (error) {
      console.error("Failed to confirm analysis:", error)
      toast.error(i18n.t("requirements.toast.confirmError"))
      return false
    }
  },

  requestAnalysisChanges: async (
    projectId: number,
    docId: string,
    analysisId: string,
    feedback: string
  ) => {
    try {
      const res = await fetch(
        `/api/v1/projects/${projectId}/requirements/${docId}/analyses/${analysisId}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback }),
        }
      )
      if (!res.ok) throw new Error("Failed to submit feedback")

      toast.success(i18n.t("requirements.toast.feedbackSuccess"))
      return true
    } catch (error) {
      console.error("Failed to submit feedback:", error)
      toast.error(i18n.t("requirements.toast.feedbackError"))
      return false
    }
  },

  fetchAnalysisTasks: async (
    projectId: number,
    docId: string,
    analysisId: string
  ) => {
    set({ isLoadingTasks: true })
    try {
      const data: any = await ProjectRequirementsService.getAnalysisTasks({
        projectId,
        docId,
        analysisId,
      })

      const mappedTasks: AnalysisTasksResult = {
        ...data,
        tasks: (data.tasks || []).map((t: any) => ({
          ...t,
          created_at: t.created_at ? new Date(t.created_at).getTime() : 0,
          synced_at: t.synced_at ? new Date(t.synced_at).getTime() : null,
        })),
      }

      set({ currentTasks: mappedTasks })
    } catch (error) {
      console.error("Failed to fetch analysis tasks:", error)
      toast.error(i18n.t("requirements.toast.fetchTasksError"))
    } finally {
      set({ isLoadingTasks: false })
    }
  },

  fetchSyncProgress: async (
    projectId: number,
    docId: string,
    analysisId: string
  ) => {
    try {
      const data: any = await ProjectRequirementsService.getAnalysisSyncProgress({
        projectId,
        docId,
        analysisId,
      })

      const mappedProgress: SyncProgress = {
        ...data,
        last_updated: data.last_updated ? new Date(data.last_updated).getTime() : null,
      }

      set({ syncProgress: mappedProgress })
    } catch (error) {
      console.error("Failed to fetch sync progress:", error)
    }
  },

  formatFileSize: (bytes: number) => {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
  },

  getStatusText: (status: string) => {
    const statusMap: Record<string, string> = {
      pending: i18n.t("requirements.status.pending"),
      analyzed: i18n.t("requirements.status.analyzed"),
      confirmed: i18n.t("requirements.status.confirmed"),
      breakdown_completed: i18n.t("requirements.status.breakdown_completed"),
    }
    return statusMap[status] || status
  },

  getStatusColor: (status: string) => {
    const colorMap: Record<string, string> = {
      pending: "bg-yellow-100 text-yellow-800",
      analyzed: "bg-blue-100 text-blue-800",
      confirmed: "bg-green-100 text-green-800",
      breakdown_completed: "bg-purple-100 text-purple-800",
    }
    return colorMap[status] || "bg-gray-100 text-gray-800"
  },

  getTaskSyncStatusColor: (status: string) => {
    const colorMap: Record<string, string> = {
      pending: "bg-gray-100 text-gray-600",
      syncing: "bg-blue-100 text-blue-600 animate-pulse",
      synced: "bg-green-100 text-green-600",
      failed: "bg-red-100 text-red-600",
    }
    return colorMap[status] || "bg-gray-100 text-gray-600"
  },
}))
