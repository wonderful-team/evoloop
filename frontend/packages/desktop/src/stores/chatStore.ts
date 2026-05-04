import { toast } from "sonner"
import { create } from "zustand"
import i18n from "@evoloop/shared/i18n"
import { AgentService, ConversationsService } from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
import { llmPlatformService } from "@/services/llmPlatform"
import type { Message } from "@/components/Chat/ChatMessageItem"

import { ChatState, ActivitySnapshot } from "./chat/types"
import { 
    commitThinkingBuffer, 
    normalizeMessage, 
    tryParseHumanRequest 
} from "./chat/helpers"

export const useChatStore = create<ChatState>((set, get) => ({
    // --- Initial State ---
    threadId: null,
    projectId: null,
    skillId: null,
    messages: [],
    changeset: [],
    viewedChanges: new Set<string>(),
    changesetLastUpdated: null,
    hasMoreHistory: true,
    isLoadingHistory: false,
    firstMessageId: null,
    totalMessageCount: null,
    selectedModel: llmPlatformService.getSelectedModel(),
    status: "idle",
    finalOutcome: null,
    activeMemories: [],
    artifacts: [],
    humanRequest: null,
    quotaExhaustedInfo: null,
    agentState: null,
    streamingThinking: "",
    streamingSteps: [],
    isConnected: false,
    connectionStatus: "disconnected",
    _streamBuffer: "",
    _flushTimeout: null,

    // --- Core Actions ---
    setThread: async (threadId, projectId, skillId) => {
        const currentThreadId = get().threadId
        set({
            threadId,
            projectId,
            skillId: skillId || null,
            ...(currentThreadId !== threadId ? {
                messages: [],
                status: "idle",
                finalOutcome: null,
                humanRequest: null,
                changeset: [],
                viewedChanges: new Set(),
                changesetLastUpdated: null,
                hasMoreHistory: false,
                firstMessageId: null,
                totalMessageCount: null,
                isLoadingHistory: false,
            } : {}),
        })

        if (threadId) {
            get().loadViewedChanges(threadId)
            
            // Register callbacks once
            const store = get()
            ChatConnection.getInstance().setCallbacks({
                onConnectionChange: store._setConnectionStatus,
                onToken: store._appendToken,
                onActivity: store._setActivitySnapshot,
                onArtifact: store._addArtifact,
                onStatus: store._updateStatus,
                onHumanRequest: store._setHumanRequest,
                onMessage: store._appendMessage,
                onThinking: (ev) => store._appendThinking(ev.content),
                onProgress: (ev) => store._updateProgress(ev),
                onAgentState: (ev) => store._setAgentState(ev),
                onQuotaExhausted: store._setQuotaExhausted,
                onLLMAuthError: store._setLLMAuthError,
                onRunStart: store._handleRunStart,
                onRunEnd: store._handleRunEnd,
                onAuthExpired: (ev) => toast.error(ev.message),
                onError: store._setError,
                onUnauthorized: () => {
                    set({ status: 'unauthorized' })
                }
            })

            // Fetch history and activity first, then connect SSE
            Promise.all([
                get().fetchHistory(threadId),
                get().fetchActivity(threadId)
            ]).then(() => {
                ChatConnection.getInstance().connect(threadId)
            })
        } else {
            ChatConnection.getInstance().disconnect()
        }
    },

    fetchHistory: async (threadId) => {
        set({ isLoadingHistory: true })
        try {
            const data = await ConversationsService.getConversationMessages({
                threadId,
                limit: 30,
            })
            const msgs = (data.data || []).map(normalizeMessage)
            set({
                messages: msgs,
                hasMoreHistory: !!data.has_more,
                firstMessageId: data.first_id || null,
                totalMessageCount: data.total_count || data.total || msgs.length,
            })
        } catch (e) {
            console.error("[ChatStore] Fetch history failed", e)
        } finally {
            set({ isLoadingHistory: false })
        }
    },

    fetchActivity: async (threadId) => {
        try {
            const data = (await ConversationsService.getThreadActivity({ threadId })) as any as ActivitySnapshot
            set({
                artifacts: data.artifacts || [],
                activeMemories: data.active_memories || [],
                agentState: data.agent_state || null,
                finalOutcome: data.final_outcome || null,
                status: (data.status === "done" || data.status === "failed") ? "idle" : (data.status as any || "idle")
            })
        } catch (e) {
            console.error("[ChatStore] Fetch activity failed", e)
        }
    },

    loadMoreHistory: async () => {
        const { threadId, firstMessageId, hasMoreHistory, isLoadingHistory } = get()
        if (!threadId || !hasMoreHistory || isLoadingHistory || !firstMessageId) return

        set({ isLoadingHistory: true })
        try {
            const data = await ConversationsService.getConversationMessages({
                threadId,
                beforeId: String(firstMessageId),
                limit: 30,
            })
            const oldMsgs = (data.data || []).map(normalizeMessage)
            set((state) => ({
                messages: [...oldMsgs, ...state.messages],
                hasMoreHistory: !!data.has_more,
                firstMessageId: data.first_id || null,
            }))
        } catch (e) {
            console.error("[ChatStore] Load more history failed", e)
        } finally {
            set({ isLoadingHistory: false })
        }
    },

    rewindToMessage: async (messageId) => {
        const { threadId } = get()
        if (!threadId) return
        try {
            set({ status: "running" })
            await ConversationsService.rewindConversation({
                threadId,
                requestBody: {
                    message_id: messageId,
                    revert_files: true
                }
            })
            // Optimization: Truncate locally instead of full refetch
            const index = get().messages.findIndex(m => m.id === messageId)
            if (index !== -1) {
                set({ messages: get().messages.slice(0, index) })
            }
            // Trigger changeset refresh as files might have reverted
            get().fetchChangeset()
        } catch (e) {
            toast.error("Failed to rewind conversation")
            set({ status: "idle" })
        }
    },

    sendMessage: async (content, attachments, skillId) => {
        const { threadId, projectId, skillId: stateSkillId } = get()
        if (!threadId || !projectId) return

        const activeSkillId = skillId || stateSkillId
        // Optimistic update
        const tempId = `temp-${Date.now()}`
        const userMsg: Message = {
            id: tempId,
            role: "human",
            content,
            timestamp: new Date().toISOString(),
            status: "completed",
            changeset_count: 0,
            attachments: attachments || [],
            references: (attachments || [])
                .filter(a => ['reference', 'file', 'message', 'skill'].includes(a.type))
                .map(a => ({
                    id: a.id,
                    type: a.type,
                    target_id: a.url,
                    target_name: a.name
                }))
        }
        set((state) => ({ messages: [...state.messages, userMsg] }))

        try {
            await AgentService.chatEndpoint({
                requestBody: {
                    thread_id: threadId,
                    project_id: projectId,
                    skill_id: activeSkillId || undefined,
                    message: content,
                    model: get().selectedModel || undefined,
                    attachments: attachments || undefined,
                }
            })
        } catch (e: any) {
            toast.error(i18n.t("chat.errors.sendFailed"))
            set((state) => ({
                messages: state.messages.filter(m => m.id !== tempId)
            }))
        }
    },

    stopAgent: async () => {
        const { threadId } = get()
        if (!threadId) return
        try {
            await AgentService.stopChat({ requestBody: { thread_id: threadId, message: "" } })
            set({ status: "stopped" })
        } catch (e) {
            toast.error("Failed to stop agent")
        }
    },

    resumeAgent: async (userInput) => {
        const { threadId } = get()
        if (!threadId) return
        try {
            await AgentService.resumeChat({
                requestBody: { thread_id: threadId, user_input: userInput }
            })
            set({ status: "running", humanRequest: null })
        } catch (e) {
            toast.error("Failed to resume agent")
        }
    },

    cancelHumanRequest: async (reason) => {
        const { threadId } = get()
        if (!threadId) return
        try {
            await AgentService.cancelHitlRequest({
                requestBody: { thread_id: threadId, reason }
            })
            set({ humanRequest: null, status: "idle" })
        } catch (e) {
            toast.error("Failed to cancel request")
        }
    },

    clearContent: () => set({ messages: [], finalOutcome: null, humanRequest: null, quotaExhaustedInfo: null }),

    setSelectedModel: (model) => {
        set({ selectedModel: model })
        llmPlatformService.setSelectedModel(model)
    },

    fetchChangeset: async () => {
        const { threadId } = get()
        if (!threadId) return
        try {
            const data = await ConversationsService.getThreadChangeset({ threadId })
            // Flatten the changeset tree if needed, or map nodes to flat list
            // Backend returns a tree, but our UI usually expects a list of files
            const flatten = (node: any, list: any[] = []) => {
                if (node.path && node.operation) list.push(node)
                if (node.children) node.children.forEach((c: any) => flatten(c, list))
                return list
            }
            const files = flatten(data)
            set({ changeset: files, changesetLastUpdated: new Date().toISOString() })
        } catch (e) {
            console.error("[ChatStore] Fetch changeset failed", e)
        }
    },

    // --- Changeset Actions ---
    setChangeset: (files) => set({ changeset: files, changesetLastUpdated: new Date().toISOString() }),

    addToChangeset: (file) => {
        set((state) => {
            const idx = state.changeset.findIndex(f => f.path === file.path)
            const newCs = idx >= 0 ? [...state.changeset] : [...state.changeset, file]
            if (idx >= 0) newCs[idx] = file
            return { changeset: newCs, changesetLastUpdated: new Date().toISOString() }
        })
    },

    markChangeAsViewed: (path) => {
        set((state) => {
            const newViewed = new Set(state.viewedChanges).add(path)
            const { threadId } = state
            if (threadId) localStorage.setItem(`evoloop:viewed:${threadId}`, JSON.stringify([...newViewed]))
            return { viewedChanges: newViewed }
        })
    },

    markAllChangesAsViewed: () => {
        set((state) => {
            const allPaths = state.changeset.map(f => f.path)
            const newViewed = new Set(allPaths)
            if (state.threadId) localStorage.setItem(`evoloop:viewed:${state.threadId}`, JSON.stringify(allPaths))
            return { viewedChanges: newViewed }
        })
    },

    clearChangeset: () => set({ changeset: [], viewedChanges: new Set(), changesetLastUpdated: null }),

    loadViewedChanges: (threadId) => {
        const saved = localStorage.getItem(`evoloop:viewed:${threadId}`)
        if (saved) set({ viewedChanges: new Set(JSON.parse(saved)) })
    },

    // --- Internal Handlers ---
    _setConnectionStatus: (connected, status) => set({ isConnected: connected, connectionStatus: status }),

    _appendThinking: (text) => {
        set((state) => {
            const msgs = [...state.messages]
            let last = msgs[msgs.length - 1]
            
            // Auto-create AI placeholder if not present
            if (last?.role !== "ai") {
                const placeholder: Message = {
                    id: `streaming-${Date.now()}`,
                    role: "ai",
                    content: "",
                    thinking: text,
                    status: "streaming",
                    timestamp: new Date().toISOString(),
                    changeset_count: 0
                }
                msgs.push(placeholder)
            } else {
                last.thinking = (last.thinking || "") + text
                last.status = "streaming"
            }
            
            return { 
                messages: msgs,
                streamingThinking: (state.streamingThinking || "") + text 
            }
        })
    },

    _appendToken: (tokens) => {
        set((state) => {
            const msgs = [...state.messages]
            let last = msgs[msgs.length - 1]
            
            // Auto-create AI placeholder if not present
            if (last?.role !== "ai") {
                const placeholder: Message = {
                    id: `streaming-${Date.now()}`,
                    role: "ai",
                    content: tokens,
                    thinking: state.streamingThinking || "",
                    status: "streaming",
                    timestamp: new Date().toISOString(),
                    changeset_count: 0
                }
                msgs.push(placeholder)
            } else {
                if (state.streamingThinking) {
                    last.thinking = (last.thinking || "") + state.streamingThinking
                }
                last.content = (last.content || "") + tokens
                last.status = "streaming"
            }
            
            return { 
                messages: msgs, 
                streamingThinking: "" 
            }
        })
    },

    _setHumanRequest: (req) => {
        if (!req) return
        if (req.action === "clear") {
            set((state) => ({
                humanRequest: null,
                status: "idle",
                messages: state.messages.map(m => m.humanRequest ? { ...m, humanRequest: undefined } : m)
            }))
            return
        }
        const data = req.data || req
        set((state) => {
            const msgs = [...state.messages]
            const lastAi = [...msgs].reverse().find(m => m.role === "ai")
            if (lastAi) lastAi.humanRequest = data
            return { humanRequest: data, status: "interrupted", messages: msgs }
        })
        const type = req.request_type || req.type || "text_input"
        const title = i18n.t(`chat.interrupted.${type}Title`, { defaultValue: i18n.t("chat.request.title") })
        toast.error(title, { description: req.prompt, duration: Infinity })
    },

    _setActivitySnapshot: (data) => {
        const newStatus = data.status || "unknown"
        let normalized = newStatus
        if (["done", "failed", "cancelled"].includes(newStatus)) normalized = "idle"
        else if (newStatus === "stopping") normalized = "stopped"

        set({
            status: normalized,
            artifacts: data.artifacts || [],
            finalOutcome: data.final_outcome || null,
            activeMemories: data.active_memories || [],
            agentState: data.agent_state || null,
        })
    },

    _addArtifact: (ev) => {
        const data = ev.data || ev
        set(state => {
            const idx = state.artifacts.findIndex(a => a.id === data.id || a.name === data.name)
            const list = [...state.artifacts]
            if (idx >= 0) list[idx] = { ...list[idx], ...data }
            else list.push(data)
            return { artifacts: list }
        })
    },

    _updateStatus: (ev) => {
        const raw = ev.status || ev
        if (raw === "quota_exhausted") return set({ status: "quota_exhausted" })
        
        let normalized = raw
        if (["done", "failed", "cancelled"].includes(raw)) normalized = "idle"
        else if (raw === "stopping") normalized = "stopped"

        const state = get()
        const updates: Partial<ChatState> = { 
            status: normalized,
            activeMemories: ev.active_memories || state.activeMemories,
            agentState: ev.agent_state || state.agentState
        }
        if (normalized === "idle") {
            Object.assign(updates, commitThinkingBuffer(state))
        }
        if (state.status === "running" && normalized !== "running") {
            updates.messages = state.messages.map(m => m.status === "streaming" ? { ...m, status: "completed" } : m)
        }
        if (normalized !== "interrupted" && state.humanRequest) {
            updates.humanRequest = null
            updates.messages = (updates.messages || state.messages).map(m => m.humanRequest ? { ...m, humanRequest: undefined } : m)
        }
        set(updates)
    },

    _setQuotaExhausted: (info) => set({ 
        status: "quota_exhausted", 
        quotaExhaustedInfo: {
            title: info.title || i18n.t("chat.quotaExhausted.title"),
            message: info.message || i18n.t("chat.quotaExhausted.message"),
            hint: info.hint || i18n.t("chat.quotaExhausted.hint"),
            actionText: info.actionText || i18n.t("chat.quotaExhausted.action")
        } 
    }),

    _setLLMAuthError: (ev) => {
        toast.error(ev.title || i18n.t("chat.llmAuthError", "LLM API 认证失败"), {
            description: ev.message || i18n.t("chat.llmAuthErrorDesc", "API 密钥无效或已过期"),
            action: { 
                label: i18n.t("chat.goToSettings", "去设置"), 
                onClick: () => { window.location.hash = '#/settings' } 
            },
            duration: 10000,
        })
        set({ status: 'error' })
    },

    _setAgentState: (ev) => set({
        agentState: {
            mode: ev.mode,
            task_name: ev.task_name,
            task_status: ev.task_status
        }
    }),

    _updateProgress: (ev) => set(state => ({ 
        agentState: state.agentState 
            ? { ...state.agentState, task_status: ev.message } 
            : { mode: "PLANNING", task_name: "Agent Running", task_status: ev.message } 
    })),

    _appendMessage: (raw) => {
        const { threadId, messages } = get()
        set(commitThinkingBuffer)
        const humanReq = tryParseHumanRequest(raw)
        if (!threadId || (raw.role === "system" && !humanReq)) return

        if (humanReq) {
            set(state => {
                const msgs = [...state.messages]
                const lastAi = [...msgs].reverse().find(m => m.role === "ai")
                if (lastAi) lastAi.humanRequest = humanReq
                return { messages: msgs, humanRequest: humanReq, status: "interrupted" }
            })
            return
        }

        const msg = normalizeMessage(raw)
        const existIdx = messages.findIndex(m => m.id === msg.id)
        if (existIdx >= 0) {
            set(state => {
                const msgs = [...state.messages]
                const ex = msgs[existIdx]
                msgs[existIdx] = { 
                    ...ex, 
                    thinking: msg.thinking || ex.thinking,
                    content: (ex.status === "streaming") ? ex.content : (msg.content || ex.content),
                    status: msg.status || ex.status
                }
                return { messages: msgs }
            })
            return
        }

        const streamIdx = messages.findIndex(m => m.role === "ai" && m.status === "streaming")
        if (streamIdx >= 0 && msg.role === "ai") {
            set(state => {
                const msgs = [...state.messages]
                msgs[streamIdx] = { 
                    ...msg, 
                    content: msg.content || msgs[streamIdx].content,
                    thinking: msg.thinking || msgs[streamIdx].thinking,
                    status: msg.status || "completed" 
                }
                return { messages: msgs }
            })
            return
        }
        // Trigger changeset refresh if message has file changes
        if (msg.changeset_count && msg.changeset_count > 0) {
            get().fetchChangeset()
        }

        set(state => ({ messages: [...state.messages, msg] }))
    },

    _truncateMessages: (idx) => set(state => ({ messages: state.messages.slice(0, idx) })),
    _handleRunStart: (ev) => {
        set({ 
            status: "running", 
            streamingThinking: "", 
            _streamBuffer: "",
            finalOutcome: null 
        })
        console.log(`[ChatStore] Run started: ${ev.run_id}`)
    },

    _handleRunEnd: (ev) => {
        const state = get()
        const normalized = (ev.status === "done" || ev.status === "failed" || ev.status === "cancelled") ? "idle" : (ev.status as any || "idle")
        
        const updates: Partial<ChatState> = { 
            status: normalized,
            finalOutcome: ev.final_outcome || state.finalOutcome
        }
        
        // Finalize any lingering streaming messages
        updates.messages = state.messages.map(m => m.status === "streaming" ? { ...m, status: "completed" } : m)
        
        set(updates)
        console.log(`[ChatStore] Run ended: ${ev.run_id}, status: ${ev.status}`)
    },

    _setError: (err) => {
        toast.error(i18n.t("chat.errors.connection", { error: err }))
        set({ status: "error" })
    },
}))
