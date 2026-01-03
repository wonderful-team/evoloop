import { create } from 'zustand'
import { EvoLoopApi } from '@/client/evoloopClient'
import { ProjectsService } from '@/client'

export interface TaskStats {
    total: number
    pending: number
    in_progress: number
    completed: number
    overdue: number
    high_priority: number
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
    indexing_status?: string
}

interface ProjectState {
    projects: Project[]
    currentProject: Project | null
    isLoading: boolean

    fetchProjects: () => Promise<void>
    setProject: (project: Project) => void
    getProject: (id: number) => Project | undefined
}

export const useProjectStore = create<ProjectState>((set, get) => ({
    projects: [],
    currentProject: null,
    isLoading: false,

    fetchProjects: async () => {
        set({ isLoading: true })
        try {
            const token = localStorage.getItem('access_token')
            let rawList: any[] = []

            if (token) {
                // Logged In: Fetch from Cloud (synced list)
                const resp: any = await EvoLoopApi.getCloudProjects({ page: 1, page_size: 100 })
                // Normalize Cloud Response
                if (resp && Array.isArray(resp.list)) {
                    rawList = resp.list
                } else if (resp && Array.isArray(resp.data?.list)) {
                    rawList = resp.data.list
                } else if (Array.isArray(resp)) {
                    rawList = resp
                }
            } else {
                // Guest / Not Logged In: Scan Local Folders
                const resp: any = await ProjectsService.listProjects()
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
                id: item.project_id || item.id,
                name: item.project_name || item.title || item.name,
                description: item.project_desc || item.description || '',
                path: item.external_path || item.path || '',
                indexing_status: item.indexing_status || 'unknown'
            }))

            set({ projects: list, isLoading: false })

            // Auto-select logic
            const current = get().currentProject
            if (current) {
                const found = list.find(p => p.id === current.id)
                if (found) {
                    set({ currentProject: found })
                } else if (list.length > 0) {
                    set({ currentProject: list[0] })
                }
            } else if (list.length > 0) {
                set({ currentProject: list[0] })
            }
        } catch (error) {
            console.error('Failed to fetch projects', error)
            set({ projects: [], isLoading: false })
        }
    },

    setProject: (project) => {
        set({ currentProject: project })
    },

    getProject: (id) => {
        return get().projects.find((p) => p.id === id)
    }
}))
