import { toast } from "sonner"
import { create } from "zustand"
import i18n from "@evoloop/shared/i18n"
import { AgentService, ConversationsService } from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
import type { Message } from "@/components/Chat/ChatMessageItem"
import type { StreamState, StreamEvent } from "@/types/stream"
import { llmPlatformService } from "@/services/llmPlatform"

// Step item type for activity tracking
export interface StepItem {
    id: number
    name: string
    tool?: string              // Original tool identifier (e.g. "search_web")
    status: "running" | "done" | "failed" | "cancelled"
    type: "node" | "tool" | "ai" | "skill"
    parent_id?: number
    time: string
    details?: string
    input?: any  // Tool input parameters (for real-time steps)
    tool_meta?: {
        affected_path_keys?: string[]
        display_name?: string
    }
}

interface ChangesetFile {
    path: string
    operation: 'ADD' | 'EDIT' | 'DELETE'
    diff?: string
    timestamp: string
}

interface ChatState {
    // --- Data ---
    threadId: string | null
    projectId: number | null
    messages: Message[]

    // Changeset State
    changeset: ChangesetFile[]
    viewedChanges: Set<string>  // Set of file paths that have been viewed
    changesetLastUpdated: string | null

    // Pagination State for Infinite Scroll
    hasMoreHistory: boolean      // Whether there are more messages to load
    isLoadingHistory: boolean    // Loading state for pagination
    firstMessageId: number | string | null  // Cursor for loading older messages
    totalMessageCount: number | null  // Total messages in thread (if known)

    // Activity State
    status:
    | "idle"
    | "running"
    | "error"
    | "stopped"
    | "interrupted"
    | "summarizing"
    | "indexing"
    | "quota_exhausted"  // LLM quota exhausted state
    | "unauthorized"     // 401 unauthorized
    | "unknown"
    steps: StepItem[]
    finalOutcome: string | null // Session outcome: SUCCESS | FAILED | INCOMPLETE
    streamedContent: string // The currently streaming token buffer (for the specific AI task)
    activeMemories: Array<{ id: string; name: string }> // Active memory highlights
    artifacts: Array<{ id: number; name: string; type: string; status: string; path?: string }> // Generated artifacts
    humanRequest: any | null // HITL Request (now includes project_switch, confirm, etc.)
    quotaExhaustedInfo: {  // Quota exhausted information
        title: string
        message: string
        hint: string
        actionText: string
    } | null
    agentState: { mode: string; task_name: string; task_status: string; details?: any } | null // Current agent state
    thoughts: any[] // Transient Thoughts history

    // Enhanced Stream State for real-time UI updates
    streamState: StreamState

    isConnected: boolean
    connectionStatus: string

    // Model Selection
    selectedModel: string | null // User selected model for this chat

    // Throttling Logic
    _streamBuffer: string
    _flushTimeout: any

    // --- Actions ---

    // storage/network actions
    setThread: (threadId: string | null, projectId: number) => Promise<void>
    fetchHistory: (threadId: string) => Promise<void>
    loadMoreHistory: () => Promise<void> // Infinite scroll: load older messages
    sendMessage: (content: string, attachments?: any[]) => Promise<void>
    stopAgent: () => Promise<void>
    resumeAgent: (userInput?: string) => Promise<void>
    cancelHumanRequest: (reason?: string) => Promise<void>
    clearContent: () => void
    setSelectedModel: (model: string | null) => void // Set user selected model

    // Changeset Actions
    setChangeset: (files: ChangesetFile[]) => void
    addToChangeset: (file: ChangesetFile) => void
    markChangeAsViewed: (path: string) => void
    markAllChangesAsViewed: () => void
    clearChangeset: () => void
    loadViewedChanges: (threadId: string) => void

    // internal sse handlers (called by ChatConnection)
    _setConnectionStatus: (connected: boolean, status: string) => void
    _appendToken: (tokens: string) => void
    _setActivitySnapshot: (snapshot: any) => void  // Initial full snapshot only
    _addStep: (step: any) => void  // Incremental step update
    _addArtifact: (artifact: any) => void  // Incremental artifact update
    _updateStatus: (status: any) => void  // Incremental status update
    _setHumanRequest: (request: any) => void
    _setQuotaExhausted: (info: { title: string; message: string; hint: string; actionText: string }) => void
    _appendMessage: (msg: any) => void // Append message to chat
    _truncateMessages: (index: number) => void // Optimistic truncate for rewind
    _setError: (error: string) => void
    _processStreamEvent: (event: StreamEvent) => void // Handle structured stream events
}

