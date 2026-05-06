// Gateway WebSocket 连接管理 Hook
// 提取自 ChatScreen，避免组件过长

import { useEffect, useState, useRef, useCallback } from 'react';
import { getGatewayClient } from '@/services/gateway/GatewayClient';
import { GatewayMessageType, ConnectionState } from '@/services/gateway/types';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';
import { parseHITLRequest } from '@/utils/messageAdapter';
import { useHITLStore } from '@/stores/hitlStore';

interface UseChatGatewayOptions {
  isLoggedIn: boolean;
  syncMessages: (messages: AgentSyncMessage[]) => void;
  onAgentRunCompleted?: (threadId: string) => void;
}

export function useChatGateway({ isLoggedIn, syncMessages, onAgentRunCompleted }: UseChatGatewayOptions) {
  const [gatewayConnectionState, setGatewayConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
  const currentConversationIdRef = useRef<string | null>(null);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);

  const setCurrentConversationId = useCallback((id: string | null) => {
    currentConversationIdRef.current = id;
  }, []);

  useEffect(() => {
    if (!isLoggedIn) return;

    const client = getGatewayClient();

    const handleMessageSync = (message: { data: AgentSyncMessage }) => {
      const msg = message.data;
      const threadId = msg?.thread_id;
      if (!threadId || threadId !== currentConversationIdRef.current) return;
      if (!msg) return;

      const hitlRequest = parseHITLRequest(msg);
      if (hitlRequest) {
        setHitlRequest(hitlRequest);
      }

      syncMessages([msg]);
    };

    const handleAgentRunCompleted = (message: { thread_id: string }) => {
      const threadId = message?.thread_id;
      if (threadId && threadId === currentConversationIdRef.current) {
        onAgentRunCompleted?.(threadId);
      }
    };

    const handleStateChange = (state: ConnectionState) => {
      setGatewayConnectionState(state);
    };

    client.on('stateChange', handleStateChange);
    client.on(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
    client.on(GatewayMessageType.AGENT_RUN_COMPLETED, handleAgentRunCompleted);

    client.connect().catch(() => { });

    return () => {
      client.off('stateChange', handleStateChange);
      client.off(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
      client.off(GatewayMessageType.AGENT_RUN_COMPLETED, handleAgentRunCompleted);
      client.disconnect();
    };
  }, [isLoggedIn, syncMessages, setHitlRequest]);

  return { gatewayConnectionState, setCurrentConversationId };
}
