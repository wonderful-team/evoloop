// Gateway WebSocket 连接管理 Hook
// 提取自 ChatScreen，避免组件过长

import { useEffect, useState, useRef, useCallback } from 'react';
import { getGatewayClient } from '@/services/gateway/GatewayClient';
import { ConnectionState } from '@/services/gateway/types';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import { parseHITLRequest } from '@/utils/messageAdapter';
import { useHITLStore } from '@/stores/hitlStore';
import { useConversationStore } from '@/stores/conversationStore';
import { Conversation } from '@/types/conversation';

interface UseChatGatewayOptions {
  isLoggedIn: boolean;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  onAgentRunCompleted?: (threadId: string) => void;
  onCommandStatusUpdate?: (data: { command_id: number; status: string; device_key?: string; error?: string }) => void;
  onReconnected?: () => void;
  // 当收到 message.sync 且该 thread 不在本地 conversations 列表时，触发刷新
  onNewThreadDetected?: (threadId: string) => void;
  // 当收到配额耗尽的错误消息时触发，附带错误内容
  onQuotaExhausted?: (message: string) => void;
}

export function useChatGateway({ isLoggedIn, syncMessages, onAgentRunCompleted, onCommandStatusUpdate, onReconnected, onNewThreadDetected, onQuotaExhausted }: UseChatGatewayOptions) {
  const [gatewayConnectionState, setGatewayConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
  const currentConversationIdRef = useRef<string | null>(null);
  const prevConnectionStateRef = useRef<ConnectionState>(ConnectionState.DISCONNECTED);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);

  // 使用 selector 以避免整个 store 任何更新都导致当前 hook 重新 Render 
  const incrementUnread = useConversationStore((state) => state.incrementUnread);
  const conversations = useConversationStore((state) => state.conversations);

  // 使用 ref 来保存所有的回调函数与 actions。
  // 这可确保在与事件监听器交互时，无需将这些回调加入 useEffect 的依赖项，
  // 从而彻底杜绝外部回调不稳定（比如未加 useCallback 的内联匿名函数）所导致的重复断连/重连循环。
  const syncMessagesRef = useRef(syncMessages);
  const onAgentRunCompletedRef = useRef(onAgentRunCompleted);
  const onCommandStatusUpdateRef = useRef(onCommandStatusUpdate);
  const onReconnectedRef = useRef(onReconnected);
  const setHitlRequestRef = useRef(setHitlRequest);
  const incrementUnreadRef = useRef(incrementUnread);

  const onNewThreadDetectedRef = useRef(onNewThreadDetected);
  const onQuotaExhaustedRef = useRef(onQuotaExhausted);
  const conversationsRef = useRef<Conversation[]>([]);

  // 每次渲染时更新最新的引用
  useEffect(() => {
    syncMessagesRef.current = syncMessages;
    onAgentRunCompletedRef.current = onAgentRunCompleted;
    onCommandStatusUpdateRef.current = onCommandStatusUpdate;
    onReconnectedRef.current = onReconnected;
    setHitlRequestRef.current = setHitlRequest;
    incrementUnreadRef.current = incrementUnread;
    onNewThreadDetectedRef.current = onNewThreadDetected;
    onQuotaExhaustedRef.current = onQuotaExhausted;
  });

  const setCurrentConversationId = useCallback((id: string | null) => {
    currentConversationIdRef.current = id;
  }, []);

  // 将 conversations 同步到 ref，避免监听函数依赖 conversations 导致重复订阅
  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  useEffect(() => {
    if (!isLoggedIn) return;

    const client = getGatewayClient();

    const handleMessageSync = (message: { data: any }) => {
      const body = message.data;
      if (!body || !body.thread_id) return;

      const threadId = body.thread_id;

      // 后端 canonical message.sync 信封 body 是 MessageSyncBody，
      // 消息列表在 body.messages；兼容旧版单条消息格式。
      const rawMessages = Array.isArray(body.messages) ? body.messages : [body];
      if (rawMessages.length === 0) return;

      // 规范化后端 SyncMessage 字段 → AgentSyncMessage
      const agentMessages: AgentSyncMessage[] = rawMessages
        .map((m: any): AgentSyncMessage => ({
          ...m,
          id: String(m.message_id || m.id || `msg-${m.sequence_number || Date.now()}`),
          meta_data: m.metadata || m.meta_data || undefined,
          created_at: m.created_at,
          is_visible: typeof m.is_visible === 'boolean' ? (m.is_visible ? 1 : 0) : m.is_visible,
        }))
        .filter((m: AgentSyncMessage) => m.is_visible !== 0);

      if (agentMessages.length === 0) return;

      // 检测配额耗尽错误消息，触发充值引导 UI
      const quotaMsg = agentMessages.find(m => m.category === 'quota_exhausted');
      if (quotaMsg) {
        onQuotaExhaustedRef.current?.(quotaMsg.content);
      }

      const firstMsg = agentMessages[0];
      const messageId = firstMsg?.id;
      const projectId = firstMsg?.project_id;

      // 只有当前会话不是打开状态时才累加未读
      if (threadId && threadId !== currentConversationIdRef.current) {
        incrementUnreadRef.current(threadId, messageId, projectId);
      }

      // 只有当前打开的会话才同步到 UI
      if (threadId !== currentConversationIdRef.current) return;

      syncMessagesRef.current(agentMessages);

      // 如果该 thread 尚未出现在本地 conversations 列表，说明是新建会话的首次消息同步。
      // 此时 PHP MC 大概率已消费 message_sync 队列，触发列表刷新以获取 conversation 元数据。
      const exists = conversationsRef.current.some((c) => c.id === threadId);
      if (!exists && onNewThreadDetectedRef.current) {
        onNewThreadDetectedRef.current(threadId);
      }
    };

    const handleAgentRunCompleted = (message: any) => {
      const threadId = message?.data?.thread_id;
      const messageId = message?.data?.message_id;
      const projectId = message?.data?.project_id;
      if (threadId && threadId !== currentConversationIdRef.current) {
        incrementUnreadRef.current(threadId, messageId, projectId);
      }
      if (threadId && threadId === currentConversationIdRef.current) {
        onAgentRunCompletedRef.current?.(threadId);
      }
    };

    const handleMessagesDeleted = (message: any) => {
      const data = message.data;
      if (!data) return;
      const threadId = data.thread_id;
      const messageIds = data.message_ids;
      
      if (threadId && messageIds && Array.isArray(messageIds)) {
        useConversationStore.getState().removeMessages(messageIds);
      }
    };

    const handleThreadRewind = (message: any) => {
      const data = message.data;
      if (!data) return;
      const threadId = data.thread_id;
      const targetSequence = data.target_sequence;
      const includeTarget = data.include_target;

      if (threadId && typeof targetSequence === 'number') {
        useConversationStore.getState().rewindLocalMessages(targetSequence, !!includeTarget);
      }
    };

    const handleCommandStatusUpdate = (message: any) => {
      const data = message?.data || message;
      if (data?.command_id && onCommandStatusUpdateRef.current) {
        onCommandStatusUpdateRef.current({
          command_id: data.command_id,
          status: data.status,
          device_key: data.device_key,
          error: data.error,
        });
      }
    };

    const handleStateChange = (state: ConnectionState) => {
      const prev = prevConnectionStateRef.current;
      prevConnectionStateRef.current = state;

      // 从非 CONNECTED 状态重新连接成功时触发恢复回调
      if (state === ConnectionState.CONNECTED && prev !== ConnectionState.CONNECTED) {
        onReconnectedRef.current?.();
      }

      setGatewayConnectionState(state);
    };

    const handleMessage = (message: { type: string; data: any }) => {
      switch (message.type) {
        case 'message.sync':
          handleMessageSync(message);
          break;
        case 'message.deleted':
          handleMessagesDeleted(message);
          break;
        case 'command.rewind':
          handleThreadRewind(message);
          break;
        case 'agent.status':
          handleAgentRunCompleted(message);
          break;
        case 'command.ack':
          handleCommandStatusUpdate(message);
          break;
        case 'hitl.request': {
          const hitlData = parseHITLRequest(message.data);
          if (hitlData) {
            setHitlRequestRef.current(hitlData);
          }
          break;
        }
      }
    };

    client.on('stateChange', handleStateChange);
    client.on('message', handleMessage);

    client.connect().catch(() => { });

    return () => {
      client.off('stateChange', handleStateChange);
      client.off('message', handleMessage);
      client.disconnect();
    };
  }, [isLoggedIn]); // 仅依赖登录状态！避免任何外部重渲染导致重复 connect/disconnect。

  return { gatewayConnectionState, setCurrentConversationId };
}
