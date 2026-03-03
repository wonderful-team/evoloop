import { create } from "zustand"
import { ProjectsService } from "@/client"

export interface TaskStats {
  total: number
  pending: number
  in_progress: number
  completed: number
  overdue: number
  high_priority: number
}

// Virtual Global Project constant for global mode
export const GLOBAL_PROJECT: Project = {
  id: 0,
  name: "global",
  description: "Cross-project conversations and general Q&A",
  path: "",
  project_id: 0,
  project_name: "global",
  project_desc: "Cross-project conversations and general Q&A",
  owner_member_id: 0,
  owner_member_name: "",
  status: 1,
  priority: 0,
  start_time: 0,
  expected_end_time: 0,
  actual_end_time: 0,
  create_time: Date.now(),
  update_time: Date.now(),
  external_source: "",
  external_id: "",
  external_path: "",
  last_sync_time: 0,
  member_count: 0,
  task_stats: {
    total: 0,
    pending: 0,
    in_progress: 0,
    completed: 0,
    overdue: 0,
    high_priority: 0,
  },
  create_time_format: "",
  start_time_format: "",
  update_time_format: "",
  last_sync_time_format: "",
  status_text: "global",
  priority_text: "",
  has_wiki: false,
  last_indexed_at: null,
  // Mark as global project
  isGlobal: true,
  // Local state - global project is always synced/exists
  local_status: "SYNCED",
  exists_locally: true,
  // Indexing status - global mode doesn't need indexing
  indexing_status: "not_needed",
  db_indexing_status: "not_needed",
}

// Helper function to check if a project is the global project
export const isGlobalProject = (project: Project | null): boolean => {
  return project?.id === 0 || project?.isGlobal === true
}

export interface Project {
  // Adapter fields for compatibility
  id: number
  name: string
  description: string
  path: string

