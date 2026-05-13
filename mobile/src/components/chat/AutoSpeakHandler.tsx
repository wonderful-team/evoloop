// 自动朗读 AI 回复 - 独立组件，避免 ChatScreen 订阅 messages 导致重渲染
// speak 函数由父组件（ChatScreen）传入，确保与 ChatScreen 中的 useTTS 是同一实例

import { useEffect } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useAutoSpeak } from '@/hooks/useTTS';

interface AutoSpeakHandlerProps {
  speak: (text: string) => Promise<void>;
  /** 是否启用（SSE 流式过程中应设为 false） */
  enabled?: boolean;
}

export function AutoSpeakHandler({ speak, enabled = true }: AutoSpeakHandlerProps) {
  const messages = useConversationStore((state) => state.messages);
  const { autoSpeak } = useAutoSpeak();

  useEffect(() => {
    if (!enabled || !autoSpeak || messages.length === 0) return;
    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role === 'ai' && lastMessage.isComplete) {
      speak(lastMessage.content);
    }
  }, [messages, autoSpeak, speak, enabled]);

  return null;
}
