import { create } from 'zustand'
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
            const resp: any = await ProjectsService.listProjects()

            // Handle the new response structure
            // expected: { code: 0, message: "...", data: { list: [...] } }
            // fallback to older check if needed, but primarily support new one

            let rawList: any[] = []
            if (resp.data && Array.isArray(resp.data.list)) {
                rawList = resp.data.list
            } else if (resp.projects) {
                // Fallback for old API if it still exists locally in some form
                rawList = resp.projects
            } else if (Array.isArray(resp)) {
                // Another fallback
                rawList = resp
            }

            const list: Project[] = rawList.map((item: any) => ({
                ...item,
                // Map to compatibility fields
                id: item.project_id || item.id,
                name: item.project_name || item.title || item.name,
                description: item.project_desc || item.description || '',
                path: item.external_path || item.path || '',
            }))

            set({ projects: list, isLoading: false })

            // Auto-select first project if none selected
            // Try to match by ID if we have a current one (to keep selection on refresh)
            const current = get().currentProject
            if (current) {
                const found = list.find(p => p.id === current.id)
                if (found) {
                    set({ currentProject: found })
                } else if (list.length > 0) {
                    // If current project disappeared, maybe select first? 
                    // Or keep it null? Let's select first to be safe
                    set({ currentProject: list[0] })
                }
            } else if (list.length > 0) {
                set({ currentProject: list[0] })
            }
        } catch (error) {
            console.error('Failed to fetch projects', error)
            set({ isLoading: false })
        }
    },

    setProject: (project) => {
        set({ currentProject: project })
    },

    getProject: (id) => {
        return get().projects.find((p) => p.id === id)
    }
}))
