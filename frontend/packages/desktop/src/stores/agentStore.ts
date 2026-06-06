import { create } from "zustand"
import { AgentState } from "./agent/types"
import { toast } from "sonner"
import i18n from "@evoloop/shared/i18n"
import { useChatStore } from "./chatStore"
import { AgentService } from "@/client"

export const useAgentStore = create<AgentState>((set, get) => ({
    // --- Data ---
    status: "idle",
    finalOutcome: null,
    activeMemories: [],
    artifacts: [],
    humanRequest: null,
    quotaExhaustedInfo: null,
    agentState: null,

    // --- Live Buffer (For Right Panel) ---
    streamingThinking: "",
    streamingSteps: [],

    isConnected: false,
    connectionStatus: "disconnected",

    // Internal Handlers
    _setConnectionStatus: (connected, status) => {
        const prevConnected = get().isConnected
        set({ isConnected: connected, connectionStatus: status })
        if (connected && !prevConnected) {
            const chatState = useChatStore.getState()
            const threadId = chatState.threadId
            if (threadId) {
                console.log("[AgentStore] SSE Reconnected, fetching latest history and activity...")
                if (chatState.messages.length === 0) {
                    chatState.fetchHistory(threadId)
                }
                chatState.fetchActivity(threadId)
            }
        }
    },

    _appendThinking: (text) => {
        // Just used for the Activity tab, actual message buffering is in chatStore
        set(state => ({ streamingThinking: state.streamingThinking + text }))
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
        else if (raw === "waiting_human") normalized = "interrupted"

        const state = get()
        const updates: Partial<AgentState> = {
            status: normalized,
            activeMemories: ev.active_memories || state.activeMemories,
            agentState: ev.agent_state || state.agentState
        }
        
        if (["idle", "stopped", "interrupted"].includes(normalized)) {
            updates.streamingThinking = ""
        }
        
        const chatStore = useChatStore.getState()

        if (normalized === "idle") {
            chatStore._finalizeMessages()
        }
        if (state.status === "running" && normalized !== "running") {
            chatStore._finalizeMessages()
        }
        if (normalized !== "interrupted" && state.humanRequest) {
            updates.humanRequest = null
            chatStore._clearHumanRequest()
        }
        set(updates)
    },

    _setHumanRequest: (req) => {
        if (!req) return
        if (req.action === "clear") {
            set({ humanRequest: null, status: "idle" })
            useChatStore.getState()._clearHumanRequest()
            return
        }
        const data = req.data || req
        set({ humanRequest: data, status: "interrupted" })
        useChatStore.getState()._attachHumanRequestToLastMessage(data)
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
            task_status: ev.task_status,
            activeSkills: ev.active_skills ?? null
        }
    }),

    _updateProgress: (ev) => set(state => ({
        agentState: state.agentState
            ? { ...state.agentState, task_status: ev.message }
            : { mode: "PLANNING", task_name: "Agent Running", task_status: ev.message }
    })),

    _handleRunStart: (ev) => {
        set({
            status: "running",
            streamingThinking: "",
            finalOutcome: null
        })
        useChatStore.getState()._handleRunStart(ev)
        console.log(`[AgentStore] Run started: ${ev.run_id}`)
    },

    _handleRunEnd: (ev) => {
        const state = get()
        const normalized = (ev.status === "done" || ev.status === "failed" || ev.status === "cancelled") ? "idle" : (ev.status as any || "idle")

        const updates: Partial<AgentState> = {
            status: normalized,
            finalOutcome: ev.final_outcome || state.finalOutcome,
            agentState: state.agentState
                ? { ...state.agentState, activeSkills: null }
                : state.agentState
        }

        useChatStore.getState()._finalizeMessages()
        set(updates)
        console.log(`[AgentStore] Run ended: ${ev.run_id}, status: ${ev.status}`)
    },

    _handleSessionCompleted: (ev) => {
        const state = get()
        set({
            status: "idle",
            finalOutcome: ev.data?.outcome || state.finalOutcome,
        })
        useChatStore.getState()._finalizeMessages()
        console.log(`[AgentStore] Session completed - final state cleaned and finalized: run_id=${ev.data?.run_id}`)
    },

    _setError: (err) => {
        toast.error(i18n.t("chat.errors.connection", { error: err }))
        set({ status: "error" })
    },

    clearContent: () => set({
        status: "idle",
        finalOutcome: null,
        activeMemories: [],
        artifacts: [],
        humanRequest: null,
        quotaExhaustedInfo: null,
        agentState: null,
        streamingThinking: "",
        streamingSteps: []
    }),

    // --- Actions ---
    stopAgent: async () => {
        const threadId = useChatStore.getState().threadId
        if (!threadId) return
        try {
            await AgentService.stopChat({ requestBody: { thread_id: threadId, message: "" } })
            set({ status: "stopped" })
        } catch (e) {
            toast.error("Failed to stop agent")
        }
    },

    resumeAgent: async (userInput) => {
        const threadId = useChatStore.getState().threadId
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
        const threadId = useChatStore.getState().threadId
        if (!threadId) return
        try {
            await AgentService.cancelHitlRequest({
                requestBody: { thread_id: threadId, reason }
            })
            set({ humanRequest: null, status: "idle" })
            useChatStore.getState()._clearHumanRequest()
        } catch (e) {
            toast.error("Failed to cancel request")
        }
    }
}))
