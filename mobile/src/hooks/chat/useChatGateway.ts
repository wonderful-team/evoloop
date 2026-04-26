// Gateway WebSocket 连接管理 Hook
// 提取自 ChatScreen，避免组件过长

import { useEffect, useState, useRef, useCallback } from 'react';
import { getGatewayClient } from '@/services/gateway/GatewayClient';
import { GatewayMessageType, ConnectionState } from '@/services/gateway/types';
import { AgentSyncMessage, AgentCommandComplete } from '@/services/gateway/agentMessage';
import { parseHITLRequest } from '@/utils/messageAdapter';
import { useHITLStore } from '@/stores/hitlStore';

interface UseChatGatewayOptions {
  isLoggedIn: boolean;
  syncMessages: (messages: AgentSyncMessage[]) => void;
}

export function useChatGateway({ isLoggedIn, syncMessages }: UseChatGatewayOptions) {
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

    const handleCommandComplete = (message: { data: AgentCommandComplete }) => {
      const payload = message.data;
      const threadId = payload?.thread_id;
      if (threadId && threadId === currentConversationIdRef.current) {
        // Agent 已完成，消息已通过 message_sync 同步
      }
    };

    const handleStateChange = (state: ConnectionState) => {
      setGatewayConnectionState(state);
    };

    client.on('stateChange', handleStateChange);
    client.on(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
    client.on('command_complete', handleCommandComplete);

    client.connect().catch(() => {});

    return () => {
      client.off('stateChange', handleStateChange);
      client.off(GatewayMessageType.MESSAGE_SYNC || 'message_sync', handleMessageSync);
      client.off('command_complete', handleCommandComplete);
      client.disconnect();
    };
  }, [isLoggedIn, syncMessages, setHitlRequest]);

  return { gatewayConnectionState, setCurrentConversationId };
}
