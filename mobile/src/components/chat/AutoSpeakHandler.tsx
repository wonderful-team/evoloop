// 自动朗读 AI 回复 - 独立组件，避免 ChatScreen 订阅 messages 导致重渲染
// speak 函数由父组件（ChatScreen）传入，确保与 ChatScreen 中的 useTTS 是同一实例

import { useEffect } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useAutoSpeak } from '@/hooks/useTTS';

interface AutoSpeakHandlerProps {
  speak: (text: string) => Promise<void>;
}

export function AutoSpeakHandler({ speak }: AutoSpeakHandlerProps) {
  const messages = useConversationStore((state) => state.messages);
  const { autoSpeak } = useAutoSpeak();

  useEffect(() => {
    if (autoSpeak && messages.length > 0) {
      const lastMessage = messages[messages.length - 1];
      if (lastMessage.role === 'assistant' && lastMessage.isComplete) {
        speak(lastMessage.content);
      }
    }
  }, [messages, autoSpeak, speak]);

  return null;
}