export const useChatStore = create<ChatState>((set, get) => ({
    threadId: null,
    projectId: null,
    messages: [],

    // Changeset State
    changeset: [],
    viewedChanges: new Set<string>(),
    changesetLastUpdated: null,

    // Pagination State
    hasMoreHistory: true,
    isLoadingHistory: false,
    firstMessageId: null,
    totalMessageCount: null,

    // Model Selection
    selectedModel: llmPlatformService.getSelectedModel(),

    status: "idle",
    steps: [],
    finalOutcome: null,
    streamedContent: "",

    activeMemories: [],
    artifacts: [],
    humanRequest: null,
    quotaExhaustedInfo: null,
    agentState: null,
    thoughts: [],

    // Stream State for real-time updates
    streamState: {
        events: [],
        currentThinking: null,
        currentTool: null,
        overallProgress: 0,
    },

    isConnected: false,
    connectionStatus: "disconnected",

    _streamBuffer: "",
    _flushTimeout: null,

    setThread: async (threadId, projectId) => {
        const currentThreadId = get().threadId

        // 1. Switch Thread Metadata
        set({
            threadId,
            projectId,
            // Only clear UI if switching to a DIFFERENT thread
            ...(currentThreadId !== threadId
                ? {
                    messages: [],
                    steps: [],
                    streamedContent: "",
                    status: "idle",
                    finalOutcome: null,
                    humanRequest: null,
                    changeset: [],
                    viewedChanges: new Set(),
                    changesetLastUpdated: null,
                }
                : {}),
        })

        // Load viewed changes for this thread
        if (threadId) {
            get().loadViewedChanges(threadId)
        }

        // 2. Connect SSE (Persistent)
        const connection = ChatConnection.getInstance()

        // Update Callbacks (to ensure they point to current store instance/state if needed, though 'set' is stable)
        connection.setCallbacks({
            onConnectionChange: (connected: boolean, status: string) =>
                get()._setConnectionStatus(connected, status),
            onToken: (token: string) => get()._appendToken(token),
            onActivity: (snapshot: any) => get()._setActivitySnapshot(snapshot),
            onStep: (step: any) => get()._addStep(step),
            onArtifact: (artifact: any) => get()._addArtifact(artifact),
            onStatus: (status: any) => get()._updateStatus(status),
            onHumanRequest: (req: any) => get()._setHumanRequest(req),
            onMessage: (msg: any) => get()._appendMessage(msg),
            onStream: (event: StreamEvent) => get()._processStreamEvent(event),
            onError: (error: string) => get()._setError(error),
            onUnauthorized: () => {
                // SSE连接401未授权，更新状态并让用户知道需要重新登录
                console.warn("[ChatStore] SSE connection unauthorized");
                set({ 
                    status: "error",
                    isConnected: false,
                    connectionStatus: "unauthorized"
                });
                // 触发全局401处理（通过API错误处理）
                // 这里不直接跳转，让后续的API调用触发统一的401处理
            },
        })

        connection.connect(threadId)

        // 3. Fetch History & Activity only when we have a real threadId
        if (threadId) {
            await get().fetchHistory(threadId)

            // 4. Fetch Initial Activity (to catch up if already running)
            try {
                const activity = (await ConversationsService.getThreadActivity({
                    threadId,
                })) as any
                if (activity) {
                    get()._setActivitySnapshot(activity)
                    // Check for pending request in snapshot too (for page reload scenario)
                    if (activity.human_request) {
                        get()._setHumanRequest(activity.human_request)
                    }
                }
            } catch (_e) {
                // ignore
            }
        }
    },

    fetchHistory: async (threadId) => {
        try {
            // Initial load: fetch latest messages (no cursor)
            const response = (await ConversationsService.getConversationMessages({
                threadId,
                limit: 50,
            })) as any
            
            const rawMessages = response?.data || []
            
            // Format messages
            const formatted: Message[] = rawMessages
                .map((m: any, idx: number) => ({
                    id: m.id || idx,
                    // Normalize role: user->human, assistant->ai
                    role: m.role === "human" || m.role === "user" ? "human" : "ai",
                    originalRole: m.role,
                    content: m.content || "",
                    thinking: m.thinking,
                    timestamp: m.created_at,
                    steps_snapshot: m.steps_snapshot,
                    steps: m.steps || [],
                    references: m.references || [],
                    has_file_operations: m.has_file_operations || false,
                    changeset_count: m.changeset_count || 0,
                }))
                // Filter: only show human/ai messages (tool messages are folded server-side)
                // Accept both "human" and "user" roles for backward compatibility
                .filter((m: any) => m.originalRole === "human" || m.originalRole === "user" || m.originalRole === "ai" || m.originalRole === "assistant")

            // Update state with pagination info
            if (get().threadId === threadId) {
                // Use the first message's ID from the formatted array as firstMessageId
                // (API might not return first_id field)
                const firstMsgId = formatted.length > 0 ? formatted[0].id : null
                console.log('[ChatStore] fetchHistory loaded:', { 
                    count: formatted.length, 
                    firstMsgId, 
                    lastMsgId: formatted.length > 0 ? formatted[formatted.length - 1].id : null,
                    hasMore: response?.has_more 
                })
                set({
                    messages: formatted,
                    hasMoreHistory: response?.has_more ?? false,
                    firstMessageId: firstMsgId,
                    totalMessageCount: response?.total_count ?? null,
                    isLoadingHistory: false,
                })
            }
        } catch (e) {
            console.error("Failed to fetch history", e)
            if (get().messages.length === 0) {
                toast.error(i18n.t("chat.errors.loadHistory"))
            }
        }
    },

    loadMoreHistory: async () => {
        const { threadId, firstMessageId, isLoadingHistory, hasMoreHistory } = get()
        
        console.log('[ChatStore] loadMoreHistory check:', { threadId, firstMessageId, isLoadingHistory, hasMoreHistory })
        
        if (!threadId || isLoadingHistory || !hasMoreHistory || !firstMessageId) {
            console.log('[ChatStore] loadMoreHistory skipped due to:', { noThreadId: !threadId, isLoadingHistory, noHasMoreHistory: !hasMoreHistory, noFirstMessageId: !firstMessageId })
            return
        }
        
        set({ isLoadingHistory: true })
        
        try {
            const response = (await ConversationsService.getConversationMessages({
                threadId,
                limit: 50,
                beforeId: firstMessageId as any, // Cast to avoid type mismatch with generated client
            })) as any
            
            const rawMessages = response?.data || []
            
            if (rawMessages.length === 0) {
                set({ hasMoreHistory: false, isLoadingHistory: false })
                return
            }
            
            // Format new messages
            const formatted: Message[] = rawMessages
                .map((m: any, idx: number) => ({
                    id: m.id || idx,
                    // Normalize role: user->human, assistant->ai
                    role: m.role === "human" || m.role === "user" ? "human" : "ai",
                    originalRole: m.role,
                    content: m.content || "",
                    thinking: m.thinking,
                    timestamp: m.created_at,
                    steps_snapshot: m.steps_snapshot,
                    steps: m.steps || [],
                    references: m.references || [],
                    has_file_operations: m.has_file_operations || false,
                    changeset_count: m.changeset_count || 0,
                }))
                // Filter: only show human/ai messages (tool messages are folded server-side)
                // Accept both "human" and "user" roles for backward compatibility
                .filter((m: any) => m.originalRole === "human" || m.originalRole === "user" || m.originalRole === "ai" || m.originalRole === "assistant")
            
            // Prepend new messages to existing list
            // Update firstMessageId to the first message of the newly loaded batch
            set((state) => {
                const newFirstMsgId = formatted.length > 0 ? formatted[0].id : state.firstMessageId
                console.log('[ChatStore] loadMoreHistory loaded:', { 
                    newCount: formatted.length, 
                    newFirstMsgId, 
                    totalMessages: state.messages.length + formatted.length,
                    hasMore: response?.has_more 
                })
                return {
                    messages: [...formatted, ...state.messages],
                    hasMoreHistory: response?.has_more ?? false,
                    firstMessageId: newFirstMsgId,
                    isLoadingHistory: false,
                }
            })
        } catch (e) {
            console.error("Failed to load more history", e)
            set({ isLoadingHistory: false })
        }
    },

    sendMessage: async (content, attachments: any[] = []) => {
        const { threadId, projectId, selectedModel } = get()
        // Allow projectId to be 0 (global mode), but not null/undefined
        // threadId can be null for new conversations; backend will generate it
        if (projectId === null || projectId === undefined || (!content.trim() && attachments.length === 0)) return

        // 1. Optimistic Update
        const tempId = Date.now()

        // Construct display content for local optimistic UI
        // For voice messages, use the content directly (which is the transcript)
        const displayContent = content

        const newMessage: Message = {
            id: tempId,
            role: "human",
            content: displayContent,
            attachments: attachments.length > 0 ? attachments : undefined,
        }

        set((state) => ({
            messages: [...state.messages, newMessage],
            status: "running", // Assume running immediately
        }))

        // 2. Send Request
        try {
            const res = await AgentService.chatEndpoint({
                requestBody: {
                    message: content, // Send raw text (backend handles merging)
                    thread_id: threadId || undefined,
                    project_id: projectId,
                    attachments: attachments, // Pass structured attachments
                    model: selectedModel, // Pass user selected model
                },
            }) as any

            // If backend generated a new thread_id, switch to it without clearing messages
            if (res && res.thread_id && !threadId) {
                set({ threadId: res.thread_id })
                ChatConnection.getInstance().connect(res.thread_id)
            }

            if (res && res.message_id) {
                set((state) => ({
                    messages: state.messages.map((m) =>
                        m.id === tempId ? { ...m, id: res.message_id } : m
                    ),
                }))
            }
            // Success - we don't need to do anything else, SSE "status: running" will confirm
            // But we keep status running just in case SSE is slow
        } catch (e) {
            console.error(e)
            toast.error(i18n.t("chat.errors.sendMessage"))
            set((state) => ({
                messages: state.messages.filter((m) => m.id !== tempId), // Revert
                status: "error",
            }))
        }
    },

    stopAgent: async () => {
        const { threadId } = get()
        if (!threadId) return

        try {
            await AgentService.stopChat({
                requestBody: { thread_id: threadId, message: "" },
            })
            toast.info(i18n.t("chat.agentStopped"))
            set({ status: "stopped", humanRequest: null })
        } catch (_e) {
            toast.error(i18n.t("chat.errors.stopAgent"))
        }
    },

    resumeAgent: async (userInput?: string) => {
        const { threadId, selectedModel } = get()
        if (!threadId) return

        try {
            await AgentService.resumeChat({
                requestBody: { thread_id: threadId, user_input: userInput, model: selectedModel },
            })
            toast.info(i18n.t("chat.status.resuming"))
            set({ status: "running", humanRequest: null }) // Optimistic clear
        } catch (_e) {
            toast.error(i18n.t("chat.errors.resumeAgent"))
        }
    },

    cancelHumanRequest: async (reason?: string) => {
        const { threadId, selectedModel } = get()
        if (!threadId) return

        // Save previous state for rollback
        const previousStatus = get().status
        const previousHumanRequest = get().humanRequest

        // Optimistic update to idle (consistent with backend clear_human_request)
        set({ status: "idle", humanRequest: null })

        try {
            await AgentService.cancelHitlRequest({
                requestBody: { thread_id: threadId, reason: reason || i18n.t("chat.status.userCancelled"), model: selectedModel },
            })
            toast.info(i18n.t("chat.status.cancelling"))
            
            // Safety timeout: if state is still stuck after 5s, force reset
            setTimeout(() => {
                const current = get()
                if (current.status === "interrupted" && current.humanRequest) {
                    set({ status: "idle", humanRequest: null })
                    toast.error(i18n.t("chat.errors.cancelFailed"))
                }
            }, 5000)
            
        } catch (error) {
            toast.error(i18n.t("chat.errors.cancelHitl"))
            // Rollback optimistic update
            set({ status: previousStatus, humanRequest: previousHumanRequest })
        }
    },

    clearContent: () => {
        set({ 
            messages: [], 
            steps: [], 
            finalOutcome: null, 
            streamedContent: "", 
            humanRequest: null,
            quotaExhaustedInfo: null,
            streamState: {
                events: [],
                currentThinking: null,
                currentTool: null,
                overallProgress: 0,
            },
        })
    },

    setSelectedModel: (model: string | null) => {
        // Update local state
        set({ selectedModel: model })
        // Persist to service (which saves to localStorage)
        llmPlatformService.setSelectedModel(model)
    },

    // --- Internal Handlers ---

    _setConnectionStatus: (connected, status) => {
        set({ isConnected: connected, connectionStatus: status })
    },

    _appendToken: (token) => {
        // Accumulate locally
        const state = get()
        const newBuffer = state._streamBuffer + token
        set({ _streamBuffer: newBuffer })

        // Throttle Update (max 20 FPS / 50ms)
        if (!state._flushTimeout) {
            const timeout = setTimeout(() => {
                const latestBuffer = get()._streamBuffer
                set((state) => ({
                    streamedContent: state.streamedContent + latestBuffer,
                    _streamBuffer: "",
                    _flushTimeout: null,
                }))
            }, 50)
            set({ _flushTimeout: timeout })
        }
    },

    _setHumanRequest: (req: any) => {
        // Handle clear action from ActivityMonitor
        if (req && req.action === "clear") {
            set({ humanRequest: null, status: "idle" })
            return
        }

        // Handle create/update action
        const data = req.data || req
        set({ humanRequest: data, status: "interrupted" })

        if (data) {
            // Determine interaction type and show appropriate notification
            const interactionType = req.type || "text_input"
            const titleMap: Record<string, string> = {
                text_input: i18n.t("chat.interrupted.inputTitle"),
                project_switch: i18n.t("chat.interrupted.projectSwitchTitle"),
                confirm: i18n.t("chat.interrupted.confirmTitle"),
                file_select: i18n.t("chat.interrupted.fileSelectTitle"),
            }

            const title = titleMap[interactionType] || i18n.t("chat.request.title")

            // 1. In-app Toast (Persistent)
            toast.error(title, {
                description: req.prompt,
                duration: Infinity, // Keep until handled
            })

            // 2. Desktop Notification (For background awareness)
            if ("Notification" in window && Notification.permission === "granted") {
                new Notification(`${i18n.t("chat.notification.prefix")}${title}`, {
                    body: req.prompt,
                    requireInteraction: true,
                })
            }
        }
    },

    _setActivitySnapshot: (data: any) => {
        // This is the "Truth" from backend
        // data contains: status, tasks, artifacts...

        const newStatus = data.status || "unknown"
        const prevStatus = get().status

        // Detect Completion (Transition from working to finished)
        if (
            prevStatus === "running" &&
            newStatus !== "running" &&
            newStatus !== "summarizing"
        ) {
            // Clear streamed content when execution completes
            // Note: Messages are updated incrementally via _appendMessage, no need to re-fetch
            set({ streamedContent: "" })
        }

        // Normalize Backend Status -> Frontend Status
        // Backend: running, done, failed, cancelled, stopping, interrupted, idle
        // Frontend: running, idle, error, stopped, interrupted, summarizing, indexing

        let normalizedStatus = newStatus
        if (["done", "failed", "cancelled"].includes(newStatus)) {
            normalizedStatus = "idle"
        } else if (newStatus === "stopping") {
            normalizedStatus = "stopped"
        }

        set({
            status: normalizedStatus,
            steps: data.steps || data.tasks || [],
            artifacts: data.artifacts || [], // Generated artifacts
            finalOutcome: data.final_outcome || null, // Session completion outcome
            activeMemories: data.active_memories || [],
            agentState: data.agent_state || null,
            humanRequest: data.human_request || null, // Fix: Sync HITL request from activity snapshot
        })

        // Extract transient thoughts from agent state
        if (data.agent_state && data.agent_state.details && data.agent_state.details.type === 'thought') {
            const newThought = data.agent_state.details
            const thoughtId = `${Date.now()}-${Math.random()}`

            // Deduplicate: Don't add if we just added this exact title/type recently (e.g. within 2 seconds)
            const recentThoughts = get().thoughts.slice(-3)
            const isDuplicate = recentThoughts.some(t =>
                t.title === (data.agent_state.task_status || "Thinking") &&
                Date.now() - t.timestamp < 2000
            )

            if (!isDuplicate) {
                const thoughtObj = {
                    id: thoughtId,
                    type: "thought",
                    thought_type: newThought.thought_type || "generic",
                    title: data.agent_state.task_status || i18n.t("chat.status.thinking"),
                    content: newThought,
                    confidence: newThought.confidence,
                    timestamp: Date.now()
                }

                // Add to thoughts list, keep last 20
                set(state => ({
                    thoughts: [...state.thoughts, thoughtObj as any].slice(-20)
                }))
            }
        }
    },

    // Incremental update handlers (no re-fetch needed)
    _addStep: (stepEvent: any) => {
        // Add or update a single step incrementally
        const stepData = stepEvent.data || stepEvent
        if (!stepData) return

        // The 'id' is in the event wrapper, not inside data — inject it
        const mergedData = { ...stepData, id: stepEvent.id }

        set(state => {
            const existingIndex = state.steps.findIndex(s => s.id === mergedData.id)
            let newSteps

            if (existingIndex >= 0) {
                // Update existing step — preserve original name/tool/input from create event
                newSteps = [...state.steps]
                newSteps[existingIndex] = { ...newSteps[existingIndex], ...mergedData }
            } else {
                // Add new step
                newSteps = [...state.steps, mergedData]
            }

            return { steps: newSteps }
        })
    },

    _addArtifact: (artifactEvent: any) => {
        // Add or update a single artifact incrementally
        const artifactData = artifactEvent.data || artifactEvent
        if (!artifactData) return

        set(state => {
            const existingIndex = state.artifacts.findIndex(a => a.id === artifactData.id || a.name === artifactData.name)
            let newArtifacts
            
            if (existingIndex >= 0) {
                // Update existing artifact
                newArtifacts = [...state.artifacts]
                newArtifacts[existingIndex] = { ...newArtifacts[existingIndex], ...artifactData }
            } else {
                // Add new artifact
                newArtifacts = [...state.artifacts, artifactData]
            }
            
            return { artifacts: newArtifacts }
        })
    },

    _updateStatus: (statusEvent: any) => {
        // Update status incrementally
        const newStatus = statusEvent.status || statusEvent
        if (!newStatus) return

        // Special handling for quota_exhausted - do not normalize
        if (newStatus === "quota_exhausted") {
            set({ status: "quota_exhausted" })
            return
        }

        // Normalize backend status to frontend status
        let normalizedStatus = newStatus
        if (["done", "failed", "cancelled"].includes(newStatus)) {
            normalizedStatus = "idle"
        } else if (newStatus === "stopping") {
            normalizedStatus = "stopped"
        }

        const prevStatus = get().status
        const currentHumanRequest = get().humanRequest
        
        // Detect completion - clear streamed content when execution ends
        // Note: Messages are updated incrementally via _appendMessage, no need to re-fetch
        if (prevStatus === "running" && normalizedStatus !== "running") {
            set({ streamedContent: "" })
        }

        // HITL Safety Net 1: When leaving interrupted state, clear humanRequest
        if (prevStatus === "interrupted" && normalizedStatus !== "interrupted") {
            set({ status: normalizedStatus, humanRequest: null })
            return
        }
        
        // HITL Safety Net 2: If status is not interrupted but humanRequest exists, clear it
        if (normalizedStatus !== "interrupted" && currentHumanRequest) {
            set({ status: normalizedStatus, humanRequest: null })
            return
        }

        // When leaving quota_exhausted state, clear the info
        if (prevStatus === "quota_exhausted" && normalizedStatus !== "quota_exhausted") {
            set({ status: normalizedStatus, quotaExhaustedInfo: null })
            return
        }

        set({ status: normalizedStatus })
    },

    _setQuotaExhausted: (info: { title: string; message: string; hint: string; actionText: string }) => {
        set({ 
            status: "quota_exhausted",
            quotaExhaustedInfo: info,
            streamedContent: "",
            steps: [],
        })
    },

    _appendMessage: (rawMsg: any) => {
        const { messages, threadId } = get()
        if (!rawMsg || !threadId) return

        // Tool messages are now folded server-side
        // Backend API now returns pre-folded messages with nested 'steps' array
        // If we receive a tool message here, it's likely an orphan or out-of-order
        if (rawMsg.role === "tool" || rawMsg.type === "tool") {
            // Log warning in dev mode, but don't try to fold manually
            console.warn("[ChatStore] Received orphan tool message:", rawMsg.id)
            return
        }

        // 1. Format
        // Use pre-folded steps from backend
        // Normalize role: user->human, assistant->ai
        const normalizedRole = rawMsg.role === "human" || rawMsg.role === "user" ? "human" : "ai"
        const newMsg: Message = {
            id: rawMsg.id,
            role: normalizedRole,
            originalRole: rawMsg.role,
            content: rawMsg.content || "",
            thinking: rawMsg.thinking,
            timestamp: rawMsg.created_at || new Date().toISOString(),
            steps_snapshot: rawMsg.steps_snapshot,
            tool_calls: rawMsg.tool_calls,
            steps: rawMsg.steps || [], // Use backend-folded steps if available
            references: rawMsg.references || [],
        }

        // 2. Check if this is an update to an existing message (e.g., steps added via tool folding)
        const existingIndex = messages.findIndex(m => m.id === newMsg.id)
        
        if (existingIndex >= 0) {
            // Update existing message - only update fields that changed, don't merge content
            const existingMsg = messages[existingIndex]
            const updatedMsg: Message = {
                ...existingMsg,
                // Update steps if new steps are provided (tool execution updates)
                steps: (newMsg.steps && newMsg.steps.length > 0) ? newMsg.steps : existingMsg.steps,
                // Update snapshot if provided
                steps_snapshot: newMsg.steps_snapshot || existingMsg.steps_snapshot,
                // Update tool_calls if provided
                tool_calls: newMsg.tool_calls || existingMsg.tool_calls,
                // Update thinking if provided
                thinking: newMsg.thinking || existingMsg.thinking,
                // Keep original content and timestamp - don't update
                content: existingMsg.content,
                timestamp: existingMsg.timestamp,
            }
            
            const newMessages = [...messages]
            newMessages[existingIndex] = updatedMsg
            set({ messages: newMessages, streamedContent: "" })
            return
        }

        // 3. Append as new message - NO MERGING with previous messages
        // Each AI message is displayed independently, matching history message display
        set(state => ({
            messages: [...state.messages, newMsg],
            streamedContent: "" // Commit the stream
        }))
    },

    _truncateMessages: (index: number) => {
        const { messages } = get()
        if (index >= 0 && index < messages.length) {
            set({ messages: messages.slice(0, index) })
        }
    },

    _setError: (error: string) => {
        toast.error(i18n.t("chat.errors.connection", { error }))
    },

    // Changeset Actions
    setChangeset: (files: ChangesetFile[]) => {
        set({ changeset: files, changesetLastUpdated: new Date().toISOString() })
    },

    addToChangeset: (file: ChangesetFile) => {
        set((state) => {
            const existingIndex = state.changeset.findIndex(f => f.path === file.path)
            let newChangeset
            if (existingIndex >= 0) {
                // Update existing file
                newChangeset = [...state.changeset]
                newChangeset[existingIndex] = file
            } else {
                // Add new file
                newChangeset = [...state.changeset, file]
            }
            return {
                changeset: newChangeset,
                changesetLastUpdated: new Date().toISOString()
            }
        })
    },

    markChangeAsViewed: (path: string) => {
        set((state) => {
            const newViewed = new Set(state.viewedChanges)
            newViewed.add(path)
            return { viewedChanges: newViewed }
        })
        // Persist to localStorage
        const { threadId } = get()
        if (threadId) {
            const key = `evoloop:viewed:${threadId}`
            const viewed = get().viewedChanges
            localStorage.setItem(key, JSON.stringify([...viewed]))
        }
    },

    markAllChangesAsViewed: () => {
        set((state) => {
            const allPaths = state.changeset.map(f => f.path)
            return { viewedChanges: new Set(allPaths) }
        })
        const { threadId } = get()
        if (threadId) {
            const key = `evoloop:viewed:${threadId}`
            const viewed = get().viewedChanges
            localStorage.setItem(key, JSON.stringify([...viewed]))
        }
    },

    clearChangeset: () => {
        set({ changeset: [], viewedChanges: new Set(), changesetLastUpdated: null })
    },

    loadViewedChanges: (threadId: string) => {
        try {
            const key = `evoloop:viewed:${threadId}`
            const saved = localStorage.getItem(key)
            if (saved) {
                const viewed = JSON.parse(saved)
                set({ viewedChanges: new Set(viewed) })
            }
        } catch {
            // ignore parse errors
        }
    },

    _processStreamEvent: (event: StreamEvent) => {
        const state = get().streamState
        const MAX_EVENTS = 100
        const newEvents = [...state.events, event].slice(-MAX_EVENTS)

        switch (event.type) {
            case 'thinking':
                set({
                    streamState: {
                        ...state,
                        events: newEvents,
                        currentThinking: event.message,
                    }
                })
                break

            case 'tool_start':
                set({
                    streamState: {
                        ...state,
                        events: newEvents,
                        currentTool: {
                            id: event.data?.toolId || `tool-${Date.now()}`,
                            toolName: event.data?.toolName || i18n.t("common.tool.defaultName"),
                            displayName: event.data?.tool_meta?.display_name || event.data?.displayName || event.data?.toolName || i18n.t("common.tool.defaultName"),
                            status: 'running',
                            progress: 0,
                            message: event.message,
                            startTime: event.timestamp,
                            params: event.data?.params,
                        },
                    }
                })
                break

            case 'tool_progress':
                if (state.currentTool) {
                    set({
                        streamState: {
                            ...state,
                            events: newEvents,
                            currentTool: {
                                ...state.currentTool,
                                progress: event.progress || state.currentTool.progress,
                                message: event.message,
                            },
                        }
                    })
                }
                break

            case 'tool_complete':
                if (state.currentTool) {
                    set({
                        streamState: {
                            ...state,
                            events: newEvents,
                            currentTool: {
                                ...state.currentTool,
                                status: 'complete',
                                progress: 100,
                                message: event.message,
                                endTime: event.timestamp,
                                result: event.data?.result,
                            },
                        }
                    })
                }
                break

            case 'tool_error':
                if (state.currentTool) {
                    set({
                        streamState: {
                            ...state,
                            events: newEvents,
                            currentTool: {
                                ...state.currentTool,
                                status: 'error',
                                message: event.message,
                                endTime: event.timestamp,
                                error: event.data?.error,
                            },
                        }
                    })
                }
                break

            case 'progress':
                set({
                    streamState: {
                        ...state,
                        events: newEvents,
                        overallProgress: event.progress || state.overallProgress,
                    }
                })
                break

            case 'complete':
                set({
                    streamState: {
                        ...state,
                        events: newEvents,
                        currentThinking: null,
                        currentTool: null,
                        overallProgress: 100,
                    }
                })
                break

            case 'quota_exhausted':
                // Handle quota exhausted event from backend
                get()._setQuotaExhausted({
                    title: event.title || i18n.t("quota.title", "Quota Exhausted"),
                    message: event.message || i18n.t("quota.message", "Your LLM quota has been exhausted."),
                    hint: event.hint || i18n.t("quota.hint", "Please contact the administrator to add more quota."),
                    actionText: event.action_text || i18n.t("quota.action", "Check Quota"),
                })
                break

            case 'llm_auth_error':
                // Handle LLM API authentication error
                toast.error(event.title || i18n.t("chat.llmAuthError", "LLM API 认证失败"), {
                    description: event.message || i18n.t("chat.llmAuthErrorDesc", "API 密钥无效或已过期"),
                    action: {
                        label: i18n.t("chat.goToSettings", "去设置"),
                        onClick: () => {
                            window.location.hash = '#/settings'
                        }
                    },
                    duration: 10000,
                })
                set({
                    status: 'error',
                    streamState: {
                        ...state,
                        events: newEvents,
                    }
                })
                break

            case 'auth_expired':
                // EvoLoop 平台认证过期，清除 token 并跳转到登录页
                console.warn("[ChatStore] EvoLoop auth expired, clearing token and redirecting to login");

                // 保存当前路径（用于登录后返回）
                const currentHashPath = window.location.hash
                if (currentHashPath && currentHashPath !== '#/login') {
                    localStorage.setItem('redirect_after_login', currentHashPath)
                }

                // 清除 token
                localStorage.removeItem("access_token")

                // 显示提示
                toast.error(event.title || i18n.t("auth.sessionExpired", "登录已过期"), {
                    description: event.message || i18n.t("auth.pleaseLoginAgain", "EvoLoop 平台认证已过期，请重新登录"),
                    duration: 5000,
                })

                set({
                    status: 'error',
                    streamState: {
                        ...state,
                        events: newEvents,
                    }
                })

                // 延迟跳转到登录页
                setTimeout(() => {
                    window.location.href = "/login"
                }, 500)
                break

            default:
                set({
                    streamState: {
                        ...state,
                        events: newEvents,
                    }
                })
        }
    },
}))
