import { create } from 'zustand'

interface MobileState {
    currentProject: any | null
    setCurrentProject: (project: any | null) => void
    isProjectInitialized: boolean
    setProjectInitialized: (initialized: boolean) => void
}

export const useMobileStore = create<MobileState>((set) => ({
    currentProject: null,
    setCurrentProject: (project) => set({ currentProject: project }),
    isProjectInitialized: false,
    setProjectInitialized: (initialized) => set({ isProjectInitialized: initialized }),
}))
