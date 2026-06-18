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
    // --- Core Actions ---
    setThread: async (threadId, projectId, skillIds) => {
      const currentThreadId = get().threadId
      set({
        threadId,
        projectId,
        skillIds: skillIds || [],
        ...(currentThreadId !== threadId
          ? {
              messages: [],
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
        })

        // Fetch history and activity first, then connect SSE
        Promise.all([
          get().fetchHistory(threadId),
          get().fetchActivity(threadId),
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
        toast.error(
          i18n.t("chat.errors.fetchHistoryFailed", "加载历史消息失败"),
        )
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
        toast.error(
          i18n.t("chat.errors.loadMoreHistoryFailed", "加载更多历史消息失败"),
        )
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
        toast.error("Failed to rewind conversation")
        useAgentStore.setState({ status: "idle" })
      }
    },
    optimisticTruncate: (messageId) => {
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
        // Keep the target human message, remove its AI responses and everything after
        set({ messages: currentMessages.slice(0, targetHumanIndex + 1) })
      }
      return snapshot
    },

    restoreSnapshot: (snapshot) => {
      set({ messages: snapshot })
    },

    sendMessage: async (content, pickedFiles, skillIds) => {
      const { threadId, projectId, skillIds: stateSkillIds } = get()
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
          } else if (res.message_id) {
            // Existing thread: replace optimistic temp ID with real backend ID
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
      const { threadId, messages } = get()
      set((state) => {
        useAgentStore.setState({ streamingThinking: "" })
        return commitThinkingBuffer(state)
      })
      const humanReq = tryParseHumanRequest(raw)
      if (!threadId || (raw.role === "system" && !humanReq)) return

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

      const msg = normalizeMessage(raw)

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
