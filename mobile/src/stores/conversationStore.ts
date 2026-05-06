// 会话管理状态 Store

import { create } from 'zustand';
import { Conversation, ConversationHistoryResponse } from '@/types/conversation';
import { ChatMessage } from '@/types/conversation';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import * as conversationApi from '@/services/api/conversations';
import { isAuthError } from '@/utils/error';
import { adaptAgentMessages, adaptHistoryMessage, deduplicateMessages } from '@/utils/messageAdapter';

interface ConversationState {
  // 会话列表
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoadingConversations: boolean;
  hasMoreConversations: boolean;
  conversationsPage: number;

  // 当前激活的筛选条件（用于分页时保持一致）
  activeDeviceKey: string | undefined;
  activeProjectId: number | undefined;

  // 当前会话消息
  messages: ChatMessage[];
  isLoadingMessages: boolean;
  hasMoreMessages: boolean;
  firstMessageId: string | null;

  // 操作
  setCurrentConversation: (id: string | null, skipLoadMessages?: boolean) => void;
  loadConversations: (projectId?: number, refresh?: boolean, deviceKey?: string) => Promise<void>;
  loadMoreConversations: () => Promise<void>;
  createConversation: (projectId?: number, initialMessage?: string) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  loadMessages: (conversationId: string, refresh?: boolean) => Promise<void>;
  loadMoreMessages: (conversationId: string) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  updateLastMessage: (updates: Partial<ChatMessage>) => void;
  updateMessageStatus: (messageId: string, status: ChatMessage['status']) => void;
  clearMessages: () => void;
  clearConversations: () => void;

  // Rewind/Retry
  rewindConversation: (conversationId: string, request: { message_id: string; revert_files?: boolean }) => Promise<any>;
  retryConversation: (conversationId: string, request: { message_id: string; revert_files?: boolean }) => Promise<any>;

  // 添加到记忆
  addToMemory: (projectId: number, request: { name: string; description: string }) => Promise<any>;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  isLoadingConversations: false,
  hasMoreConversations: true,
  conversationsPage: 1,

  // 当前筛选条件初始为空，首次 loadConversations 时写入
  activeDeviceKey: undefined,
  activeProjectId: undefined,

  messages: [],
  isLoadingMessages: false,
  hasMoreMessages: true,
  firstMessageId: null,

  // 设置当前会话
  setCurrentConversation: (id, skipLoadMessages = false) => {
    const prevId = get().currentConversationId;

    set({
      currentConversationId: id,
      // 真正切换会话（从 A 到 B，且 A 不为 null）时才清空消息
      // 首次设置（null -> id）保留乐观更新的用户消息
      messages: prevId !== null && prevId !== id ? [] : get().messages,
      hasMoreMessages: true,
      firstMessageId: null,
    });

    // 如果设置了新会话，加载消息（可跳过，例如 Gateway 创建的会话 PHP 中不存在）
    if (id && !skipLoadMessages) {
      // 首次加载用 refresh=true，直接替换旧消息，避免并发追加导致重复
      get().loadMessages(id, true);
    }
  },

  // 加载会话列表
  // - refresh=true 时：重置页码并记录新的筛选条件
  // - refresh=false 时（加载更多）：沿用已记录的 activeDeviceKey/activeProjectId
  loadConversations: async (projectId, refresh = false, deviceKey) => {
    set({ isLoadingConversations: true });

    // 筛选条件是否发生了变化
    const { activeDeviceKey, activeProjectId, conversationsPage } = get();
    const filterChanged =
      deviceKey !== activeDeviceKey || projectId !== activeProjectId;

    // 有新筛选条件时强制 refresh，防止带旧页码混合数据
    const shouldRefresh = refresh || filterChanged;
    const page = shouldRefresh ? 1 : conversationsPage;

    // 写入当前筛选条件（refresh 时更新，保持 loadMore 与其一致）
    if (shouldRefresh) {
      set({
        activeDeviceKey: deviceKey,
        activeProjectId: projectId,
        conversations: [],
        conversationsPage: 1,
        hasMoreConversations: true,
      });
    }

    try {
      const response = await conversationApi.getConversations(projectId, page, 20, deviceKey);

      set({
        conversations: shouldRefresh
          ? response.conversations
          : [...get().conversations, ...response.conversations],
        hasMoreConversations: response.conversations.length === 20,
        conversationsPage: page + 1,
      });
    } catch (error) {
      // 认证错误已在 API client 中统一处理，不需要输出错误日志
      if (!isAuthError(error)) {
        console.error('加载会话列表失败:', error);
      }
    } finally {
      set({ isLoadingConversations: false });
    }
  },

  // 加载更多会话——自动沿用 activeDeviceKey / activeProjectId，无需调用方传参
  loadMoreConversations: async () => {
    if (!get().hasMoreConversations || get().isLoadingConversations) return;
    const { activeProjectId, activeDeviceKey } = get();
    await get().loadConversations(activeProjectId, false, activeDeviceKey);
  },

