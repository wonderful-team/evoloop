import { toast } from "sonner"
import { create } from "zustand"
import { AgentService, ChatConnection, ConversationsService } from "@/client"
import type { Message } from "@/components/Chat/ChatMessageItem"
import type { TaskItem as TaskStep } from "@/components/Chat/TaskSteps"

interface ChatState {
    // --- Data ---
    threadId: string | null
    projectId: number | null
    messages: Message[]

    // Activity State
    status:
    | "idle"
    | "running"
    | "error"
    | "stopped"
    | "interrupted"
    | "SUMMARIZING"
    | "INDEXING"
    | "unknown"
    tasks: TaskStep[]
    streamedContent: string // The currently streaming token buffer (for the specific AI task)
    activeMemories: Array<{ id: string; name: string }> // Phase 7: Active memory highlights
    humanRequest: any | null // HITL Request

    isConnected: boolean
    connectionStatus: string

    // Throttling Logic
    _streamBuffer: string
    _flushTimeout: any

    // --- Actions ---

    // storage/network actions
    setThread: (threadId: string, projectId: number) => Promise<void>
    fetchHistory: (threadId: string) => Promise<void>
    sendMessage: (content: string) => Promise<void>
    stopAgent: () => Promise<void>
    resumeAgent: (userInput?: string) => Promise<void>
    clearContent: () => void

    // internal sse handlers (called by ChatConnection)
    _setConnectionStatus: (connected: boolean, status: string) => void
    _appendToken: (tokens: string) => void
    _setActivitySnapshot: (snapshot: any) => void
    _setHumanRequest: (request: any) => void
    _setError: (error: string) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
    threadId: null,
    projectId: null,
    messages: [],

    status: "idle",
    tasks: [],
    streamedContent: "",
    activeMemories: [], // Phase 7
    humanRequest: null,

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
                    tasks: [],
                    streamedContent: "",
                    status: "idle",
                    humanRequest: null,
                }
                : {}),
        })

        // 2. Connect SSE (Persistent)
        const connection = ChatConnection.getInstance()

        // Update Callbacks (to ensure they point to current store instance/state if needed, though 'set' is stable)
        connection.setCallbacks({
            onConnectionChange: (connected: boolean, status: string) =>
                get()._setConnectionStatus(connected, status),
            onToken: (token: string) => get()._appendToken(token),
            onActivity: (snapshot: any) => get()._setActivitySnapshot(snapshot),
            onHumanRequest: (req: any) => get()._setHumanRequest(req),
            onError: (error: string) => get()._setError(error),
        })

        connection.connect(threadId)

        // 3. Fetch History (Optimistic replacement inside fetchHistory)
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
    },

    fetchHistory: async (threadId) => {
        try {
            const history = (await ConversationsService.getConversationMessages({
                threadId,
            })) as any
            const rawMessages = Array.isArray(history)
                ? history
                : history?.messages || []

            // Format - Phase 6: Include tasks_snapshot
            const formatted: Message[] = rawMessages
                .map((m: any, idx: number) => ({
                    id: m.id || idx,
                    role: m.type === "human" ? "user" : "ai",
                    content: m.content || "",
                    thinking: m.thinking,
                    timestamp: m.created_at,
                    tasks_snapshot: m.tasks_snapshot, // Phase 6: Historical tasks
                }))
                .filter((m: Message) => m.content || m.thinking)

            // Optimistic Swap:
            // If we are still on the same thread, update the messages.
            // This happens in a single state update, so React batches the swap.
            if (get().threadId === threadId) {
                set({ messages: formatted })
            }
        } catch (e) {
            console.error("Failed to fetch history", e)
            if (get().messages.length === 0) {
                toast.error("Failed to load chat history")
            }
        }
    },

    sendMessage: async (content) => {
        const { threadId, projectId } = get()
        if (!threadId || !content.trim()) return

        // 1. Optimistic Update
        const tempId = Date.now()
        const newMessage: Message = {
            id: tempId,
            role: "user",
            content: content,
        }

        set((state) => ({
            messages: [...state.messages, newMessage],
            status: "running", // Assume running immediately
        }))

        // 2. Send Request
        try {
            await AgentService.chatEndpoint({
                requestBody: {
                    message: content,
                    thread_id: threadId,
                    project_id: projectId!,
                },
            })
            // Success - we don't need to do anything, SSE "status: running" will confirm
            // But we keep status running just in case SSE is slow
        } catch (e) {
            console.error(e)
            toast.error("Failed to send message")
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
            toast.info("Agent stopped")
            set({ status: "stopped", humanRequest: null })
        } catch (_e) {
            toast.error("Failed to stop agent")
        }
    },

    resumeAgent: async (userInput?: string) => {
        const { threadId } = get()
        if (!threadId) return

        try {
            await AgentService.resumeChat({
                requestBody: { thread_id: threadId, user_input: userInput },
            })
            toast.info("Agent resuming...")
            set({ status: "running", humanRequest: null }) // Optimistic clear
        } catch (_e) {
            toast.error("Failed to resume agent")
        }
    },

    clearContent: () => {
        set({ messages: [], tasks: [], streamedContent: "", humanRequest: null })
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
        set({ humanRequest: req, status: "interrupted" })
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
            newStatus !== "SUMMARIZING"
        ) {
            // 1. Trigger Async History Refresh
            // We don't clear streamedContent YET, to keep it visible while history loads.
            const tid = get().threadId
            if (tid) {
                get()
                    .fetchHistory(tid)
                    .then(() => {
                        // 2. Once history arrived, clear the buffer.
                        // React will swap the 'streaming bubble' for the 'permanent message' in a single frame.
                        set({ streamedContent: "" })
                    })
            }
        }

        set({
            status: newStatus,
            tasks: data.tasks || [],
            activeMemories: data.active_memories || [], // Phase 7
        })
    },

    _setError: (error: string) => {
        // toast.error(`Connection Error: ${error}`)
    },
}))
