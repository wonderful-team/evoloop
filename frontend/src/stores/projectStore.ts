import { create } from 'zustand'
import { ProjectsService } from '@/client'

export interface Project {
    id: number
    name: string
    description?: string
    path: string
    status_text?: string
    owner?: string
    created_at?: string
    files_count?: number
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
            const resp = await ProjectsService.listProjects()
            // Adapt backend response structure
            const list = (resp as any)?.projects || []
            set({ projects: list, isLoading: false })

            // Auto-select first project if none selected
            if (!get().currentProject && list.length > 0) {
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
