// 会话管理状态 Store

import { create } from 'zustand';
import { Conversation, ConversationHistoryResponse } from '@/types/conversation';
import { ChatMessage } from '@/types/conversation';
import * as conversationApi from '@/services/api/conversations';
import { isAuthError } from '@/utils/error';

interface ConversationState {
  // 会话列表
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoadingConversations: boolean;
  hasMoreConversations: boolean;
  conversationsPage: number;

  // 当前会话消息
  messages: ChatMessage[];
  isLoadingMessages: boolean;
  hasMoreMessages: boolean;
  firstMessageId: string | null;

  // 操作
  setCurrentConversation: (id: string | null) => void;
  loadConversations: (projectId?: number, refresh?: boolean) => Promise<void>;
  loadMoreConversations: (projectId?: number) => Promise<void>;
  createConversation: (projectId?: number, initialMessage?: string) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  loadMessages: (conversationId: string, refresh?: boolean) => Promise<void>;
  loadMoreMessages: (conversationId: string) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  updateLastMessage: (updates: Partial<ChatMessage>) => void;
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

  messages: [],
  isLoadingMessages: false,
  hasMoreMessages: true,
  firstMessageId: null,

  // 设置当前会话
  setCurrentConversation: (id) => {
    set({
      currentConversationId: id,
      messages: [], // 切换会话时清空消息
      hasMoreMessages: true,
      firstMessageId: null,
    });

    // 如果设置了新会话，加载消息
    if (id) {
      get().loadMessages(id);
    }
  },

  // 加载会话列表
  loadConversations: async (projectId, refresh = false) => {
    set({ isLoadingConversations: true });

    try {
      const page = refresh ? 1 : get().conversationsPage;
      const response = await conversationApi.getConversations(projectId, page);

      set({
        conversations: refresh
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

  // 加载更多会话
  loadMoreConversations: async (projectId) => {
    if (!get().hasMoreConversations || get().isLoadingConversations) return;
    await get().loadConversations(projectId);
  },

  // 创建新会话
  createConversation: async (projectId, initialMessage) => {
    const response = await conversationApi.createConversation({
      project_id: projectId,
      initial_message: initialMessage,
    });

    // 刷新会话列表
    await get().loadConversations(projectId, true);

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
    set({ isLoadingMessages: true });

    try {
      const beforeMessageId = refresh ? undefined : get().firstMessageId || undefined;
      const response = await conversationApi.getConversationHistory(
        conversationId,
        beforeMessageId,
        20
      );

      const newMessages = response.messages;

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

  // 更新最后一条消息
  updateLastMessage: (updates) => {
    const { messages } = get();
    if (messages.length === 0) return;

    const lastIndex = messages.length - 1;
    const updatedMessages = [...messages];
    updatedMessages[lastIndex] = { ...updatedMessages[lastIndex], ...updates };
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
      hasMoreMessages: true,
      firstMessageId: null,
    });
  },

  // Rewind 回退
  rewindConversation: async (conversationId, request) => {
    const result = await conversationApi.rewindConversation(conversationId, request);
    // 刷新消息列表
    await get().loadMessages(conversationId, true);
    return result;
  },

  // Retry 重试
  retryConversation: async (conversationId, request) => {
    const result = await conversationApi.retryConversation(conversationId, request);
    // 刷新消息列表
    await get().loadMessages(conversationId, true);
    return result;
  },

  // 添加到记忆
  addToMemory: async (projectId, request) => {
    return await conversationApi.addToMemory(projectId, request);
  },
}));
