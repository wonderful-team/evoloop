import { create } from "zustand"
import { ChangesetState } from "./changeset/types"
import { ConversationsService } from "@/client"

export const useChangesetStore = create<ChangesetState>((set) => ({
    // Data
    changeset: [],
    viewedChanges: new Set<string>(),
    changesetLastUpdated: null,

    // Actions
    fetchChangeset: async (threadId) => {
        if (!threadId) return
        try {
            const data = await ConversationsService.getThreadChangeset({ threadId })
            // Flatten the changeset tree if needed, or map nodes to flat list
            const flatten = (node: any, list: any[] = []) => {
                if (node.path && node.operation) list.push(node)
                if (node.children) node.children.forEach((c: any) => flatten(c, list))
                return list
            }
            const files = flatten(data)
            set({ changeset: files, changesetLastUpdated: new Date().toISOString() })
        } catch (e) {
            console.error("[ChangesetStore] Fetch changeset failed", e)
        }
    },

    setChangeset: (files, _threadId) => set({ changeset: files, changesetLastUpdated: new Date().toISOString() }),

    addToChangeset: (file, _threadId) => {
        set((state) => {
            const idx = state.changeset.findIndex(f => f.path === file.path)
            const newCs = idx >= 0 ? [...state.changeset] : [...state.changeset, file]
            if (idx >= 0) newCs[idx] = file
            return { changeset: newCs, changesetLastUpdated: new Date().toISOString() }
        })
    },

    markChangeAsViewed: (path, threadId) => {
        set((state) => {
            const newViewed = new Set(state.viewedChanges).add(path)
            if (threadId) localStorage.setItem(`evoloop:viewed:${threadId}`, JSON.stringify([...newViewed]))
            return { viewedChanges: newViewed }
        })
    },

    markAllChangesAsViewed: (threadId) => {
        set((state) => {
            const allPaths = state.changeset.map(f => f.path)
            const newViewed = new Set(allPaths)
            if (threadId) localStorage.setItem(`evoloop:viewed:${threadId}`, JSON.stringify(allPaths))
            return { viewedChanges: newViewed }
        })
    },

    clearChangeset: () => set({ changeset: [], viewedChanges: new Set(), changesetLastUpdated: null }),

    loadViewedChanges: (threadId) => {
        const saved = localStorage.getItem(`evoloop:viewed:${threadId}`)
        if (saved) {
            try {
                set({ viewedChanges: new Set(JSON.parse(saved)) })
            } catch (e) {
                set({ viewedChanges: new Set() })
            }
        } else {
            set({ viewedChanges: new Set() })
        }
    }
}))
