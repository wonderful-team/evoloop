interface ChangesetFile {
  path: string
  operation: "ADD" | "EDIT" | "DELETE"
  diff?: string
  timestamp: string
}

export interface ChangesetState {
  // Data
  changeset: ChangesetFile[]
  viewedChanges: Set<string>
  changesetLastUpdated: string | null

  // Actions
  fetchChangeset: (threadId: string) => Promise<void>
  setChangeset: (files: ChangesetFile[], threadId?: string) => void
  addToChangeset: (file: ChangesetFile, threadId?: string) => void
  markChangeAsViewed: (path: string, threadId?: string) => void
  markAllChangesAsViewed: (threadId?: string) => void
  clearChangeset: () => void
  loadViewedChanges: (threadId: string) => void
}
