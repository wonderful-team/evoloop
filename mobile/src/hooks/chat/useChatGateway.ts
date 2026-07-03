// Gateway WebSocket 连接管理 Hook
// 提取自 ChatScreen，避免组件过长

import { useEffect, useState, useRef, useCallback } from 'react';
import { getGatewayClient } from '@/services/gateway/GatewayClient';
import { ConnectionState } from '@/services/gateway/types';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import { parseHITLRequest } from '@/utils/messageAdapter';
import { useHITLStore } from '@/stores/hitlStore';
import { useConversationStore } from '@/stores/conversationStore';

interface UseChatGatewayOptions {
  isLoggedIn: boolean;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  onAgentRunCompleted?: (threadId: string) => void;
  onCommandStatusUpdate?: (data: { command_id: number; status: string; device_key?: string; error?: string }) => void;
  onReconnected?: () => void;
}

export function useChatGateway({ isLoggedIn, syncMessages, onAgentRunCompleted, onCommandStatusUpdate, onReconnected }: UseChatGatewayOptions) {
  const [gatewayConnectionState, setGatewayConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
  const currentConversationIdRef = useRef<string | null>(null);
  const prevConnectionStateRef = useRef<ConnectionState>(ConnectionState.DISCONNECTED);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);

  // 使用 selector 以避免整个 store 任何更新都导致当前 hook 重新 Render 
  const incrementUnread = useConversationStore((state) => state.incrementUnread);

  // 使用 ref 来保存所有的回调函数与 actions。
  // 这可确保在与事件监听器交互时，无需将这些回调加入 useEffect 的依赖项，
  // 从而彻底杜绝外部回调不稳定（比如未加 useCallback 的内联匿名函数）所导致的重复断连/重连循环。
  const syncMessagesRef = useRef(syncMessages);
  const onAgentRunCompletedRef = useRef(onAgentRunCompleted);
  const onCommandStatusUpdateRef = useRef(onCommandStatusUpdate);
  const onReconnectedRef = useRef(onReconnected);
  const setHitlRequestRef = useRef(setHitlRequest);
  const incrementUnreadRef = useRef(incrementUnread);

  // 每次渲染时更新最新的引用
  useEffect(() => {
    syncMessagesRef.current = syncMessages;
    onAgentRunCompletedRef.current = onAgentRunCompleted;
    onCommandStatusUpdateRef.current = onCommandStatusUpdate;
    onReconnectedRef.current = onReconnected;
    setHitlRequestRef.current = setHitlRequest;
    incrementUnreadRef.current = incrementUnread;
  });

  const setCurrentConversationId = useCallback((id: string | null) => {
    currentConversationIdRef.current = id;
  }, []);

  useEffect(() => {
    if (!isLoggedIn) return;

    const client = getGatewayClient();

    const handleMessageSync = (message: { data: AgentSyncMessage }) => {
      const msg = message.data;
      const threadId = msg?.thread_id;
      if (!msg) return;

      // 只有当前会话不是打开状态时才累加未读
      if (threadId && threadId !== currentConversationIdRef.current) {
        incrementUnreadRef.current(threadId);
      }

      // 只有当前打开的会话才同步到 UI
      if (!threadId || threadId !== currentConversationIdRef.current) return;

      syncMessagesRef.current([msg]);
    };

    const handleAgentRunCompleted = (message: any) => {
      const threadId = message?.data?.thread_id;
      if (threadId && threadId !== currentConversationIdRef.current) {
        incrementUnreadRef.current(threadId);
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
