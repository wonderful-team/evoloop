import i18n from "@evoloop/shared/i18n"
import { toast } from "sonner"
import { create } from "zustand"
import { AgentService, ConversationsService } from "@/client"
import type { Message } from "@/components/Chat/ChatMessageItem"
import { ChatConnection } from "@/lib/ChatConnection"
import { llmPlatformService } from "@/services/llmPlatform"
import { useAgentStore } from "./agentStore"
import { useChangesetStore } from "./changesetStore"
import {
  commitThinkingBuffer,
  normalizeMessage,
  tryParseHumanRequest,
} from "./chat/helpers"
import type { ActivitySnapshot, ChatState } from "./chat/types"
import { useProjectStore } from "./projectStore"

// ---------------------------------------------------------------------------
// Terminal input batching
// Module-level state so the debounce timer survives re-renders / store updates.
// ---------------------------------------------------------------------------
const TERMINAL_HISTORY_BUFFER_MAX = 512 * 1024 // 512 KB in chars (≈ bytes for ASCII/UTF-8)
const RAW_INPUT_DEBOUNCE_MS = 16 // one animation frame — imperceptible to users

let _rawInputBuffer = "" // pending characters not yet sent
let _rawInputTimer: ReturnType<typeof setTimeout> | null = null
let _rawInputThreadId: string | null = null // thread the buffer belongs to

