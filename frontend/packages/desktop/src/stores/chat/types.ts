import type { Message } from "@/components/Chat/ChatMessageItem"

export interface ChangesetFile {
    path: string
    operation: 'ADD' | 'EDIT' | 'DELETE'
    diff?: string
    timestamp: string
}

export interface ActivitySnapshot {
    status: string
    main_goal: string
    updated_at: number
    running_tools_count: number
    artifacts: any[]
    agent_state: any
    active_memories: any[]
    human_request: any | null
    final_outcome: string
}

export interface ChatState {
    // --- Data ---
    threadId: string | null
    projectId: number | null
    skillId: number | null
    sessionGoal: string | null
    messages: Message[]

    // Changeset State
    changeset: ChangesetFile[]
    viewedChanges: Set<string>
    changesetLastUpdated: string | null

    // Pagination State
    hasMoreHistory: boolean
    isLoadingHistory: boolean
    firstMessageId: number | string | null
    totalMessageCount: number | null

    // Activity State
    status:
    | "idle"
    | "running"
    | "error"
    | "stopped"
    | "interrupted"
    | "summarizing"
    | "indexing"
    | "quota_exhausted"
    | "unauthorized"
    | "unknown"
    
    finalOutcome: string | null
    activeMemories: Array<{ id: string; name: string }>
    artifacts: Array<{ id: number; name: string; type: string; status: string; path?: string }>
    humanRequest: any | null
    quotaExhaustedInfo: {
        title: string
        message: string
        hint: string
        actionText: string
    } | null
    agentState: { mode: string; task_name: string; task_status: string; details?: any } | null

    // --- Live Buffer (For Right Panel) ---
    streamingThinking: string
    streamingSteps: any[]

    isConnected: boolean
    connectionStatus: string

    // Model Selection
    selectedModel: string | null

    // Throttling Logic
    _streamBuffer: string
    _flushTimeout: any

    // --- Actions ---
    setThread: (threadId: string | null, projectId: number, skillId?: number) => Promise<void>
    fetchHistory: (threadId: string) => Promise<void>
    fetchActivity: (threadId: string) => Promise<void>
    loadMoreHistory: () => Promise<void>
    sendMessage: (content: string, attachments?: any[], skillId?: number) => Promise<void>
    stopAgent: () => Promise<void>
    resumeAgent: (userInput?: string) => Promise<void>
    cancelHumanRequest: (reason?: string) => Promise<void>
    clearContent: () => void
    setSelectedModel: (model: string | null) => void
    fetchChangeset: () => Promise<void>
    rewindToMessage: (messageId: string) => Promise<void>

    // Changeset Actions
    setChangeset: (files: ChangesetFile[]) => void
    addToChangeset: (file: ChangesetFile) => void
    markChangeAsViewed: (path: string) => void
    markAllChangesAsViewed: () => void
    clearChangeset: () => void
    loadViewedChanges: (threadId: string) => void

    // Internal Handlers
    _setConnectionStatus: (connected: boolean, status: string) => void
    _appendToken: (tokens: string) => void
    _appendThinking: (text: string) => void
    _setActivitySnapshot: (snapshot: any) => void
    _addArtifact: (artifact: any) => void
    _updateStatus: (status: any) => void
    _setHumanRequest: (request: any) => void
    _setQuotaExhausted: (info: { title: string; message: string; hint: string; actionText: string }) => void
    _setLLMAuthError: (ev: any) => void
    _appendMessage: (msg: any) => void
    _updateProgress: (ev: any) => void
    _setAgentState: (ev: any) => void
    _truncateMessages: (index: number) => void
    _handleRunStart: (ev: any) => void
    _handleRunEnd: (ev: any) => void
    _setError: (error: string) => void
}
