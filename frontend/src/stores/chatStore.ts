import { toast } from "sonner"
import { create } from "zustand"
import { AgentService, ConversationsService } from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
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
    artifacts: Array<{ id: number; name: string; type: string; status: string; path?: string }> // Phase 8: Artifacts
    humanRequest: any | null // HITL Request
    agentState: { mode: string; task_name: string; task_status: string; details?: any } | null // Phase 9
    thoughts: any[] // Phase 6: Transient Thoughts history

    isConnected: boolean
    connectionStatus: string

    // Throttling Logic
    _streamBuffer: string
    _flushTimeout: any

    // --- Actions ---

    // storage/network actions
    setThread: (threadId: string, projectId: number) => Promise<void>
    fetchHistory: (threadId: string) => Promise<void>
    sendMessage: (content: string, attachments?: any[]) => Promise<void>
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

    activeMemories: [],
    artifacts: [],
    humanRequest: null,
    agentState: null,
    thoughts: [], // Phase 6

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
                    originalType: m.type, // Keep raw type for filtering
                    content: m.content || "",
                    thinking: m.thinking,
                    timestamp: m.created_at,
                    tasks_snapshot: m.tasks_snapshot, // Phase 6: Historical tasks
                }))
                // Filter out empty messages AND 'tool' messages (which cause chat bubble explosion)
                .filter((m: any) => (m.content || m.thinking) && m.originalType !== "tool")

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

    sendMessage: async (content, attachments: any[] = []) => {
        const { threadId, projectId } = get()
        if (!threadId || (!content.trim() && attachments.length === 0)) return

        // 1. Optimistic Update
        const tempId = Date.now()

        // Construct display content for local optimistic UI (Markdown fallback)
        let displayContent = content
        if (attachments.length > 0) {
            const attachmentLinks = attachments
                .map((att) => att.type === 'image' ? `![Image](${att.url})` : `[${att.type === 'message' ? 'Message' : 'File'}: ${att.name || att.url}]`)
                .join("\n")
            displayContent = displayContent
                ? `${displayContent}\n${attachmentLinks}`
                : attachmentLinks
        }

        const newMessage: Message = {
            id: tempId,
            role: "user",
            content: displayContent,
        }

        set((state) => ({
            messages: [...state.messages, newMessage],
            status: "running", // Assume running immediately
        }))

        // 2. Send Request
        try {
            await AgentService.chatEndpoint({
                requestBody: {
                    message: content, // Send raw text (backend handles merging)
                    thread_id: threadId,
                    project_id: projectId!,
                    attachments: attachments // Pass structured attachments
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

        // Normalize Backend Status -> Frontend Status
        // Backend: running, done, failed, cancelled, stopping, interrupted, idle
        // Frontend: running, idle, error, stopped, interrupted, SUMMARIZING, INDEXING

        let normalizedStatus = newStatus
        if (["done", "failed", "cancelled"].includes(newStatus)) {
            normalizedStatus = "idle"
        } else if (newStatus === "stopping") {
            normalizedStatus = "stopped"
        }

        set({
            status: normalizedStatus,
            tasks: data.tasks || [],
            artifacts: data.artifacts || [], // Phase 8: Automatically Map Artifacts
            activeMemories: data.active_memories || [], // Phase 7
            agentState: data.agent_state || null, // Phase 9
        })

        // Phase 6: Transient Thought Extraction
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
                    title: data.agent_state.task_status || "Thinking",
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

    _setError: (error: string) => {
        toast.error(`Connection Error: ${error}`)
    },
}))
