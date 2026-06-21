// Gateway WebSocket 连接管理 Hook
// 提取自 ChatScreen，避免组件过长

import { useEffect, useState, useRef, useCallback } from 'react';
import { getGatewayClient } from '@/services/gateway/GatewayClient';
import { GatewayMessageType, ConnectionState } from '@/services/gateway/types';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import { parseHITLRequest } from '@/utils/messageAdapter';
import { useHITLStore } from '@/stores/hitlStore';
import { useConversationStore } from '@/stores/conversationStore';

interface UseChatGatewayOptions {
  isLoggedIn: boolean;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  onAgentRunCompleted?: (threadId: string) => void;
}

export function useChatGateway({ isLoggedIn, syncMessages, onAgentRunCompleted }: UseChatGatewayOptions) {
  const [gatewayConnectionState, setGatewayConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
  const currentConversationIdRef = useRef<string | null>(null);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);
  const { incrementUnread } = useConversationStore();

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
        incrementUnread(threadId);
      }

      // 只有当前打开的会话才同步到 UI
      if (!threadId || threadId !== currentConversationIdRef.current) return;

      const hitlRequest = parseHITLRequest(msg);
      if (hitlRequest) {
        setHitlRequest(hitlRequest);
      }

      syncMessages([msg]);
    };

    const handleAgentRunCompleted = (message: { thread_id: string }) => {
      const threadId = message?.thread_id;
      if (threadId && threadId !== currentConversationIdRef.current) {
        incrementUnread(threadId);
      }
      if (threadId && threadId === currentConversationIdRef.current) {
        onAgentRunCompleted?.(threadId);
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

    const handleStateChange = (state: ConnectionState) => {
      setGatewayConnectionState(state);
    };

    client.on('stateChange', handleStateChange);
    client.on(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
    client.on(GatewayMessageType.MESSAGES_DELETED || 'messages_deleted', handleMessagesDeleted);
    client.on(GatewayMessageType.THREAD_REWIND || 'thread_rewind', handleThreadRewind);
    client.on(GatewayMessageType.AGENT_RUN_COMPLETED, handleAgentRunCompleted);

    client.connect().catch(() => { });

    return () => {
      client.off('stateChange', handleStateChange);
      client.off(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
      client.off(GatewayMessageType.MESSAGES_DELETED || 'messages_deleted', handleMessagesDeleted);
      client.off(GatewayMessageType.THREAD_REWIND || 'thread_rewind', handleThreadRewind);
      client.off(GatewayMessageType.AGENT_RUN_COMPLETED, handleAgentRunCompleted);
      client.disconnect();
    };
  }, [isLoggedIn, syncMessages, setHitlRequest]);

  return { gatewayConnectionState, setCurrentConversationId };
}
