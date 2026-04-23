// Gateway WebSocket Hook

import { useEffect, useCallback, useState, useRef } from 'react';
import {
  getGatewayClient,
  resetGatewayClient,
} from '@/services/gateway/GatewayClient';
import {
  GatewayMessage,
  ConnectionState,
  GatewayMessageType,
} from '@/services/gateway/types';

interface UseGatewayOptions {
  autoConnect?: boolean;
  onMessage?: (message: GatewayMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
}

export function useGateway(options: UseGatewayOptions = {}) {
  const {
    autoConnect = true,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const client = useRef(getGatewayClient()).current;
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    client.getConnectionState()
  );
  const [isConnected, setIsConnected] = useState(client.isConnected());

  useEffect(() => {
    // 监听状态变化
    const handleStateChange = (state: ConnectionState) => {
      setConnectionState(state);
      setIsConnected(state === ConnectionState.CONNECTED);
    };

    // 监听连接事件
    const handleConnected = () => {
      onConnect?.();
    };

    const handleDisconnected = () => {
      onDisconnect?.();
    };

    const handleError = (error: Error) => {
      onError?.(error);
    };

    const handleMessage = (message: GatewayMessage) => {
      onMessage?.(message);
    };

    client.on('stateChange', handleStateChange);
    client.on('connected', handleConnected);
    client.on('disconnected', handleDisconnected);
    client.on('error', handleError);
    client.on('message', handleMessage);

    // 自动连接
    if (autoConnect) {
      client.connect().catch((error) => {
        console.error('自动连接失败:', error);
      });
    }

    return () => {
      client.off('stateChange', handleStateChange);
      client.off('connected', handleConnected);
      client.off('disconnected', handleDisconnected);
      client.off('error', handleError);
      client.off('message', handleMessage);
    };
  }, [client, autoConnect, onMessage, onConnect, onDisconnect, onError]);

  // 连接
  const connect = useCallback(async () => {
    return client.connect();
  }, [client]);

  // 断开
  const disconnect = useCallback(() => {
    client.disconnect();
  }, [client]);

  // 重连
  const reconnect = useCallback(async () => {
    return client.reconnect();
  }, [client]);

  // 发送消息
  const send = useCallback(
    (message: GatewayMessage) => {
      client.send(message);
    },
    [client]
  );

  return {
    connectionState,
    isConnected,
    connect,
    disconnect,
    reconnect,
    send,
    client,
  };
}

// 语音会话 Hook
export function useVoiceSession(sessionId: string) {
  const { send, isConnected } = useGateway();
  const [transcription, setTranscription] = useState('');
  const [isListening, setIsListening] = useState(false);

  const startASR = useCallback(() => {
    if (!isConnected) return;
    
    send({
      type: GatewayMessageType.ASR_START,
      payload: { sessionId },
    });
    setIsListening(true);
    setTranscription('');
  }, [send, isConnected, sessionId]);

  const stopASR = useCallback(() => {
    if (!isConnected) return;
    
    send({
      type: GatewayMessageType.ASR_STOP,
      payload: { sessionId },
    });
    setIsListening(false);
  }, [send, isConnected, sessionId]);

  const sendAudio = useCallback(
    (audioData: ArrayBuffer | string, isFinal: boolean = false) => {
      if (!isConnected) return;
      
      send({
        type: GatewayMessageType.ASR_CHUNK,
        payload: {
          sessionId,
          audioData,
          isFinal,
        },
      });
    },
    [send, isConnected, sessionId]
  );

  const sendMessage = useCallback(
    (message: string) => {
      if (!isConnected) return;
      
      send({
        type: GatewayMessageType.CHAT_MESSAGE,
        payload: {
          sessionId,
          message,
        },
      });
    },
    [send, isConnected, sessionId]
  );

  const interrupt = useCallback(() => {
    if (!isConnected) return;
    
    send({
      type: GatewayMessageType.CHAT_INTERRUPT,
      payload: { sessionId },
    });
  }, [send, isConnected, sessionId]);

  return {
    transcription,
    isListening,
    startASR,
    stopASR,
    sendAudio,
    sendMessage,
    interrupt,
    setTranscription,
  };
}
