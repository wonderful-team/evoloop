// 会话管理状态 Store

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { Conversation, AddMemoryRequest, UpdateMemoryRequest } from '@/types/conversation';
import { ChatMessage } from '@/types/conversation';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import * as conversationApi from '@/services/api/conversations';
import { isAuthError } from '@/utils/error';
import { adaptAgentMessages, adaptHistoryMessage, mergeSyncedHumanMessages } from '@/utils/messageAdapter';

const MAX_TRACKED_MESSAGE_IDS = 100;

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

  // 未读计数（按会话维度）
  unreadCounts: Record<string, number>;

  // 会话与设备的映射关系（deviceKey -> conversationIds）
  conversationDeviceMap: Record<string, string[]>;

  // 会话与项目的映射关系（conversationId -> projectId），用于聚合项目未读
  conversationProjectMap: Record<string, number>;

  // 已处理过的消息 ID（conversationId -> Set(messageId)），内存中不持久化
  processedMessageIds: Record<string, Set<string>>;

  // 操作
  setCurrentConversation: (id: string | null, skipLoadMessages?: boolean) => void;
  switchDevice: (deviceKey?: string) => void;
  switchProject: (projectId: number) => void;
  loadConversations: (refresh?: boolean) => Promise<void>;
  loadMoreConversations: () => Promise<void>;
  createConversation: (projectId?: number, initialMessage?: string) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  loadMessages: (conversationId: string, refresh?: boolean) => Promise<void>;
  loadMoreMessages: (conversationId: string) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  removeMessages: (messageIds: string[]) => void;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  updateLastMessage: (updates: Partial<ChatMessage>) => void;
  updateMessageStatus: (messageId: string, status: ChatMessage['status']) => void;
  replaceMessageId: (oldId: string, newId: string) => void;
  clearMessages: () => void;
  clearConversations: () => void;

  // 未读计数操作
  incrementUnread: (conversationId: string, messageId?: string, projectId?: number) => void;
  clearUnread: (conversationId: string | null) => void;
  getUnreadCount: (conversationId: string) => number;

  // 设备维度未读计数
  getDeviceUnreadCount: (deviceKey: string) => number;

  // 项目维度未读计数
  getProjectUnreadCount: (projectId: number) => number;

  // 更新应用角标
  updateAppBadge: () => void;

  // Rewind/Retry
  rewindConversation: (conversationId: string, request: { message_id: string; revert_files?: boolean }) => Promise<any>;
  retryConversation: (conversationId: string, request: { message_id: string; revert_files?: boolean }) => Promise<any>;
  rewindLocalMessages: (targetSequence: number, includeTarget: boolean) => void;

  // 添加到记忆
  addToMemory: (projectId: number, deviceKey: string, request: AddMemoryRequest, messageId?: string, conversationId?: string) => Promise<any>;
  updateMemory: (projectId: number, deviceKey: string, name: string, request: UpdateMemoryRequest) => Promise<void>;
  deleteMemory: (projectId: number, deviceKey: string, name: string, messageId?: string) => Promise<void>;

  // 更新指定消息的记忆标记（乐观更新）
  updateMessageRemembered: (messageId: string, isRemembered: boolean) => void;

  // 置顶与重命名会话
  togglePinConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, newTitle: string) => Promise<void>;
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set, get) => ({
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

  // 未读计数
  unreadCounts: {},

  // 会话与设备的映射关系
  conversationDeviceMap: {},

  // 会话与项目的映射关系
  conversationProjectMap: {},

  // 已处理消息 ID（不持久化）
  processedMessageIds: {},

      // 设置当前会话
      setCurrentConversation: (id, skipLoadMessages = false) => {
        const prevId = get().currentConversationId;
        const isUpgradingNewConversation = prevId === null && id !== null && get().messages.length > 0;

        set({
          currentConversationId: id,
          // 真正切换会话（从 A 到 B，且 A 不为 null）时才清空消息
          // 首次设置（null -> id）保留乐观更新的用户消息
          messages: prevId !== null && prevId !== id ? [] : get().messages,
          hasMoreMessages: isUpgradingNewConversation ? false : true,
          firstMessageId: null,
        });

        // 如果设置了新会话，加载消息（可跳过，例如 Gateway 创建的会话 PHP 中不存在）
        if (id && !skipLoadMessages) {
          // 首次加载用 refresh=true，直接替换旧消息，避免并发追加导致重复
          get().loadMessages(id, true);
        }
      },

      switchDevice: (deviceKey) => {
        set({
          activeDeviceKey: deviceKey,
          activeProjectId: undefined,
          conversations: [],
          currentConversationId: null,
          messages: [],
          hasMoreConversations: true,
          conversationsPage: 1,
          hasMoreMessages: true,
          firstMessageId: null,
        });
      },

      switchProject: (projectId) => {
        set({
          activeProjectId: projectId,
          conversations: [],
          currentConversationId: null,
          messages: [],
          conversationsPage: 1,
          hasMoreConversations: true,
          hasMoreMessages: true,
          firstMessageId: null,
        });
      },

      // 加载会话列表（从 state 读取筛选条件）
      loadConversations: async (refresh = false) => {
        set({ isLoadingConversations: true });

        const { activeProjectId, activeDeviceKey, conversationsPage } = get();

        const shouldRefresh = refresh;
        const page = shouldRefresh ? 1 : conversationsPage;

        if (shouldRefresh) {
          set({
            conversations: [],
            conversationsPage: 1,
            hasMoreConversations: true,
          });
        }

        try {
          const response = await conversationApi.getConversations(activeProjectId, page, 20, activeDeviceKey);
          const conversations = Array.isArray(response?.conversations) ? response.conversations : [];

          set({
            conversations: shouldRefresh
              ? conversations
              : [...get().conversations, ...conversations],
            hasMoreConversations: conversations.length === 20,
            conversationsPage: page + 1,
          });

          // 记录会话与设备、项目的映射关系
          const conversationIds = conversations.map((c) => c.id);
          set((state) => {
            const nextProjectMap = { ...state.conversationProjectMap };
            conversations.forEach((c) => {
              if (c.project_id !== undefined) {
                nextProjectMap[c.id] = c.project_id;
              }
            });

            const nextState: Partial<ConversationState> = {
              conversationProjectMap: nextProjectMap,
            };

            if (activeDeviceKey) {
              nextState.conversationDeviceMap = {
                ...state.conversationDeviceMap,
                [activeDeviceKey]: shouldRefresh
                  ? conversationIds
                  : [...(state.conversationDeviceMap[activeDeviceKey] || []), ...conversationIds],
              };
            }

            return nextState as ConversationState;
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

      // 加载更多会话——自动沿用 activeDeviceKey / activeProjectId
      loadMoreConversations: async () => {
        if (!get().hasMoreConversations || get().isLoadingConversations) {return;}
        await get().loadConversations(false);
      },

      // 创建新会话
      createConversation: async (projectId, initialMessage) => {
        const response = await conversationApi.createConversation({
          project_id: projectId,
          initial_message: initialMessage,
        });

        // 刷新会话列表（保持当前筛选条件）
        await get().loadConversations(true);

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
        if (get().isLoadingMessages && !refresh) {return;}

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
          // 请求失败时，停止继续自动加载，避免在界面无法占满时陷入死循环请求
          set({ hasMoreMessages: false });
        } finally {
          set({ isLoadingMessages: false });
        }
      },

      // 加载更多消息（历史消息）
      loadMoreMessages: async (conversationId) => {
        if (!get().hasMoreMessages || get().isLoadingMessages) {return;}
        await get().loadMessages(conversationId);
      },

      // 添加消息
      addMessage: (message) => {
        set({ messages: [...get().messages, message] });
      },

      // 删除消息
      removeMessages: (messageIds) => {
        if (!messageIds || messageIds.length === 0) {return;}
        set({
          messages: get().messages.filter(msg => !messageIds.includes(msg.id)),
        });
      },

      // 回滚本地消息列表
      rewindLocalMessages: (targetSequence: number, includeTarget: boolean) => {
        set({
          messages: get().messages.filter(msg => {
            if (!msg.sequence_number) {return true;} // keep messages without sequence
            return includeTarget ? msg.sequence_number < targetSequence : msg.sequence_number <= targetSequence;
          }),
        });
      },


      // 从 Agent 即时推送同步单条消息到 UI（绕过 PHP API）
      syncMessages: (incomingMessages) => {
        if (!incomingMessages || incomingMessages.length === 0) {return;}

        const existingMessages = get().messages;
        const adapted = adaptAgentMessages(incomingMessages);
        const merged = mergeSyncedHumanMessages(existingMessages, adapted);

        // Compare array contents to determine if any actual change occurred (not just length)
        const isSame = merged.length === existingMessages.length &&
          merged.every((m, i) => {
            const em = existingMessages[i];
            return em.id === m.id &&
                   em.content === m.content &&
                   em.thinking === m.thinking &&
                   em.status === m.status &&
                   em.sequence_number === m.sequence_number;
          });

        if (isSame) {return;}

        set({ messages: merged });
      },

      // 更新最后一条消息
      updateLastMessage: (updates) => {
        const { messages } = get();
        if (messages.length === 0) {return;}

        const lastIndex = messages.length - 1;
        const updatedMessages = [...messages];
        updatedMessages[lastIndex] = { ...updatedMessages[lastIndex], ...updates };
        set({ messages: updatedMessages });
      },

      // 更新指定消息的发送状态
      updateMessageStatus: (messageId, status) => {
        const { messages } = get();
        const index = messages.findIndex(m => m.id === messageId);
        if (index === -1) {return;}

        const updatedMessages = [...messages];
        updatedMessages[index] = { ...updatedMessages[index], status };
        set({ messages: updatedMessages });
      },

      // 用后端返回的真实 message_id 替换本地乐观消息的临时 id
      replaceMessageId: (oldId, newId) => {
        const { messages } = get();
        const index = messages.findIndex(m => m.id === oldId);
        if (index === -1) {return;}

        const updatedMessages = [...messages];
        updatedMessages[index] = { ...updatedMessages[index], id: newId };
        set({ messages: updatedMessages });
      },

      // 更新指定消息的记忆标记（乐观更新）
      updateMessageRemembered: (messageId, isRemembered) => {
        const { messages } = get();
        const index = messages.findIndex(m => m.id === messageId);
        if (index === -1) {return;}

        const updatedMessages = [...messages];
        updatedMessages[index] = { ...updatedMessages[index], is_remembered: isRemembered };
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
          unreadCounts: {},
          conversationDeviceMap: {},
          conversationProjectMap: {},
          processedMessageIds: {},
        });
      },

      // 未读计数操作
      incrementUnread: (conversationId, messageId, projectId) => {
        if (!conversationId) {return;}

        // 按 messageId 去重
        if (messageId) {
          const processed = get().processedMessageIds[conversationId];
          if (processed?.has(messageId)) {return;}
        }

        set((state) => {
          const nextCounts = {
            ...state.unreadCounts,
            [conversationId]: (state.unreadCounts[conversationId] || 0) + 1,
          };

          const nextProcessed = { ...state.processedMessageIds };
          const nextProjectMap = { ...state.conversationProjectMap };

          if (messageId) {
            let ids = nextProcessed[conversationId];
            if (!ids) {
              ids = new Set();
              nextProcessed[conversationId] = ids;
            }
            ids.add(messageId);
            // 限制集合大小，避免无限增长
            if (ids.size > MAX_TRACKED_MESSAGE_IDS) {
              const arr = Array.from(ids);
              nextProcessed[conversationId] = new Set(arr.slice(arr.length - MAX_TRACKED_MESSAGE_IDS));
            }
          }

          if (projectId !== undefined) {
            nextProjectMap[conversationId] = projectId;
          }

          return {
            unreadCounts: nextCounts,
            processedMessageIds: nextProcessed,
            conversationProjectMap: nextProjectMap,
          };
        });

        get().updateAppBadge();
      },

      clearUnread: (conversationId) => {
        if (!conversationId) {return;}
        set((state) => {
          const rest = { ...state.unreadCounts };
          delete rest[conversationId];
          const nextProcessed = { ...state.processedMessageIds };
          delete nextProcessed[conversationId];
          return {
            unreadCounts: rest,
            processedMessageIds: nextProcessed,
          };
        });
        get().updateAppBadge();
      },

      getUnreadCount: (conversationId) => {
        return get().unreadCounts[conversationId] || 0;
      },

      // 获取设备维度的总未读数
      getDeviceUnreadCount: (deviceKey) => {
        if (!deviceKey) {return 0;}
        const conversationIds = get().conversationDeviceMap[deviceKey] || [];
        return conversationIds.reduce(
          (sum, id) => sum + (get().unreadCounts[id] || 0),
          0
        );
      },

      // 获取项目维度的总未读数
      getProjectUnreadCount: (projectId) => {
        const state = get();
        return Object.entries(state.unreadCounts).reduce((sum, [conversationId, count]) => {
          const convProjectId = state.conversationProjectMap[conversationId];
          // 没有 project 映射时尝试从会话列表反查
          if (convProjectId === undefined) {
            const conversation = state.conversations.find((c) => c.id === conversationId);
            if (conversation?.project_id === projectId) {
              return sum + count;
            }
            return sum;
          }
          return convProjectId === projectId ? sum + count : sum;
        }, 0);
      },

      // 更新应用桌面角标
      updateAppBadge: () => {
        if (Platform.OS === 'harmony') {return;}
        const total = Object.values(get().unreadCounts).reduce((sum, c) => sum + c, 0);
        try {
          const notifee = require('@notifee/react-native').default;
          notifee.setBadgeCount(total).catch(() => {});
        } catch {
          // notifee 未安装或不可用时静默
        }
      },

      // Rewind 回退
      rewindConversation: async (conversationId, request) => {
        const activeDeviceKey = get().activeDeviceKey;
        // 乐观直接截断本地消息列表，无需等待接口返回
        const currentMessages = get().messages;
        const index = currentMessages.findIndex(m => m.id === request.message_id);
        if (index !== -1) {
          set({ messages: currentMessages.slice(0, index) });
        }
        return await conversationApi.rewindConversation(conversationId, request, activeDeviceKey);
      },

      // Retry 重试
      retryConversation: async (conversationId, request) => {
        const activeDeviceKey = get().activeDeviceKey;
        // 乐观直接截断本地消息列表（重试时保留当前这条人类消息本身）
        const currentMessages = get().messages;
        const index = currentMessages.findIndex(m => m.id === request.message_id);
        if (index !== -1) {
          set({ messages: currentMessages.slice(0, index + 1) });
        }
        return await conversationApi.retryConversation(conversationId, request, activeDeviceKey);
      },

      // 添加到记忆
      addToMemory: async (projectId, deviceKey, request, messageId, conversationId) => {
        return await conversationApi.addToMemory(projectId, deviceKey, request, messageId, conversationId);
      },
      updateMemory: async (projectId, deviceKey, name, request) => {
        await conversationApi.updateMemory(projectId, deviceKey, name, request);
      },
      deleteMemory: async (projectId, deviceKey, name, messageId) => {
        await conversationApi.deleteMemory(projectId, deviceKey, name, messageId);
      },

      // 置顶/取消置顶会话
      togglePinConversation: async (id) => {
        const conversation = get().conversations.find(c => c.id === id);
        if (!conversation) {return;}

        const nextPinned = !conversation.is_pinned;

        // 乐观更新本地状态
        const updatedConversations = get().conversations.map(c => {
          if (c.id === id) {
            return { ...c, is_pinned: nextPinned };
          }
          return c;
        });

        // 重新排序: 置顶的在前，然后按更新时间在后
        const sortedConversations = [...updatedConversations].sort((a, b) => {
          const pinA = a.is_pinned ? 1 : 0;
          const pinB = b.is_pinned ? 1 : 0;
          if (pinA !== pinB) {
            return pinB - pinA;
          }
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });

        set({ conversations: sortedConversations });

        try {
          await conversationApi.updateConversation(id, { is_pinned: nextPinned ? 1 : 0 });
        } catch (error) {
          console.error('更新置顶状态失败:', error);
          // 失败时回滚
          const rolledBackConversations = get().conversations.map(c => {
            if (c.id === id) {
              return { ...c, is_pinned: conversation.is_pinned };
            }
            return c;
          }).sort((a, b) => {
            const pinA = a.is_pinned ? 1 : 0;
            const pinB = b.is_pinned ? 1 : 0;
            if (pinA !== pinB) {
              return pinB - pinA;
            }
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
          });
          set({ conversations: rolledBackConversations });
        }
      },

      // 重命名会话
      renameConversation: async (id, newTitle) => {
        const conversation = get().conversations.find(c => c.id === id);
        if (!conversation) {return;}

        const oldTitle = conversation.title;

        // 乐观更新本地状态
        set({
          conversations: get().conversations.map(c => {
            if (c.id === id) {
              return { ...c, title: newTitle };
            }
            return c;
          }),
        });

        try {
          await conversationApi.updateConversation(id, { title: newTitle });
        } catch (error) {
          console.error('重命名会话失败:', error);
          // 失败时回滚
          set({
            conversations: get().conversations.map(c => {
              if (c.id === id) {
                return { ...c, title: oldTitle };
              }
              return c;
            }),
          });
        }
      },
    }),
    {
      name: 'conversation-unread-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        unreadCounts: state.unreadCounts,
        conversationDeviceMap: state.conversationDeviceMap,
        conversationProjectMap: state.conversationProjectMap,
        activeDeviceKey: state.activeDeviceKey,
        activeProjectId: state.activeProjectId,
      }),
    }
  )
);
