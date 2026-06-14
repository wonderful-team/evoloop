import type { Message } from "@/components/Chat/ChatMessageItem"

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
    skillIds: number[]
    sessionGoal: string | null
    messages: Message[]

    // Pagination State
    hasMoreHistory: boolean
    isLoadingHistory: boolean
    firstMessageId: number | string | null
    totalMessageCount: number | null

    // Model Selection
    selectedModel: string | null

    // Throttling Logic
    _streamBuffer: string
    _thinkingBuffer: string
    _flushTimeout: any

    // --- Actions ---
    setThread: (threadId: string | null, projectId: number | null, skillIds?: number[]) => Promise<void>
    fetchHistory: (threadId: string) => Promise<void>
    fetchActivity: (threadId: string) => Promise<void>
    loadMoreHistory: () => Promise<void>
    sendMessage: (content: string, pickedFiles?: any[], skillIds?: number[]) => Promise<void>
    clearContent: () => void
    setSelectedModel: (model: string | null) => void
    rewindToMessage: (messageId: string) => Promise<void>
    optimisticTruncate: (messageId: string | number) => Message[]
    restoreSnapshot: (snapshot: Message[]) => void

    // Internal Handlers
    _appendToken: (tokens: string, messageId?: string) => void
    _appendThinking: (text: string, messageId?: string) => void
    _appendMessage: (msg: any) => void
    _truncateMessages: (index: number) => void
    _handleRunStart: (ev: any) => void
    _finalizeMessages: () => void
    _clearHumanRequest: () => void
    _attachHumanRequestToLastMessage: (req: any) => void
}