/** Flush the accumulated raw-input buffer as a single POST, then clear it. */
async function _flushRawInput() {
  _rawInputTimer = null
  const text = _rawInputBuffer
  const threadId = _rawInputThreadId
  _rawInputBuffer = ""
  _rawInputThreadId = null
  if (!text || !threadId) return
  const currentProject = useProjectStore.getState().currentProject
  const activeProjectId =
    currentProject?.id ?? useChatStore.getState().projectId
  try {
    await fetch(`/api/v1/conversations/${threadId}/terminal/input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, project_id: activeProjectId }),
    })
  } catch (e) {
    console.error("[ChatStore] sendRawTerminalInput flush error", e)
  }
}

export const useChatStore = create<ChatState>((set, get) => {
  const createFlushTimeout = (messageId?: string) => {
    return setTimeout(() => {
      set((currentState) => {
        const streamBuffer = currentState._streamBuffer
        const thinkingBuffer = currentState._thinkingBuffer
        if (!streamBuffer && !thinkingBuffer) return { _flushTimeout: null }

        const msgs = [...currentState.messages]
        const targetIdx = messageId
          ? msgs.findIndex((m) => String(m.id) === String(messageId))
          : -1

        if (targetIdx >= 0) {
          const target = { ...msgs[targetIdx] }
          if (streamBuffer)
            target.content = (target.content || "") + streamBuffer
          if (thinkingBuffer)
            target.thinking = (target.thinking || "") + thinkingBuffer
          target.status = "streaming"
          msgs[targetIdx] = target
        } else {
          const last = msgs[msgs.length - 1]
          if (!last || last.role !== "ai" || last.status !== "streaming") {
            msgs.push({
              id: messageId || `placeholder-${Date.now()}`,
              role: "ai",
              content: streamBuffer || "",
              thinking:
                useAgentStore.getState().streamingThinking +
                (thinkingBuffer || ""),
              status: "streaming",
              timestamp: new Date().toISOString(),
              changeset_count: 0,
            })
          } else {
            const lastUpdated = { ...last }
            if (streamBuffer)
              lastUpdated.content = (lastUpdated.content || "") + streamBuffer
            if (thinkingBuffer)
              lastUpdated.thinking =
                (lastUpdated.thinking || "") + thinkingBuffer
            lastUpdated.status = "streaming"
            msgs[msgs.length - 1] = lastUpdated
          }
        }

        if (streamBuffer) {
          useAgentStore.setState({ streamingThinking: "" })
        }

        return {
          messages: msgs,
          _streamBuffer: "",
          _thinkingBuffer: "",
          _flushTimeout: null,
        }
      })
    }, 50)
  }

  return {
    // --- Initial State ---
    threadId: null,
    projectId: null,
    skillIds: [],
    sessionGoal: null,
    messages: [],
    hasMoreHistory: false,
    isLoadingHistory: false,
    firstMessageId: null,
    totalMessageCount: null,
    selectedModel: llmPlatformService.getSelectedModel(),
    _streamBuffer: "",
    _thinkingBuffer: "",
    _flushTimeout: null,
    // --- Terminal Mode Initial State ---
    isTerminalMode: false,
    terminalHistoryBuffer: "",
    activeTasks: {},
    // --- Core Actions ---
    setThread: async (threadId, projectId, skillIds) => {
      const currentThreadId = get().threadId
      const isUpgradingNewConversation =
        currentThreadId === null &&
        threadId !== null &&
        get().messages.length > 0

      set({
        threadId,
        projectId,
        skillIds: skillIds || [],
        ...(currentThreadId !== threadId
          ? {
              messages: isUpgradingNewConversation ? get().messages : [],
              hasMoreHistory: false,
              firstMessageId: null,
              totalMessageCount: null,
              isLoadingHistory: false,
            }
          : {}),
      })

      if (threadId) {
        useChangesetStore.getState().loadViewedChanges(threadId)

        // Register callbacks once
        const store = get()
        const agentStore = useAgentStore.getState()
        ChatConnection.getInstance().setCallbacks({
          onConnectionChange: agentStore._setConnectionStatus,
          onToken: (token, messageId) => store._appendToken(token, messageId),
          onActivity: agentStore._setActivitySnapshot,
          onSystemLog: (ev) => {
            if (ev?.event === "macro_thought") agentStore._appendMacroStep(ev)
          },
          onArtifact: agentStore._addArtifact,
          onStatus: agentStore._updateStatus,
          onHumanRequest: agentStore._setHumanRequest,
          onMessage: store._appendMessage,
          onThinking: (ev) => {
            agentStore._appendThinking(ev.content)
            store._appendThinking(ev.content, ev.message_id)
          },
          onProgress: (ev) => agentStore._updateProgress(ev),
          onAgentState: (ev) => agentStore._setAgentState(ev),
          onQuotaExhausted: agentStore._setQuotaExhausted,
          onLLMAuthError: agentStore._setLLMAuthError,
          onRunStart: agentStore._handleRunStart,
          onRunEnd: agentStore._handleRunEnd,
          onSessionCompleted: agentStore._handleSessionCompleted,
          onPlanUpdated: () => {
            window.dispatchEvent(new CustomEvent("chat-plan-updated"))
          },
          onChangesetUpdated: () => {
            if (threadId) {
              useChangesetStore.getState().fetchChangeset(threadId)
              window.dispatchEvent(
                new CustomEvent("chat-changeset-updated", {
                  detail: { threadId },
                }),
              )
            }
          },
          onAuthExpired: (ev) => toast.error(ev.message),
          onError: agentStore._setError,
          onUnauthorized: () => {
            useAgentStore.setState({ status: "unauthorized" })
          },
          // Terminal / BackgroundTask SSE callbacks
          onTaskOutput: (ev) => {
            get().appendTerminalOutput(ev.output)
          },
          onTaskStatus: (ev) => {
            const { task, action } = ev
            if (["created", "started", "updated"].includes(action)) {
              get().updateActiveTask(task)
            } else if (
              ["completed", "failed", "cancelled", "timeout"].includes(action)
            ) {
              get().removeActiveTask(task.task_id)
            }
          },
        })

        // Fetch history and activity first, then connect SSE
        Promise.all([
          get().fetchHistory(threadId),
          get().fetchActivity(threadId),
          get().fetchActiveTasks(threadId),
          useChangesetStore.getState().fetchChangeset(threadId),
          useChangesetStore.getState().loadViewedChanges(threadId),
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
        set((state) => {
          const serverIds = new Set(msgs.map((m) => String(m.id)))
          const activeRunId = (useAgentStore.getState().agentState as any)
            ?.run_id

          const localMsgsToKeep = state.messages.filter((m) => {
            const idStr = String(m.id)
            if (serverIds.has(idStr)) return false // Use server's version
            if (idStr.startsWith("temp-") || idStr.startsWith("placeholder-"))
              return true
            if (m.status === "streaming") {
              // Only keep streaming messages if they match the active run
              if (activeRunId && (m as any).run_id === activeRunId) return true
              // Or if they don't have a run_id but the agent is actively running
              if (!activeRunId && useAgentStore.getState().status === "running")
                return true
            }
            return false
          })

          const merged = [...msgs, ...localMsgsToKeep].sort(
            (a, b) =>
              new Date(a.timestamp || 0).getTime() -
              new Date(b.timestamp || 0).getTime(),
          )
          return {
            messages: merged,
            hasMoreHistory: !!data.has_more,
            firstMessageId: data.first_id || null,
            totalMessageCount: data.total_count || data.total || merged.length,
          }
        })
      } catch (e) {
        console.error("[ChatStore] Fetch history failed", e)
        toast.error(i18n.t("chat.errors.fetchHistoryFailed"))
      } finally {
        set({ isLoadingHistory: false })
      }
    },

    fetchActivity: async (threadId) => {
      try {
        const data = (await ConversationsService.getThreadActivity({
          threadId,
        })) as any as ActivitySnapshot
        useAgentStore.getState()._setActivitySnapshot(data)
      } catch (e) {
        console.error("[ChatStore] Fetch activity failed", e)
      }
    },

    loadMoreHistory: async () => {
      const {
        threadId,
        firstMessageId: cursorId,
        hasMoreHistory,
        isLoadingHistory,
        messages,
      } = get()
      if (!threadId || !hasMoreHistory || isLoadingHistory) return
      // Fallback: use oldest message ID as cursor if firstMessageId is null
      const firstMessageId =
        cursorId || (messages.length > 0 ? String(messages[0].id) : null)
      if (!firstMessageId) return

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
        toast.error(i18n.t("chat.errors.loadMoreHistoryFailed"))
      } finally {
        set({ isLoadingHistory: false })
      }
    },

    rewindToMessage: async (messageId) => {
      const { threadId } = get()
      if (!threadId) return
      try {
        useAgentStore.setState({ status: "running" })
        await ConversationsService.rewindConversation({
          threadId,
          requestBody: {
            message_id: messageId,
            revert_files: true,
          },
        })
        // Optimization: Truncate locally instead of full refetch
        const index = get().messages.findIndex((m) => m.id === messageId)
        if (index !== -1) {
          set({ messages: get().messages.slice(0, index) })
        }
        // Trigger changeset refresh as files might have reverted
        useChangesetStore.getState().fetchChangeset(threadId)
        useAgentStore.setState({ status: "idle" })
      } catch (_e) {
        toast.error(i18n.t("chat.errors.rewindFailed"))
        useAgentStore.setState({ status: "idle" })
      }
    },
    optimisticTruncate: (messageId, removeHuman = false) => {
      const state = get()
      const currentMessages = state.messages
      const snapshot = [...currentMessages]
      let targetHumanIndex = -1

      if (messageId) {
        const targetIndex = currentMessages.findIndex(
          (m) => String(m.id) === String(messageId),
        )
        if (targetIndex !== -1) {
          // Find the target message itself (if it's human) or the closest preceding human message
          for (let i = targetIndex; i >= 0; i--) {
            if (currentMessages[i].role === "human") {
              targetHumanIndex = i
              break
            }
          }
        }
      } else {
        const lastHumanIndex = [...currentMessages]
          .reverse()
          .findIndex((m) => m.role === "human")
        if (lastHumanIndex !== -1) {
          targetHumanIndex = currentMessages.length - 1 - lastHumanIndex
        }
      }

      if (targetHumanIndex !== -1) {
        // Truncate based on removeHuman flag
        const endIndex = removeHuman ? targetHumanIndex : targetHumanIndex + 1
        set({ messages: currentMessages.slice(0, endIndex) })
      }
      return snapshot
    },

    restoreSnapshot: (snapshot) => {
      set({ messages: snapshot })
    },

    sendMessage: async (content, pickedFiles, skillIds) => {
      const {
        threadId,
        projectId: storeProjectId,
        skillIds: stateSkillIds,
      } = get()
      const currentProject = useProjectStore.getState().currentProject
      const projectId = currentProject?.id ?? storeProjectId
      if (projectId === null) return

      const pickedSkillIds = (pickedFiles || [])
        .filter((f) => f.type === "skill" && f.metadata?.skill_id)
        .map((f) => Number(f.metadata.skill_id))

      const activeSkillIds = Array.from(
        new Set([
          ...(skillIds && skillIds.length > 0 ? skillIds : stateSkillIds),
          ...pickedSkillIds,
        ]),
      )

      // Optimistic update
      const tempId = `temp-${Date.now()}`
      const mappedReferences = (pickedFiles || []).map((a) => ({
        id: a.id,
        type: (a.type === "reference" ? "message" : a.type) as any,
        target_id: String(a.url),
        target_name: a.name,
        meta_data: a.metadata || {},
      }))

      const userMsg: Message = {
        id: tempId,
        role: "human",
        content,
        timestamp: new Date().toISOString(),
        status: "completed",
        changeset_count: 0,
        references: mappedReferences.length > 0 ? mappedReferences : undefined,
      }
      set((state) => ({
        messages: [...state.messages, userMsg],
      }))

      // Call agent store to update status
      useAgentStore
        .getState()
        ._handleRunStart({ run_id: "optimistic", goal: null })
      useAgentStore.setState((s: any) => ({
        quotaExhaustedInfo: null,
        agentState: s.agentState
          ? {
              ...s.agentState,
              activeSkills:
                activeSkillIds.length > 0
                  ? activeSkillIds.map((id: number) => ({
                      id,
                      name: "",
                      description: "",
                    }))
                  : null,
            }
          : s.agentState,
      }))

      try {
        // 发起动作前，兜底确保读通道 (SSE连接) 处于连通状态，防止后端重启或网络异常导致失联
        if (threadId) {
          ChatConnection.getInstance().connect(threadId)
        }

        const res: any = await AgentService.chatEndpoint({
          requestBody: {
            thread_id: threadId || undefined,
            project_id: projectId,
            skill_ids: activeSkillIds.length > 0 ? activeSkillIds : undefined,
            message: content,
            model: get().selectedModel || undefined,
            references:
              mappedReferences.length > 0 ? mappedReferences : undefined,
          },
        })

        if (res) {
          if (res.thread_id && !threadId) {
            // New thread: sync ID and re-init state/SSE
            console.log(`[ChatStore] Syncing new threadId: ${res.thread_id}`)
            await get().setThread(res.thread_id, projectId, activeSkillIds)
          }
          if (res.message_id) {
            // Existing thread or new thread: replace optimistic temp ID with real backend ID
            set((state) => ({
              messages: state.messages.map((m) =>
                m.id === tempId ? { ...m, id: res.message_id } : m,
              ),
            }))
          }
        }
      } catch (_e: any) {
        toast.error(i18n.t("chat.errors.sendFailed"))
        set((state) => ({
          messages: state.messages.filter((m) => m.id !== tempId),
        }))
        useAgentStore.getState()._handleRunEnd({ status: "idle" })
      }
    },

    clearContent: () => set({ messages: [] }),

    // --- Terminal Mode Actions ---

    setTerminalMode: (enabled) => set({ isTerminalMode: enabled }),

    appendTerminalOutput: (output) =>
      set((state) => {
        const combined = state.terminalHistoryBuffer + output
        // Cap at TERMINAL_HISTORY_BUFFER_MAX characters to prevent unbounded growth.
        // When over-limit, drop the oldest bytes so the most recent output is always
        // available, and write a marker line so users know data was trimmed.
        if (combined.length > TERMINAL_HISTORY_BUFFER_MAX) {
          const trimmed = combined.slice(
            combined.length - TERMINAL_HISTORY_BUFFER_MAX,
          )
          // Find the first newline so we don't start mid-line
          const firstNewline = trimmed.indexOf("\n")
          const safe =
            firstNewline !== -1 ? trimmed.slice(firstNewline + 1) : trimmed
          return {
            terminalHistoryBuffer: `\r\n\x1b[33m${i18n.t("chat.terminal.trimMarker")}\x1b[0m\r\n${safe}`,
          }
        }
        return { terminalHistoryBuffer: combined }
      }),

    updateActiveTask: (task) =>
      set((state) => ({
        activeTasks: { ...state.activeTasks, [task.task_id]: task },
      })),

    removeActiveTask: (taskId) =>
      set((state) => {
        const next = { ...state.activeTasks }
        delete next[taskId]
        return { activeTasks: next }
      }),

    fetchActiveTasks: async (threadId) => {
      try {
        const res = await fetch(
          `/api/v1/conversations/${threadId}/tasks/active`,
        )
        if (!res.ok) return
        const tasks: Array<{
          task_id: string
          task_type: string
          title: string
          status: string
          created_at: string
          output: string
          metadata: Record<string, any>
        }> = await res.json()

        if (!tasks.length) return

        // Rebuild activeTasks map and rehydrate terminalHistoryBuffer
        const activeTasks: Record<string, any> = {}
        let extraBuffer = ""
        for (const t of tasks) {
          activeTasks[t.task_id] = t
          if (t.output) {
            extraBuffer += t.output
          }
        }
        set((state) => ({
          activeTasks,
          // Only prepend history if the buffer is currently empty to avoid duplicates
          terminalHistoryBuffer:
            state.terminalHistoryBuffer.length === 0
              ? extraBuffer
              : state.terminalHistoryBuffer,
        }))
      } catch (e) {
        console.error("[ChatStore] fetchActiveTasks failed", e)
      }
    },

    sendTerminalCommand: async (command) => {
      let { threadId, projectId } = get()
      const currentProject = useProjectStore.getState().currentProject
      const activeProjectId = currentProject?.id ?? projectId
      if (!threadId) {
        if (activeProjectId === null) return
        threadId = crypto.randomUUID()
        await get().setThread(threadId, activeProjectId)
      }
      if (!command.trim()) return
      try {
        const res = await fetch(
          `/api/v1/conversations/${threadId}/terminal/execute`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command, project_id: activeProjectId }),
          },
        )
        if (!res.ok) {
          console.error(
            "[ChatStore] sendTerminalCommand failed",
            await res.text(),
          )
        }
      } catch (e) {
        console.error("[ChatStore] sendTerminalCommand error", e)
      }
    },

    sendRawTerminalInput: (text) => {
      const { threadId } = get()
      if (!threadId) return
      // Accumulate into the module-level buffer. If the incoming data belongs to a
      // different thread (shouldn't happen in practice) flush the old one first.
      if (_rawInputThreadId && _rawInputThreadId !== threadId) {
        if (_rawInputTimer) clearTimeout(_rawInputTimer)
        _flushRawInput()
      }
      _rawInputBuffer += text
      _rawInputThreadId = threadId
      // Reset the debounce window so rapid keystrokes are coalesced.
      if (_rawInputTimer) clearTimeout(_rawInputTimer)
      _rawInputTimer = setTimeout(_flushRawInput, RAW_INPUT_DEBOUNCE_MS)
    },

    setSelectedModel: (model) => {
      set({ selectedModel: model })
      llmPlatformService.setSelectedModel(model)
    },

    // --- Internal Handlers ---

    _appendThinking: (text: string, messageId?: string) => {
      const state = get()
      const newBuffer = (state._thinkingBuffer || "") + text

      if (state._flushTimeout) {
        set({ _thinkingBuffer: newBuffer })
        return
      }

      const timeout = createFlushTimeout(messageId)
      set({ _thinkingBuffer: newBuffer, _flushTimeout: timeout })
    },

    _appendToken: (tokens, messageId) => {
      const state = get()
      const newBuffer = (state._streamBuffer || "") + tokens

      if (state._flushTimeout) {
        set({ _streamBuffer: newBuffer })
        return
      }

      const timeout = createFlushTimeout(messageId)
      set({ _streamBuffer: newBuffer, _flushTimeout: timeout })
    },

    _finalizeMessages: () => {
      set((state) => {
        const updates: any = commitThinkingBuffer(state)
        updates.messages = (updates.messages || state.messages).map((m: any) =>
          m.status === "streaming" ? { ...m, status: "completed" } : m,
        )
        return updates
      })
    },

    _clearHumanRequest: () => {
      set((state) => ({
        messages: state.messages.map((m) =>
          m.humanRequest ? { ...m, humanRequest: undefined } : m,
        ),
      }))
    },

    _attachHumanRequestToLastMessage: (req) => {
      set((state) => {
        const msgs = [...state.messages]
        const lastAi = [...msgs].reverse().find((m) => m.role === "ai")
        if (lastAi) lastAi.humanRequest = req
        return { messages: msgs }
      })
    },

    _appendMessage: (raw) => {
      // SSE "message" events wrap MessageBlock in {type, action, data: MessageBlock}
      const payload = raw?.data ? raw.data : raw
      const { threadId, messages } = get()
      set((state) => {
        useAgentStore.setState({ streamingThinking: "" })
        return commitThinkingBuffer(state)
      })
      const humanReq = tryParseHumanRequest(payload)
      if (!threadId || (payload.role === "system" && !humanReq)) return

      if (humanReq) {
        set((state) => {
          const msgs = [...state.messages]
          const lastAi = [...msgs].reverse().find((m) => m.role === "ai")
          if (lastAi) lastAi.humanRequest = humanReq
          return { messages: msgs }
        })
        useAgentStore.getState()._setHumanRequest(humanReq)
        return
      }

      const msg = normalizeMessage(payload)

      // Replace optimistic human message (temp-*) with real backend ID
      if (msg.role === "human" && !msg.id.toString().startsWith("temp-")) {
        const tempIdx = messages.findIndex(
          (m) => m.role === "human" && String(m.id).startsWith("temp-"),
        )
        if (tempIdx >= 0) {
          set((state) => {
            const msgs = [...state.messages]
            msgs[tempIdx] = {
              ...msgs[tempIdx],
              ...msg,
              id: msg.id,
              references:
                msg.references && msg.references.length > 0
                  ? msg.references
                  : msgs[tempIdx].references,
            }
            return { messages: msgs }
          })
          return
        }
      }

      const existIdx = messages.findIndex((m) => m.id === msg.id)
      if (existIdx >= 0) {
        let shouldRefreshChangeset = false
        set((state) => {
          const msgs = [...state.messages]
          const ex = msgs[existIdx]
          const prevChangesetCount = ex.changeset_count || 0
          msgs[existIdx] = {
            ...ex,
            thinking: msg.thinking || ex.thinking,
            content:
              ex.status === "streaming"
                ? ex.content
                : msg.content || ex.content,
            status: msg.status || ex.status,
            // Merge references: prefer incoming if existing has none
            references:
              msg.references && msg.references.length > 0
                ? msg.references
                : ex.references,
            changeset_count:
              msg.changeset_count !== undefined
                ? msg.changeset_count
                : ex.changeset_count,
            has_file_operations:
              msg.has_file_operations !== undefined
                ? msg.has_file_operations
                : ex.has_file_operations,
          }
          if (
            msg.changeset_count &&
            msg.changeset_count > 0 &&
            prevChangesetCount === 0
          ) {
            shouldRefreshChangeset = true
          }
          return { messages: msgs }
        })
        if (shouldRefreshChangeset) {
          setTimeout(() => {
            const threadId = get().threadId
            if (threadId) {
              useChangesetStore.getState().fetchChangeset(threadId)
            }
          }, 500)
        }
        return
      }

      let streamIdx = -1
      for (let i = messages.length - 1; i >= 0; i--) {
        if (
          messages[i].role === msg.role &&
          messages[i].status === "streaming"
        ) {
          streamIdx = i // fallback: remember the last streaming message
          if (String(messages[i].id) === String(msg.id)) {
            break // exact match found
          }
        }
      }

      if (streamIdx >= 0) {
        let shouldRefreshChangeset = false
        set((state) => {
          const msgs = [...state.messages]
          const ex = msgs[streamIdx]
          const prevChangesetCount = ex.changeset_count || 0
          msgs[streamIdx] = {
            ...msg,
            content: msg.content || msgs[streamIdx].content,
            thinking: msg.thinking || msgs[streamIdx].thinking,
            status: msg.status || "completed",
          }
          if (
            msg.changeset_count &&
            msg.changeset_count > 0 &&
            prevChangesetCount === 0
          ) {
            shouldRefreshChangeset = true
          }
          return { messages: msgs }
        })
        if (shouldRefreshChangeset) {
          setTimeout(() => {
            const threadId = get().threadId
            if (threadId) {
              useChangesetStore.getState().fetchChangeset(threadId)
            }
          }, 500)
        }
        return
      }

      // Trigger changeset refresh if message has file changes
      if (msg.changeset_count && msg.changeset_count > 0) {
        setTimeout(() => {
          const threadId = get().threadId
          if (threadId) {
            useChangesetStore.getState().fetchChangeset(threadId)
          }
        }, 500)
      }

      set((state) => ({ messages: [...state.messages, msg] }))
    },

    _truncateMessages: (idx) =>
      set((state) => ({ messages: state.messages.slice(0, idx) })),
    _handleRunStart: (ev) => {
      set({
        sessionGoal: ev.goal || get().sessionGoal,
        _streamBuffer: "",
        _thinkingBuffer: "",
      })
    },
  }
})