  // Raw fields from API
  project_id: number
  project_name: string
  project_desc: string
  owner_member_id: number
  owner_member_name: string
  status: number
  priority: number
  start_time: number
  expected_end_time: number
  actual_end_time: number
  create_time: number
  update_time: number
  external_source: string
  external_id: string
  external_path: string
  last_sync_time: number
  member_count: number
  task_stats: TaskStats
  create_time_format: string
  start_time_format: string
  update_time_format: string
  last_sync_time_format: string
  status_text: string
  priority_text: string
  indexing_status?: string      // Redis real-time status (idle, running, etc.)
  db_indexing_status?: string   // DB persisted status (pending, in_progress, completed, failed, not_needed)
  summarization_status?: string
  wiki_status?: string
  has_wiki?: boolean
  local_status?: string | null  // SYNCED, PENDING_CREATION, DISCONNECTED, etc.
  exists_locally?: boolean      // Whether the project exists on local filesystem
  last_indexed_at?: string | null // ISO timestamp of last successful indexing
  isGlobal?: boolean            // Flag to identify virtual global project
}

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  isLoading: boolean
  isGlobalMode: boolean

  fetchProjects: (filterType?: 'switchable' | 'cloud_only' | 'disconnected') => Promise<void>
  setProject: (project: Project) => void
  setGlobalMode: (enabled: boolean) => void
  getProject: (id: number) => Project | undefined
  updateProjectStatus: (id: number, statusUpdates: Partial<Project>) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  isGlobalMode: false,

  fetchProjects: async (filterType?: 'switchable' | 'cloud_only' | 'disconnected') => {
    set({ isLoading: true })
    try {
      const token = localStorage.getItem("access_token")
      let rawList: any[] = []

      if (token) {
        // Logged In: Fetch from Cloud (synced list)
        // Use OpenAPI client which handles token automatically via OpenAPI.TOKEN
        const resp: any = await ProjectsService.getProjects({ filterType })

        // Normalize Cloud Response (ProjectsListProjectsResponse)
        // The generated type says 'unknown', but usually it's list of projects or { list: [] }
        // Based on backend: returns List[Project] directly or paginated?
        // Backend /api/v1/projects return list[Project] usually?
        // Let's assume it returns { list: [...] } or [...]
        // The legacy getCloudProjects assumed { list: ... } or { data: { list: ... } }

        // We'll keep the robust normalization
        if (resp && Array.isArray(resp.list)) {
          rawList = resp.list
        } else if (resp && Array.isArray(resp.data?.list)) {
          rawList = resp.data.list
        } else if (resp && Array.isArray(resp.projects)) {
          rawList = resp.projects
        } else if (Array.isArray(resp)) {
          rawList = resp
        }
      } else {
        // Guest / Not Logged In: Scan Local Folders
        const resp: any = await ProjectsService.getProjects()
        // Normalize Local Response ({ projects: [...] })
        if (resp.projects && Array.isArray(resp.projects)) {
          rawList = resp.projects
        } else if (Array.isArray(resp)) {
          rawList = resp
        }
      }

      const list: Project[] = rawList.map((item: any) => ({
        ...item,
        // Map to compatibility fields
        id: Number(item.project_id || item.id),
        name: item.project_name || item.title || item.name,
        description: item.project_desc || item.description || "",
        path: item.external_path || item.path || item.local_path || "",
        indexing_status: item.indexing_status || "unknown",
        local_status: item.local_status || null,
        exists_locally: item.exists_locally === true, // Ensure boolean
      }))

      set({ projects: list, isLoading: false })

      // Auto-select logic
      // Filter out disconnected projects (cloud only, no local)
      const localProjects = list.filter((p) => p.exists_locally !== false)
      const current = get().currentProject
      const isGlobal = get().isGlobalMode

      // Check if current project is still valid and not ignored
      const currentInList = current ? list.find((p) => p.id === current.id) : null

      // Preserve global mode - don't auto-switch away from it
      if (isGlobal && current?.id === 0) {
        // Keep global mode, no changes needed
      } else if (current && currentInList) {
        // Current project exists in new list, update it
        set({ currentProject: currentInList })
      } else if (current && !currentInList) {
        // Current project was removed (e.g., ignored) - need to reselect
        console.log(`[ProjectStore] Current project ${current.id} no longer available, reselecting...`)
        if (localProjects.length > 0) {
          set({ currentProject: localProjects[0], isGlobalMode: false })
        } else if (list.length > 0) {
          set({ currentProject: list[0], isGlobalMode: false })
        } else {
          set({ currentProject: null, isGlobalMode: false })
        }
      } else if (localProjects.length > 0) {
        // No current project - prefer locally existing projects
        set({ currentProject: localProjects[0] })
      } else if (list.length > 0) {
        // Fallback: select first even if disconnected
        set({ currentProject: list[0] })
      } else {
        set({ currentProject: null })
      }
    } catch (error) {
      console.error("Failed to fetch projects", error)
      set({ projects: [], isLoading: false })
    }
  },

  setProject: (project) => {
    set({
      currentProject: project,
      isGlobalMode: isGlobalProject(project)
    })
  },

  setGlobalMode: (enabled) => {
    if (enabled) {
      set({
        currentProject: GLOBAL_PROJECT,
        isGlobalMode: true
      })
    } else {
      // Exit global mode, try to select first available local project
      const { projects } = get()
      const localProjects = projects.filter((p) => p.exists_locally !== false)
      if (localProjects.length > 0) {
        set({
          currentProject: localProjects[0],
          isGlobalMode: false
        })
      } else {
        set({
          currentProject: null,
          isGlobalMode: false
        })
      }
    }
  },

  getProject: (id) => {
    return get().projects.find((p) => p.id === id)
  },

  updateProjectStatus: (id, statusUpdates) => {
    set((state) => {
      const newProjects = state.projects.map((p) =>
        p.id === id ? { ...p, ...statusUpdates } : p,
      )

      // Also update current if matches
      const newCurrent =
        state.currentProject?.id === id
          ? { ...state.currentProject, ...statusUpdates }
          : state.currentProject

      return {
        projects: newProjects,
        currentProject: newCurrent,
      }
    })
  },
}))
