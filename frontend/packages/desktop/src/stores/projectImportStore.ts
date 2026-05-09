import { create } from "zustand"
import { ProjectsService, SystemService } from "@/client"
import { useProjectStore } from "./projectStore"

export interface DetectedProject {
  id: number
  name: string
  path: string
  detected_at: number
}

interface ProjectImportState {
  detectedProjects: DetectedProject[]
  ignoredProjects: DetectedProject[]
  isLoading: boolean
  hasNewDetected: boolean
  isManualMode: boolean // Whether the user manually triggered the import dialog
  dismissedProjectIds: Set<number> // 用户已处理（忽略/稍后）的项目ID
  isDiscoveryEnabled: boolean | null // 项目发现是否启用（null = 尚未检查）

  fetchDetected: (force?: boolean) => Promise<void>
  scanProjects: () => Promise<void>
  fetchIgnored: () => Promise<void>
  checkDiscoveryEnabled: () => Promise<boolean>
  importProject: (id: number) => Promise<void>
  ignoreProject: (id: number) => Promise<void>
  unignoreProject: (id: number) => Promise<void>
  clearNewDetectedFlag: () => void
  setManualMode: (enabled: boolean) => void
  dismissProject: (id: number) => void // 标记单个项目为已处理
  dismissAllProjects: () => void // 标记所有当前项目为已处理
  dismissAllAndResetManual: () => void // 标记所有项目为已处理并重置手动模式（一次性原子操作）

  batchImportProjects: (ids: number[]) => Promise<{ success: number; failed: number }>
  batchIgnoreProjects: (ids: number[]) => Promise<{ success: number; failed: number }>
}

