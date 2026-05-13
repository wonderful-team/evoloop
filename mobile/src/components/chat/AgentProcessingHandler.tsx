// AI 思考中状态管理 - 独立组件，避免 ChatScreen 订阅 messages 导致重渲染

import { useEffect } from 'react';
import { useConversationStore } from '@/stores/conversationStore';

interface AgentProcessingHandlerProps {
  isAgentProcessing: boolean;
  onClear: () => void;
}

export function AgentProcessingHandler({ isAgentProcessing, onClear }: AgentProcessingHandlerProps) {
  const messages = useConversationStore((state) => state.messages);

  // 收到 AI 回复后清除思考中状态
  useEffect(() => {
    if (isAgentProcessing && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'ai') {
        onClear();
      }
    }
  }, [messages, isAgentProcessing, onClear]);

  // 超时 30 秒自动清除
  useEffect(() => {
    if (!isAgentProcessing) return;
    const timer = setTimeout(() => {
      onClear();
    }, 30000);
    return () => clearTimeout(timer);
  }, [isAgentProcessing, onClear]);

  return null;
}
