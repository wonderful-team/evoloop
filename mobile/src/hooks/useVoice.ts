// 语音对话 Hook

import { useCallback, useEffect, useRef, useState } from 'react';
import { VoiceSessionManager, VoiceSessionState } from '@/services/voice/VoiceSessionManager';
import { VADDetector } from '@/services/voice/VADDetector';
import { useVoiceStore } from '@/stores/voiceStore';
import { useHITLStore } from '@/stores/hitlStore';
import { ChatMessage, TaskCommand } from '@/types/voice';
import { HumanRequest } from '@/types/hitl';

export interface UseVoiceOptions {
  onCommandReady?: (command: TaskCommand) => void;
  onHITLRequest?: (request: HumanRequest) => void;
  onError?: (error: Error) => void;
  autoStart?: boolean;
}

export interface UseVoiceReturn {
  // 状态
  state: VoiceSessionState;
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  volume: number;
  messages: ChatMessage[];
  currentCommand: TaskCommand | null;

  // HITL 状态
  hitlRequest: HumanRequest | null;
  isWaitingForHuman: boolean;

  // 控制方法
  start: () => Promise<void>;
  stop: () => Promise<void>;
  interrupt: () => Promise<void>;
  sendMessage: (text: string) => void;
  confirmCommand: (confirmed: boolean) => void;
  respondToHITL: (value: string) => void;
  cancelHITL: (reason?: string) => void;
}

export function useVoice(options: UseVoiceOptions = {}): UseVoiceReturn {
  const { onCommandReady, onHITLRequest, onError, autoStart = false } = options;

  // 本地状态
  const [state, setState] = useState<VoiceSessionState>('idle');
  const [volume, setVolume] = useState(0);

  // Store 状态
  const store = useVoiceStore();
  const hitlStore = useHITLStore();

  // HITL 状态监听
  useEffect(() => {
    if (hitlStore.currentRequest && onHITLRequest) {
      onHITLRequest(hitlStore.currentRequest);
    }
  }, [hitlStore.currentRequest, onHITLRequest]);

  // Refs
  const sessionManagerRef = useRef<VoiceSessionManager | null>(null);
  const vadRef = useRef<VADDetector | null>(null);

  // 初始化会话管理器
  useEffect(() => {
    sessionManagerRef.current = new VoiceSessionManager({
      onStateChange: setState,
      onMessage: (message) => {
        // 消息已自动添加到 store
        console.log('收到消息:', message);
      },
      onCommandReady: (command) => {
        console.log('指令待确认:', command);
        onCommandReady?.(command);
      },
      onHITLRequest: (request) => {
        console.log('HITL 请求:', request);
        onHITLRequest?.(request);
      },
      onError: (error) => {
        console.error('语音会话错误:', error);
        onError?.(error);
      },
      onVolumeChange: setVolume,
    });

    // 初始化 VAD（用于实时音量显示）
    vadRef.current = new VADDetector(
      { threshold: 0.1 },
      { onVolumeChange: setVolume }
    );

    // 自动启动
    if (autoStart) {
      sessionManagerRef.current.start().catch(onError);
    }

    // 清理
    return () => {
      sessionManagerRef.current?.stop().catch(console.error);
      vadRef.current?.stop().catch(console.error);
    };
  }, [autoStart, onCommandReady, onError]);

  // 开始会话
  const start = useCallback(async () => {
    try {
      await sessionManagerRef.current?.start();
    } catch (error) {
      onError?.(error as Error);
    }
  }, [onError]);

  // 停止会话
  const stop = useCallback(async () => {
    try {
      await sessionManagerRef.current?.stop();
    } catch (error) {
      onError?.(error as Error);
    }
  }, [onError]);

  // 打断 AI 讲话
  const interrupt = useCallback(async () => {
    try {
      await sessionManagerRef.current?.interrupt();
    } catch (error) {
      onError?.(error as Error);
    }
  }, [onError]);

  // 发送文本消息
  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      sessionManagerRef.current?.sendTextMessage(text);
    },
    []
  );

  // 确认指令
  const confirmCommand = useCallback(
    (confirmed: boolean) => {
      sessionManagerRef.current?.confirmCommand(confirmed);
    },
    []
  );

  // 响应 HITL 请求
  const respondToHITL = useCallback(
    (value: string) => {
      const requestId = hitlStore.currentRequest?.id;
      if (requestId) {
        sessionManagerRef.current?.sendHITLResponse(requestId, value);
      }
    },
    [hitlStore.currentRequest]
  );

  // 取消 HITL 请求
  const cancelHITL = useCallback(
    (reason?: string) => {
      sessionManagerRef.current?.cancelHITLRequest(reason);
    },
    []
  );

  // 计算派生状态
  const isListening = state === 'listening';
  const isSpeaking = state === 'speaking';
  const isThinking = state === 'thinking' || state === 'recognizing';

  return {
    state,
    isListening,
    isSpeaking,
    isThinking,
    volume,
    messages: store.messages,
    currentCommand: store.currentCommand,
    // HITL 状态
    hitlRequest: hitlStore.currentRequest,
    isWaitingForHuman: hitlStore.isWaiting,
    // 方法
    start,
    stop,
    interrupt,
    sendMessage,
    confirmCommand,
    respondToHITL,
    cancelHITL,
  };
}

// 简单的录音 Hook（仅录音功能，不连接 Gateway）
export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0);

  const vadRef = useRef<VADDetector | null>(null);
  const durationTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 开始录音
  const startRecording = useCallback(async () => {
    try {
      // 启动 VAD 检测音量
      vadRef.current = new VADDetector(
        { threshold: 0.1 },
        {
          onVolumeChange: setVolume,
          onSpeechEnd: () => {
            // 可以在这里自动停止录音
          },
        }
      );

      await vadRef.current.start();
      setIsRecording(true);

      // 启动时长计时器
      durationTimerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } catch (error) {
      console.error('开始录音失败:', error);
    }
  }, []);

  // 停止录音
  const stopRecording = useCallback(async () => {
    try {
      await vadRef.current?.stop();
      setIsRecording(false);
      setVolume(0);

      // 清理计时器
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
        durationTimerRef.current = null;
      }

      const finalDuration = duration;
      setDuration(0);

      return finalDuration;
    } catch (error) {
      console.error('停止录音失败:', error);
      return 0;
    }
  }, [duration]);

  // 清理
  useEffect(() => {
    return () => {
      vadRef.current?.stop().catch(console.error);
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
    };
  }, []);

  return {
    isRecording,
    duration,
    volume,
    startRecording,
    stopRecording,
  };
}
