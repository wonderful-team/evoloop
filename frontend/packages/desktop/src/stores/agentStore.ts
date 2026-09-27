import i18n from "@evoloop/shared/i18n"
import { toast } from "sonner"
import { create } from "zustand"
import { AgentService } from "@/client"
import {
  appendMacroStep,
  macroThoughtText,
} from "@/components/Learning/macroRun"
import {
  AGENT_IDLE_STATUSES,
  HITL_ENDED_STATUSES,
  HITL_PENDING_STATUSES,
} from "./agent/hitlConstants"
import type { AgentState } from "./agent/types"
import { useChatStore } from "./chatStore"

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
  _thinkingBuffer: "",
  _flushTimeout: null,
  streamingSteps: [],

  // --- Live subagent panel (started / completed / failed / cancelled) ---
  subagents: [],
  activeSubagentDetail: null,
  // --- Live A2A delegation panel (started / completed / failed / timeout / cancelled) ---
  a2aDelegations: [],
  activeA2ADetail: null,
  macroSteps: [],

  isConnected: false,
  connectionStatus: "disconnected",
  _finalizedRunIds: new Set<string>(),

  // Internal Handlers
  _setConnectionStatus: (connected, status) => {
    const prevConnected = get().isConnected
    set({ isConnected: connected, connectionStatus: status })
    if (connected && !prevConnected) {
      const chatState = useChatStore.getState()
      const threadId = chatState.threadId
      if (threadId) {
        console.log(
          "[AgentStore] SSE Reconnected, fetching latest history and activity...",
        )
        // Always fetch history to catch up on missed messages during disconnection
        chatState.fetchHistory(threadId)
        chatState.fetchActivity(threadId)

        // run_end 可能在断线期间丢失（后端重启/崩溃）——重连后短暂观察。
        // 裁决依据 = 活动快照（AgentActivity，后端真实运行状态），而非
        // "消息流里有没有 streaming 行"的启发式：LLM 长思考期本来就没有
        // streaming 行，曾致 running 被误判 idle → 停止按钮消失、无法主动
        // 停止（快照 running 则保持 running，不误杀）。
        const st = get().status
        if (st === "running" || st === "summarizing") {
          setTimeout(async () => {
            if (get().status !== "running" && get().status !== "summarizing")
              return
            const cur = useChatStore.getState()
            if (!cur.threadId) return
            await cur.fetchHistory(cur.threadId)
            await cur.fetchActivity(cur.threadId) // _setActivitySnapshot 以后端真实状态归一化并裁决
            const stillRunning =
              get().status === "running" || get().status === "summarizing"
            const stillStreaming = useChatStore
              .getState()
              .messages.some(
                (m) =>
                  m.status === "streaming" ||
                  m.status === "running" ||
                  m.status === "pending",
              )
            if (!stillRunning && !stillStreaming) {
              set({ status: "idle" })
              toast.info(i18n.t("chat.errors.reconnectedIdle"))
            }
          }, 5000)
        }
      }
    }
  },

  _appendThinking: (text) => {
    const state = get()
    const newBuffer = (state._thinkingBuffer || "") + text

    if (state._flushTimeout) {
      set({ _thinkingBuffer: newBuffer })
      return
    }

    const timeout = setTimeout(() => {
      set((currentState) => {
        const thinkingBuffer = currentState._thinkingBuffer
        if (!thinkingBuffer) return { _flushTimeout: null }

        return {
          streamingThinking: currentState.streamingThinking + thinkingBuffer,
          _thinkingBuffer: "",
          _flushTimeout: null,
        }
      })
    }, 50)

    set({ _thinkingBuffer: newBuffer, _flushTimeout: timeout })
  },

  _appendMacroStep: (payload) => {
    const text = macroThoughtText(payload)
    if (!text) return
    set((state) => ({
      macroSteps: appendMacroStep(state.macroSteps, text, Date.now()),
    }))
  },

  _setActivitySnapshot: (data) => {
    const newStatus = data.status || "unknown"
    // 未知状态不裁决（保持现状态不动）：快照词汇漂移/缺失时绝不误杀
    // running——停止按钮因此不会因接口形状变化而消失（严格 fail-safe）。
    const KNOWN_ACTIVITY_STATUSES = new Set([
      ...HITL_ENDED_STATUSES,
      ...HITL_PENDING_STATUSES,
      "running",
      "idle",
      "stopping",
      "stopped",
      "quota_exhausted",
      "error",
    ])
    if (!KNOWN_ACTIVITY_STATUSES.has(newStatus)) return
    let normalized = newStatus
    if (HITL_ENDED_STATUSES.includes(newStatus)) normalized = "idle"
    else if (newStatus === "stopping") normalized = "stopped"
    else if (HITL_PENDING_STATUSES.includes(newStatus))
      normalized = "interrupted"

    let humanReq = data.human_request || null
    if (humanReq) {
      let reqData = humanReq.data || humanReq
      if (reqData && reqData.type === "human_request" && reqData.request_type) {
        reqData = {
          ...reqData,
          type: reqData.request_type,
        }
      }
      // Phase D: A2A 回调等待由"A2A 委派"面板呈现，不作为交互式 human request 卡片。
      if (
        reqData &&
        (reqData.type === "a2a_callback" ||
          reqData.request_type === "a2a_callback")
      ) {
        humanReq = null
      } else {
        humanReq = reqData
      }
    }

    set({
      status: normalized,
      artifacts: data.artifacts || [],
      finalOutcome: data.final_outcome || null,
      activeMemories: data.active_memories || [],
      agentState: data.agent_state || null,
      subagents: data.subagents || [],
      humanRequest: humanReq,
    })

    if (humanReq) {
      useChatStore.getState()._attachHumanRequestToLastMessage(humanReq)
    }
  },

  _addArtifact: (ev) => {
    const data = ev.data || ev
    set((state) => {
      const idx = state.artifacts.findIndex(
        (a) => a.id === data.id || a.name === data.name,
      )
      const list = [...state.artifacts]
      if (idx >= 0) list[idx] = { ...list[idx], ...data }
      else list.push(data)
      return { artifacts: list }
    })
  },

  _updateStatus: (ev) => {
    const raw = ev.status || ev
    if (raw === "quota_exhausted") return set({ status: "quota_exhausted" })
    if (raw === "error") {
      // 后端 StatusEvent(error)：带 message 时兜底呈现（正常错误应走
      // QuotaExhausted/LLMAuth 专用事件或 system 消息块，此处仅防御）
      if (ev.message) toast.error(ev.message)
      return set({ status: "error" })
    }

    let normalized = raw
    if (HITL_ENDED_STATUSES.includes(raw)) normalized = "idle"
    else if (raw === "stopping") normalized = "stopped"
    else if (HITL_PENDING_STATUSES.includes(raw)) normalized = "interrupted"

    const state = get()
    const isTerminal = AGENT_IDLE_STATUSES.includes(normalized)

    // If a terminal status refers to an already-finalized run, skip the side
    // effects (finalize, clear buffers) but still update display state.
    const runId = ev.run_id || state.agentState?.run_id || "unknown"
    const alreadyFinalized = isTerminal && state._finalizedRunIds.has(runId)

    const updates: Partial<AgentState> = {
      status: normalized,
      activeMemories: ev.active_memories || state.activeMemories,
      agentState: ev.agent_state || state.agentState,
    }

    if (isTerminal && !alreadyFinalized) {
      updates.streamingThinking = ""
      updates._thinkingBuffer = ""
    }

    const chatStore = useChatStore.getState()

    if (normalized === "idle" && !alreadyFinalized) {
      chatStore._finalizeMessages()
    }
    if (
      state.status === "running" &&
      normalized !== "running" &&
      !alreadyFinalized
    ) {
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
    let data = req.data || req
    if (data && data.type === "human_request" && data.request_type) {
      data = {
        ...data,
        type: data.request_type,
      }
    }
    // Phase D: A2A 回调等待由"A2A 委派"面板呈现，仅保留 interrupted 状态，
    // 不挂交互式 human request 卡片（避免双重视觉）。
    if (
      data &&
      (data.type === "a2a_callback" || data.request_type === "a2a_callback")
    ) {
      set({ status: "interrupted" })
      return
    }
    set({ humanRequest: data, status: "interrupted" })
    useChatStore.getState()._attachHumanRequestToLastMessage(data)
  },

  _setQuotaExhausted: (info) =>
    set({
      status: "quota_exhausted",
      quotaExhaustedInfo: {
        title: info.title || i18n.t("chat.quotaExhausted.title"),
        message: info.message || i18n.t("chat.quotaExhausted.message"),
        hint: info.hint || i18n.t("chat.quotaExhausted.hint"),
        actionText: info.actionText || i18n.t("chat.quotaExhausted.action"),
      },
    }),

  /**
   * 服务端错误统一分发中枢（对齐后端 ErrorEmitter 单出口契约）：
   * quota_exhausted → 续费横幅；llm_auth_error → toast+设置跳转；
   * auth_expired → toast；其余 → 连接错误 toast。
   * 新增错误类型只在此追加分支，UI 组件不感知事件类型。
   */
  _handleServerError: (ev: {
    type: string
    title?: string
    message?: string
    hint?: string
  }) => {
    switch (ev.type) {
      case "quota_exhausted":
        get()._setQuotaExhausted(ev)
        break
      case "llm_auth_error":
        get()._setLLMAuthError(ev)
        break
      case "auth_expired":
        toast.error(ev.message || i18n.t("chat.errors.unauthorized"), {
          duration: 8000,
        })
        set({ status: "error" })
        break
      default:
        get()._setError(ev.message || ev.type)
    }
  },

  _setLLMAuthError: (ev) => {
    toast.error(ev.title || i18n.t("chat.llmAuthError"), {
      description: ev.message || i18n.t("chat.llmAuthErrorDesc"),
      action: {
        label: i18n.t("chat.goToSettings"),
        onClick: () => {
          window.location.hash = "#/settings"
        },
      },
      duration: 10000,
    })
    set({ status: "error" })
  },

  _setAgentState: (ev) =>
    set({
      agentState: {
        mode: ev.mode,
        task_name: ev.task_name,
        task_status: ev.task_status,
        activeSkills: ev.active_skills ?? null,
      },
    }),

  _updateProgress: (ev) =>
    set((state) => ({
      agentState: state.agentState
        ? { ...state.agentState, task_status: ev.message }
        : {
            mode: "PLANNING",
            task_name: i18n.t("chat.agentRunning"),
            task_status: ev.message,
          },
    })),

  _handleRunStart: (ev) => {
    set({
      status: "running",
      streamingThinking: "",
      _thinkingBuffer: "",
      finalOutcome: null,
      macroSteps: [],
      // New run begins; clear finalized set so terminal events for this run
      // are processed exactly once.
      _finalizedRunIds: new Set<string>(),
    })
    useChatStore.getState()._handleRunStart(ev)
    console.log(`[AgentStore] Run started: ${ev.run_id}`)
  },

  _handleRunEnd: (ev) => {
    const state = get()
    const runId = ev.run_id || "unknown"

    // Terminal event deduplication: ignore duplicate run_end for the same run.
    if (state._finalizedRunIds.has(runId)) {
      console.log(`[AgentStore] Duplicate run_end ignored: ${runId}`)
      return
    }

    const normalized =
      ev.status === "done" ||
      ev.status === "failed" ||
      ev.status === "cancelled"
        ? "idle"
        : (ev.status as any) || "idle"

    const nextFinalized = new Set(state._finalizedRunIds)
    nextFinalized.add(runId)

    const updates: Partial<AgentState> = {
      status: normalized,
      finalOutcome: ev.final_outcome || state.finalOutcome,
      agentState: state.agentState
        ? { ...state.agentState, activeSkills: null }
        : state.agentState,
      _finalizedRunIds: nextFinalized,
    }

    // failed 收尾：具体错误由 system 消息块/专用事件承载，这里给轻量提示
    if (ev.status === "failed") {
      toast.error(i18n.t("chat.errors.runFailed"), { duration: 6000 })
    }

    useChatStore.getState()._finalizeMessages()
    set(updates)
    console.log(`[AgentStore] Run ended: ${runId}, status: ${ev.status}`)
  },

  _handleSessionCompleted: (ev) => {
    const state = get()
    const runId = ev.data?.run_id || "unknown"

    if (state._finalizedRunIds.has(runId)) {
      console.log(`[AgentStore] Duplicate session_completed ignored: ${runId}`)
      return
    }

    const nextFinalized = new Set(state._finalizedRunIds)
    nextFinalized.add(runId)

    set({
      status: "idle",
      finalOutcome: ev.data?.outcome || state.finalOutcome,
      _finalizedRunIds: nextFinalized,
    })
    useChatStore.getState()._finalizeMessages()
    console.log(
      `[AgentStore] Session completed - final state cleaned and finalized: run_id=${runId}`,
    )
  },

  _handleSubagentLifecycle: (ev) => {
    if (!ev || !ev.subagent_thread_id) return
    const entry = {
      subagent_id: ev.subagent_id,
      subagent_thread_id: ev.subagent_thread_id,
      instruction: ev.instruction || "",
      status: ev.status,
      result: ev.result || "",
      error: ev.error || null,
    }
    set((state) => {
      const idx = state.subagents.findIndex(
        (s) => s.subagent_thread_id === ev.subagent_thread_id,
      )
      if (idx >= 0) {
        const list = [...state.subagents]
        list[idx] = { ...list[idx], ...entry }
        return { subagents: list }
      }
      return { subagents: [...state.subagents, entry] }
    })
  },

  _handleA2ALifecycle: (ev) => {
    if (!ev || !ev.task_id) return
    const entry = {
      task_id: ev.task_id,
      target_device_key: ev.target_device_key || "",
      target_device_name: ev.target_device_name || "",
      instruction: ev.instruction || "",
      status: ev.status,
      result: ev.result || "",
      error: ev.error || null,
    }
    set((state) => {
      const idx = state.a2aDelegations.findIndex(
        (d) => d.task_id === ev.task_id,
      )
      if (idx >= 0) {
        const list = [...state.a2aDelegations]
        list[idx] = { ...list[idx], ...entry }
        return { a2aDelegations: list }
      }
      return { a2aDelegations: [...state.a2aDelegations, entry] }
    })
  },

  _setError: (err) => {
    toast.error(i18n.t("chat.errors.connection", { error: err }))
    set({ status: "error" })
  },

  _openSubagentDetail: (threadId) => set({ activeSubagentDetail: threadId }),
  _closeSubagentDetail: () => set({ activeSubagentDetail: null }),

  _openA2ADetail: (taskId) => set({ activeA2ADetail: taskId }),
  _closeA2ADetail: () => set({ activeA2ADetail: null }),

  clearContent: () =>
    set({
      status: "idle",
      finalOutcome: null,
      activeMemories: [],
      artifacts: [],
      humanRequest: null,
      quotaExhaustedInfo: null,
      agentState: null,
      subagents: [],
      activeSubagentDetail: null,
      a2aDelegations: [],
      activeA2ADetail: null,
      streamingThinking: "",
      _thinkingBuffer: "",
      streamingSteps: [],
    }),

  // --- Actions ---
  stopAgent: async () => {
    const threadId = useChatStore.getState().threadId
    if (!threadId) return
    try {
      await AgentService.stopChat({
        requestBody: { thread_id: threadId, message: "" },
      })
      set({ status: "stopped" })
    } catch (_e) {
      toast.error(i18n.t("chat.errors.stopAgentFailed"))
    }
  },

  resumeAgent: async (userInput, grantMode) => {
    const threadId = useChatStore.getState().threadId
    if (!threadId) return
    try {
      await AgentService.resumeChat({
        requestBody: {
          thread_id: threadId,
          user_input: userInput,
          grant_mode: grantMode,
        },
      })
      set({ status: "running", humanRequest: null })
    } catch (_e) {
      toast.error(i18n.t("chat.errors.resumeAgentFailed"))
    }
  },

  cancelHumanRequest: async (reason) => {
    const threadId = useChatStore.getState().threadId
    if (!threadId) return
    try {
      await AgentService.cancelHitlRequest({
        requestBody: { thread_id: threadId, reason },
      })
      set({ humanRequest: null, status: "idle" })
      useChatStore.getState()._clearHumanRequest()
    } catch (_e) {
      toast.error(i18n.t("chat.errors.cancelRequestFailed"))
    }
  },
}))