  // 创建新会话
  createConversation: async (projectId, initialMessage) => {
    const response = await conversationApi.createConversation({
      project_id: projectId,
      initial_message: initialMessage,
    });

    // 刷新会话列表（保持当前筛选条件）
    const { activeDeviceKey, activeProjectId } = get();
    await get().loadConversations(activeProjectId, true, activeDeviceKey);

    // 设置为当前会话
    set({ currentConversationId: response.conversation_id });

    return response.conversation_id;
  },

  // 删除会话
  deleteConversation: async (id) => {
    await conversationApi.deleteConversation(id);

    // 从列表中移除
    set({
      conversations: get().conversations.filter(c => c.id !== id),
    });

    // 如果删除的是当前会话，清空当前会话
    if (get().currentConversationId === id) {
      set({
        currentConversationId: null,
        messages: [],
      });
    }
  },

  // 加载消息
  loadMessages: async (conversationId, refresh = false) => {
    // 防止同一个会话的并发请求导致消息重复
    if (get().isLoadingMessages && !refresh) return;

    set({ isLoadingMessages: true });

    try {
      const beforeMessageId = refresh ? undefined : get().firstMessageId || undefined;
      const response = await conversationApi.getConversationHistory(
        conversationId,
        get().activeProjectId || 0,
        beforeMessageId,
        50
      );

      const rawMessages: Record<string, any>[] = response.messages || [];
      const newMessages = rawMessages.map(adaptHistoryMessage);

      set({
        messages: refresh
          ? newMessages
          : [...newMessages, ...get().messages], // 旧消息在前
        hasMoreMessages: response.has_more,
        firstMessageId: response.first_message_id || get().firstMessageId,
      });
    } catch (error) {
      // 认证错误已在 API client 中统一处理，不需要输出错误日志
      if (!isAuthError(error)) {
        console.error('加载消息失败:', error);
      }
    } finally {
      set({ isLoadingMessages: false });
    }
  },

  // 加载更多消息（历史消息）
  loadMoreMessages: async (conversationId) => {
    if (!get().hasMoreMessages || get().isLoadingMessages) return;
    await get().loadMessages(conversationId);
  },

  // 添加消息
  addMessage: (message) => {
    set({ messages: [...get().messages, message] });
  },

  // 从 Agent 即时推送同步单条消息到 UI（绕过 PHP API）
  syncMessages: (incomingMessages) => {
    if (!incomingMessages || incomingMessages.length === 0) return;

    const existingMessages = get().messages;
    const adapted = adaptAgentMessages(incomingMessages);
    const newMessages = deduplicateMessages(existingMessages, adapted);

    if (newMessages.length === 0) return;

    set({ messages: [...existingMessages, ...newMessages] });
  },

  // 更新最后一条消息
  updateLastMessage: (updates) => {
    const { messages } = get();
    if (messages.length === 0) return;

    const lastIndex = messages.length - 1;
    const updatedMessages = [...messages];
    updatedMessages[lastIndex] = { ...updatedMessages[lastIndex], ...updates };
    set({ messages: updatedMessages });
  },

  // 更新指定消息的发送状态
  updateMessageStatus: (messageId, status) => {
    const { messages } = get();
    const index = messages.findIndex(m => m.id === messageId);
    if (index === -1) return;

    const updatedMessages = [...messages];
    updatedMessages[index] = { ...updatedMessages[index], status };
    set({ messages: updatedMessages });
  },

  // 清空消息
  clearMessages: () => {
    set({
      messages: [],
      hasMoreMessages: true,
      firstMessageId: null,
    });
  },

  // 清空所有会话数据
  clearConversations: () => {
    set({
      conversations: [],
      currentConversationId: null,
      messages: [],
      hasMoreConversations: true,
      conversationsPage: 1,
      activeDeviceKey: undefined,
      activeProjectId: undefined,
      hasMoreMessages: true,
      firstMessageId: null,
    });
  },

  // Rewind 回退
  rewindConversation: async (conversationId, request) => {
    const activeDeviceKey = get().activeDeviceKey;
    const result = await conversationApi.rewindConversation(conversationId, request, activeDeviceKey);
    // 刷新消息列表
    await get().loadMessages(conversationId, true);
    return result;
  },

  // Retry 重试
  retryConversation: async (conversationId, request) => {
    const activeDeviceKey = get().activeDeviceKey;
    const result = await conversationApi.retryConversation(conversationId, request, activeDeviceKey);
    // 刷新消息列表
    await get().loadMessages(conversationId, true);
    return result;
  },

  // 添加到记忆
  addToMemory: async (projectId, request) => {
    return await conversationApi.addToMemory(projectId, request);
  },
}));
