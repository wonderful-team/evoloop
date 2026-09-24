import i18n from "@evoloop/shared/i18n"
import {create} from "zustand"
import {ProjectsService} from "@/client"

// localStorage key for persisting user's project selection
const LAST_PROJECT_ID_KEY = "evoloop_last_project_id"

// Helper to get last selected project ID from localStorage
const getLastSelectedProjectId = (): number | null => {
  try {
    const stored = localStorage.getItem(LAST_PROJECT_ID_KEY)
    // 注意：0 是合法值（0 = 全局工作空间），不能用 if (stored) 的 falsy 判断
    if (stored !== null) {
      const id = parseInt(stored, 10)
      return Number.isNaN(id) ? null : id
    }
  } catch {
    // localStorage might not be available
  }
  return null
}

// Helper to save selected project ID to localStorage
const saveLastSelectedProjectId = (id: number | null) => {
  try {
    if (id !== null) {
      localStorage.setItem(LAST_PROJECT_ID_KEY, String(id))
    } else {
      localStorage.removeItem(LAST_PROJECT_ID_KEY)
    }
  } catch {
    // localStorage might not be available
  }
}

// 把当前项目上报给后端（SharedState.project_id，后端 SSOT + 持久化）。
// 仅在后端当前 project_id 为空（0）时用于初始化回填——此后后端成为权威，
// 前端从后端读。失败不阻断（非致命）。
const syncProjectToBackend = (project: Project | null) => {
  if (!project || project.id == null || project.id === 0) return
  import("@/client")
    .then(({ ProjectsService }) => {
      ProjectsService.switchProject({
        requestBody: {
          project_id: project.id!,
          project_name: project.name || "",
        },
      }).catch(() => {})
    })
    .catch(() => {})
}

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
  description: i18n.t("projects.global.description"),
  path: "",
  project_id: 0,
  project_name: "global",
  project_desc: i18n.t("projects.global.description"),
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
  indexing_status?: string // Redis real-time status (idle, running, etc.)
  db_indexing_status?: string // DB persisted status (pending, in_progress, completed, failed, not_needed)
  summarization_status?: string
  wiki_status?: string
  has_wiki?: boolean
  local_status?: string | null // SYNCED, PENDING_CREATION, DISCONNECTED, etc.
  exists_locally?: boolean // Whether the project exists on local filesystem
  last_indexed_at?: string | null // ISO timestamp of last successful indexing
  files_count?: number // Number of files in the project (optional, from API)
  created_at?: string | null // ISO timestamp of project creation (optional, from API)
  duty_enabled?: boolean // Whether duty monitoring is enabled for this project
  isGlobal?: boolean // Flag to identify virtual global project
}

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  isLoading: boolean
  isGlobalMode: boolean
  projectSwitcherOpen: boolean

  openProjectSwitcher: () => void
  closeProjectSwitcher: () => void

  fetchProjects: (
    filterType?: "switchable" | "cloud_only" | "disconnected",
  ) => Promise<void>
  setProject: (project: Project | null) => void
  setGlobalMode: (enabled: boolean) => void
  getProject: (id: number) => Project | undefined
  updateProjectStatus: (id: number, statusUpdates: Partial<Project>) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  isGlobalMode: false,
  projectSwitcherOpen: false,

  openProjectSwitcher: () => set({ projectSwitcherOpen: true }),
  closeProjectSwitcher: () => set({ projectSwitcherOpen: false }),

  fetchProjects: async (
    filterType?: "switchable" | "cloud_only" | "disconnected",
  ) => {
    set({ isLoading: true })
    try {
      let rawList: any[] = []
      const resp: any = await ProjectsService.getProjects({ filterType })

      if (resp && Array.isArray(resp.list)) {
        rawList = resp.list
      } else if (resp && Array.isArray(resp.data?.list)) {
        rawList = resp.data.list
      } else if (resp && Array.isArray(resp.projects)) {
        rawList = resp.projects
      } else if (Array.isArray(resp)) {
        rawList = resp
      }

      const list: Project[] = rawList.map((item: any) => ({
        ...item,
        id: Number(item.project_id || item.id),
        name: item.project_name || item.title || item.name,
        description: item.project_desc || item.description || "",
        path: item.external_path || item.path || item.local_path || "",
        indexing_status: item.indexing_status || "unknown",
        local_status: item.local_status || null,
        exists_locally: item.exists_locally === true,
        files_count: item.files_count,
        created_at: item.created_at,
      }))

      set({ projects: list, isLoading: false })

      // 真数据源：后端 SharedState.project_id（GET /projects/current）。
      // 后端是 SSOT——前端以此为准决定当前项目，localStorage 仅作缓存。
      // 若后端返回有效 project_id 且在本列表中，用它作为 currentProject。
      let backendPid: number | null = null
      try {
        const curResp: any = await ProjectsService.getCurrentProject()
        const curData =
          curResp?.data || curResp || {}
        const rawPid = curData.project_id ?? curData.projectId
        const pid = Number(rawPid)
        if (!Number.isNaN(pid) && pid > 0) backendPid = pid
      } catch (e) {
        console.error("获取后端当前项目失败（回退本地缓存）:", e)
      }
      const backendInList =
        backendPid != null ? list.find((p) => p.id === backendPid) : null

      const localProjects = list.filter((p) => p.exists_locally !== false)
      const current = get().currentProject
      const isGlobal = get().isGlobalMode
      const currentInList = current
        ? list.find((p) => p.id === current.id)
        : null
      const lastSelectedId = getLastSelectedProjectId()
      const lastSelectedInList =
        lastSelectedId !== null
          ? list.find((p) => p.id === lastSelectedId)
          : null

      if (isGlobal && current?.id === 0) {
        // Keep global mode
      } else if (backendInList) {
        // 后端真数据源优先
        saveLastSelectedProjectId(backendInList.id)
        set({ currentProject: backendInList, isGlobalMode: false })
      } else if (current && current.id === 0) {
        // 会话内全局：GLOBAL_PROJECT 是虚拟项不在 switchable 列表里，
        // 若不在此拦截，会掉进 current && !currentInList 分支被换成第一个本地项目
        saveLastSelectedProjectId(0)
        set({ currentProject: GLOBAL_PROJECT, isGlobalMode: true })
      } else if (current && currentInList) {
        set({ currentProject: currentInList })
        // 后端暂无权威 project_id（0）时，把当前项目回填给后端
        if (backendPid == null || backendPid <= 0) {
          syncProjectToBackend(currentInList)
        }
      } else if (lastSelectedId === 0 && (backendPid == null || backendPid <= 0)) {
        // 用户上次明确选择了全局（localStorage=0），且后端无具体项目权威。
        // GLOBAL_PROJECT 不在 projects 列表中（虚拟项），lastSelectedInList 会落空，
        // 必须在此恢复全局，否则会落到"选第一个本地项目"的兜底分支丢失全局模式。
        saveLastSelectedProjectId(0)
        set({ currentProject: GLOBAL_PROJECT, isGlobalMode: true })
      } else if (lastSelectedInList) {
        set({
          currentProject: lastSelectedInList,
          isGlobalMode: isGlobalProject(lastSelectedInList),
        })
        // 后端暂无权威 project_id（0）时，把本地恢复的项目回填给后端
        if (backendPid == null || backendPid <= 0) {
          syncProjectToBackend(lastSelectedInList)
        }
      } else if (current && !currentInList) {
        if (localProjects.length > 0) {
          const firstLocal = localProjects[0]
          saveLastSelectedProjectId(firstLocal.id)
          set({ currentProject: firstLocal, isGlobalMode: false })
          if (backendPid == null || backendPid <= 0) {
            syncProjectToBackend(firstLocal)
          }
        } else if (list.length > 0) {
          const first = list[0]
          saveLastSelectedProjectId(first.id)
          set({ currentProject: first, isGlobalMode: false })
          if (backendPid == null || backendPid <= 0) {
            syncProjectToBackend(first)
          }
        } else {
          saveLastSelectedProjectId(0)
          set({ currentProject: GLOBAL_PROJECT, isGlobalMode: true })
        }
      } else if (localProjects.length > 0) {
        const firstLocal = localProjects[0]
        saveLastSelectedProjectId(firstLocal.id)
        set({ currentProject: firstLocal, isGlobalMode: false })
        if (backendPid == null || backendPid <= 0) {
          syncProjectToBackend(firstLocal)
        }
      } else if (list.length > 0) {
        const first = list[0]
        saveLastSelectedProjectId(first.id)
        set({ currentProject: first, isGlobalMode: false })
        if (backendPid == null || backendPid <= 0) {
          syncProjectToBackend(first)
        }
      } else {
        saveLastSelectedProjectId(0)
        set({ currentProject: GLOBAL_PROJECT, isGlobalMode: true })
      }
    } catch (error) {
      console.error("Failed to fetch projects", error)
      set({ projects: [], isLoading: false })
    }
  },

  setProject: (project: Project | null) => {
    // Persist selection to localStorage
    saveLastSelectedProjectId(project?.id ?? null)

    set({
      currentProject: project,
      isGlobalMode: isGlobalProject(project),
    })
  },

  setGlobalMode: (enabled) => {
    if (enabled) {
      saveLastSelectedProjectId(0) // Save global mode (id=0)
      set({
        currentProject: GLOBAL_PROJECT,
        isGlobalMode: true,
      })
    } else {
      // Exit global mode, try to select first available local project
      const { projects } = get()
      const localProjects = projects.filter((p) => p.exists_locally !== false)
      if (localProjects.length > 0) {
        const firstLocal = localProjects[0]
        saveLastSelectedProjectId(firstLocal.id)
        set({
          currentProject: firstLocal,
          isGlobalMode: false,
        })
      } else {
        saveLastSelectedProjectId(null)
        set({
          currentProject: null,
          isGlobalMode: false,
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
