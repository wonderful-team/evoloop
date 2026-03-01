import { create } from "zustand"
import { ProjectsService } from "@/client"

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

  fetchDetected: () => Promise<void>
  fetchIgnored: () => Promise<void>
  importProject: (id: number) => Promise<void>
  ignoreProject: (id: number) => Promise<void>
  unignoreProject: (id: number) => Promise<void>
  clearNewDetectedFlag: () => void

  batchImportProjects: (ids: number[]) => Promise<{ success: number; failed: number }>
  batchIgnoreProjects: (ids: number[]) => Promise<{ success: number; failed: number }>
}

export const useProjectImportStore = create<ProjectImportState>((set, get) => ({
  detectedProjects: [],
  ignoredProjects: [],
  isLoading: false,
  hasNewDetected: false,

  fetchDetected: async () => {
    try {
      // Use ProjectsService.getDetectedProjects() which uses generated SDK
      const res: any = await ProjectsService.getDetectedProjects()

      const items = (res.items || []).map((item: any) => ({
        ...item,
        detected_at: item.detected_at ? new Date(item.detected_at).getTime() : 0,
      }))

      set({
        detectedProjects: items,
        hasNewDetected: items.length > 0,
      })
    } catch (error) {
      console.error("Failed to fetch detected projects:", error)
      set({ detectedProjects: [], hasNewDetected: false })
    }
  },

  fetchIgnored: async () => {
    try {
      const res: any = await ProjectsService.getIgnoredProjects()

      const items = (res.items || []).map((item: any) => ({
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
      await get().fetchDetected()

      // @ts-ignore - accessing other store
      await window.__PROJECT_STORE__?.fetchProjects?.()
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
      await get().fetchDetected()
      await get().fetchIgnored()
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

  batchImportProjects: async (ids: number[]) => {
    set({ isLoading: true })
    try {
      const res: any = await ProjectsService.batchImportProjects({
        requestBody: { repo_ids: ids },
      })

      await get().fetchDetected()

      // @ts-ignore - accessing other store
      await window.__PROJECT_STORE__?.fetchProjects?.()

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