export const useProjectImportStore = create<ProjectImportState>((set, get) => ({
  detectedProjects: [],
  ignoredProjects: [],
  isLoading: false,
  hasNewDetected: false,
  isManualMode: false,
  dismissedProjectIds: new Set<number>(),
  isDiscoveryEnabled: null,

  checkDiscoveryEnabled: async () => {
    try {
      const res = await SystemService.getProjectDiscoveryConfig()
      const enabled = res.enabled ?? true
      set({ isDiscoveryEnabled: enabled })
      return enabled
    } catch (error) {
      console.error("[ProjectImport] Failed to check discovery config:", error)
      // Default to true on error to maintain backward compatibility
      set({ isDiscoveryEnabled: true })
      return true
    }
  },

  scanProjects: async () => {
    set({ isLoading: true })
    try {
      const res = await ProjectsService.scanWorkspaceProjectsEndpoint()
      const items = (res.data || []).map((item: any) => ({
        ...item,
        detected_at: item.detected_at ? new Date(item.detected_at).getTime() : 0,
      }))

      set({
        detectedProjects: items,
        hasNewDetected: items.length > 0,
        isManualMode: items.length > 0,
        dismissedProjectIds: new Set<number>(), // 主动扫描时重置 dismissed 记录
      })
    } catch (error) {
      console.error("[ProjectImport] Failed to scan projects:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchDetected: async (force: boolean = false) => {
    // Check discovery config first (if not already checked)
    let { isDiscoveryEnabled } = get()
    if (isDiscoveryEnabled === null) {
      isDiscoveryEnabled = await get().checkDiscoveryEnabled()
    }
    
    // Skip fetching if discovery is disabled, unless forced
    if (!isDiscoveryEnabled && !force) {
      console.debug("[ProjectImport] Discovery disabled, skipping fetch")
      set({ detectedProjects: [], hasNewDetected: false })
      return
    }

    try {
      // Use ProjectsService.getDetectedProjects() which uses generated SDK
      const res: any = await ProjectsService.getDetectedProjects({ force })

      const items = (res.data || []).map((item: any) => ({
        ...item,
        detected_at: item.detected_at ? new Date(item.detected_at).getTime() : 0,
      }))

      // 检查是否有新的、未处理过的项目
      const { dismissedProjectIds } = get()
      const hasNewUnprocessed = items.some((item: DetectedProject) => !dismissedProjectIds.has(item.id))

      set({
        detectedProjects: items,
        hasNewDetected: hasNewUnprocessed,
      })
    } catch (error: any) {
      // Handle timeout errors gracefully - don't spam console with expected errors
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        console.warn('[ProjectImport] Fetch detected projects timed out, will retry on next poll')
      } else if (error.message?.includes('Network Error') || !navigator.onLine) {
        console.warn('[ProjectImport] Network error, likely offline')
      } else {
        console.error('Failed to fetch detected projects:', error)
      }
      // Keep existing projects on error, don't clear them
      set({ hasNewDetected: false })
    }
  },

  fetchIgnored: async () => {
    try {
      const res: any = await ProjectsService.getIgnoredProjects()

      const items = (res.data || []).map((item: any) => ({
        ...item,
        detected_at: item.detected_at ? new Date(item.detected_at).getTime() : 0,
      }))

      set({ ignoredProjects: items })
    } catch (error) {
      console.error("Failed to fetch ignored projects:", error)
    }
  },

  importProject: async (id: number) => {
    set({ isLoading: true })
    try {
      await ProjectsService.importDetectedProject({ repoId: id })
      await get().fetchDetected(true)
      await useProjectStore.getState().fetchProjects()
    } catch (error) {
      console.error("Failed to import project:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  ignoreProject: async (id: number) => {
    set({ isLoading: true })
    try {
      await ProjectsService.ignoreDetectedProject({ repoId: id })
      await get().fetchDetected(true)
      await get().fetchIgnored()

      // Refresh main project list to remove ignored project
      await useProjectStore.getState().fetchProjects()
    } catch (error) {
      console.error("Failed to ignore project:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  unignoreProject: async (id: number) => {
    set({ isLoading: true })
    try {
      await ProjectsService.unignoreProject({ repoId: id })
      await get().fetchDetected()
      await get().fetchIgnored()

      // Refresh main project list to add restored project
      await useProjectStore.getState().fetchProjects()
    } catch (error) {
      console.error("Failed to unignore project:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  clearNewDetectedFlag: () => {
    set({ hasNewDetected: false })
  },

  setManualMode: (enabled: boolean) => {
    set({ isManualMode: enabled })
  },

  dismissProject: (id: number) => {
    set((state) => {
      const newDismissed = new Set(state.dismissedProjectIds)
      newDismissed.add(id)

      // 检查是否还有未处理的项目
      const hasNewUnprocessed = state.detectedProjects.some(
        (item) => !newDismissed.has(item.id)
      )

      return {
        dismissedProjectIds: newDismissed,
        hasNewDetected: hasNewUnprocessed,
        // 如果最后一个未处理项目被 dismiss，同时退出手动模式
        isManualMode: hasNewUnprocessed ? state.isManualMode : false,
      }
    })
  },

  dismissAllProjects: () => {
    set((state) => {
      const newDismissed = new Set(state.dismissedProjectIds)
      state.detectedProjects.forEach((item) => newDismissed.add(item.id))

      return {
        dismissedProjectIds: newDismissed,
        hasNewDetected: false,
      }
    })
  },

  dismissAllAndResetManual: () => {
    set((state) => {
      const newDismissed = new Set(state.dismissedProjectIds)
      state.detectedProjects.forEach((item) => newDismissed.add(item.id))

      return {
        dismissedProjectIds: newDismissed,
        hasNewDetected: false,
        isManualMode: false,
      }
    })
  },

  batchImportProjects: async (ids: number[]) => {
    set({ isLoading: true })
    try {
      const res: any = await ProjectsService.batchImportProjects({
        requestBody: { repo_ids: ids },
      })

      await get().fetchDetected()

      await useProjectStore.getState().fetchProjects()

      return {
        success: res.results?.success?.length || 0,
        failed: res.results?.failed?.length || 0,
      }
    } catch (error) {
      console.error("Failed to batch import projects:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  batchIgnoreProjects: async (ids: number[]) => {
    set({ isLoading: true })
    try {
      const res: any = await ProjectsService.batchIgnoreProjects({
        requestBody: { repo_ids: ids },
      })

      await get().fetchDetected()
      await get().fetchIgnored()

      // Refresh main project list to remove ignored projects
      await useProjectStore.getState().fetchProjects()

      return {
        success: res.results?.success?.length || 0,
        failed: res.results?.failed?.length || 0,
      }
    } catch (error) {
      console.error("Failed to batch ignore projects:", error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },
}))
