// 首页 - 语音对话主界面（新版 VoiceEngine）

import React, { useCallback, useEffect, useState, useRef } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  StatusBar,
  PermissionsAndroid,
} from 'react-native';
import { router } from '@/utils/navigation';
import { useTranslation } from 'react-i18next';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import {
  Text,
  Snackbar,
  Portal,
  Dialog,
  Button,
} from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  MessageList,
  VoiceInputWithEngine,
  VoiceInputWithEngineHandle,
  InputMode,
} from '@/components/voice';
import { HITLBanner, HumanRequestCard } from '@/components/hitl';
import { QuotaExhaustedBanner, QuotaExhaustedCard, HistoryDrawer, AutoSpeakHandler, AgentProcessingHandler, RecognizingBanner, ChatWelcome } from '@/components/chat';
import { useDeviceControl } from '@/hooks/useDeviceControl';
import { useCommands } from '@/hooks/useCommands';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useStreamingTTS, detectEmotionAndSpeed } from '@/hooks/useStreamingTTS';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import type { LocalIntent } from '@/services/voice/localNLU';
import { extractSegments } from '@/services/voice/streamingSegmenter';
import { useWakeWordSettings } from '@/hooks/useWakeWord';
import { useSystemIntent } from '@/hooks/useSystemIntent';
import ReactNativeHapticFeedback from 'react-native-haptic-feedback';
import { useConversationStore } from '@/stores/conversationStore';
import { useTheme } from '@/theme';
import { useAuthStore } from '@/stores/authStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useProjects } from '@/hooks/useProjects';
import { useDevices } from '@/hooks/useDevices';
import { useChatGateway } from '@/hooks/chat/useChatGateway';
import * as conversationApi from '@/services/api/conversations';

import { ChatMessage, MessageReference } from '@/types/conversation';
import type { UploadedFile } from '@/services/api/upload';
import { ConnectionState } from '@/services/gateway/types';
import { getErrorMessage, isQuotaError } from '@/utils/error';
import { debugManager } from '@/utils/debugManager';
import { requestMicrophonePermission as requestMicPermission } from '@/utils/permissions';
import { generateUUID } from '@/utils/uuid';
import { Menu, Divider } from 'react-native-paper';


export default function ChatScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
  const insets = useSafeAreaInsets();

  // 从 MC 拉取项目列表（登录后才请求）
  const { currentProject, isGlobalMode } = useProjects({ autoFetch: isLoggedIn });

  // 保持设备列表刷新
  useDevices({ autoFetch: isLoggedIn });

  // 输入模式
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);

  // UI 状态
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [showRewindDialog, setShowRewindDialog] = useState(false);
  const [pendingRewindMessageId, setPendingRewindMessageId] = useState<string | null>(null);
  const [pendingRewindContent, setPendingRewindContent] = useState<string>('');
  const [pendingRetryMessageId, setPendingRetryMessageId] = useState<string | null>(null);
  const [hasFileOperations, setHasFileOperations] = useState(false);
  const [pendingForwardContent, setPendingForwardContent] = useState<string | null>(null);
  const [isAgentProcessing, setIsAgentProcessing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [debugMenuVisible, setDebugMenuVisible] = useState(false);



  const conversations = useConversationStore((state) => state.conversations);
  const currentConversationId = useConversationStore((state) => state.currentConversationId);
  const activeDeviceKey = useConversationStore((state) => state.activeDeviceKey);
  const hasMessages = useConversationStore((state) => state.messages.length > 0);
  const hasMoreMessages = useConversationStore((state) => state.hasMoreMessages);
  const isLoadingMessages = useConversationStore((state) => state.isLoadingMessages);

  // 方法 - Zustand action 引用稳定，单独 selector
  const loadConversations = useConversationStore((state) => state.loadConversations);
  const setCurrentConversation = useConversationStore((state) => state.setCurrentConversation);
  const clearUnread = useConversationStore((state) => state.clearUnread);
  const createConversation = useConversationStore((state) => state.createConversation);
  const addMessage = useConversationStore((state) => state.addMessage);
  const loadMessages = useConversationStore((state) => state.loadMessages);
  const syncMessages = useConversationStore((state) => state.syncMessages);
  const updateMessageStatus = useConversationStore((state) => state.updateMessageStatus);
  const rewindConversation = useConversationStore((state) => state.rewindConversation);
  const retryConversation = useConversationStore((state) => state.retryConversation);
  const addToMemory = useConversationStore((state) => state.addToMemory);
  const replaceMessageId = useConversationStore((state) => state.replaceMessageId);

  // 连续对话与打断设置
  const [continuousListening, setContinuousListening] = useState(true);
  const startVoiceInputRef = useRef<((mode?: 'wake' | 'asr') => Promise<void>) | null>(null);
  const handleBeforeStartRecordingRef = useRef<(() => Promise<boolean>) | null>(null);

  useEffect(() => {
    const loadVoiceSettings = async () => {
      try {
        const val = await AsyncStorage.getItem('voice_settings');
        if (val) {
          const parsed = JSON.parse(val);
          if (parsed && typeof parsed.continuousListening === 'boolean') {
            setContinuousListening(parsed.continuousListening);
          }
        }
      } catch {}
    };
    loadVoiceSettings();
  }, []);

  // TTS
  const { speak, enqueue: enqueueTTS, clearQueue: clearTTSQueue, stop: stopTTS, isSpeaking: isTTSSpeaking, prewarm: prewarmTTS } = useStreamingTTS({
    onComplete: () => {
      console.log('[ChatScreen] TTS complete callback');
      if (continuousListening) {
        console.log('[ChatScreen] Continuous listening is enabled, auto-starting voice input...');
        handleBeforeStartRecordingRef.current?.().then((allowed) => {
          if (allowed) {
            startVoiceInputRef.current?.('asr').catch((err) => {
              console.error('[ChatScreen] Auto start voice input failed:', err);
            });
          }
        });
      }
    }
  });

  // SSE 流式状态
  const streamMessageIdRef = useRef<string | null>(null);
  const ttsBufferRef = useRef('');
  const isFirstSegmentRef = useRef(true);
  const commandIdMapRef = useRef<Map<number, string>>(new Map());

  // 清理 markdown 标记，避免 TTS 朗读 ** * 等符号
  const cleanForTTS = useCallback((text: string): string => {
    return text
      .replace(/\*\*(.+?)\*\*/g, '$1')   // **bold**
      .replace(/\*(.+?)\*/g, '$1')         // *italic*
      .replace(/`{1,3}(.+?)`{1,3}/g, '$1') // `code` / ```code```
      .replace(/[#>\-\[\]\(\)]/g, '')     // markdown 符号
      .trim();
  }, []);

  // 流式 TTS：语言感知断句器（替代旧的三段式 flushTTSBuffer）
  const flushTTSBuffer = useCallback(() => {
    const [segments, remaining] = extractSegments(
      ttsBufferRef.current,
      isFirstSegmentRef.current
    );
    if (segments.length > 0) {
      ttsBufferRef.current = remaining;
      if (isFirstSegmentRef.current) { isFirstSegmentRef.current = false; }
      segments.forEach((s) => {
        const cleaned = cleanForTTS(s);
        if (!cleaned) { return; }
        const ttsOptions = detectEmotionAndSpeed(cleaned);
        enqueueTTS(cleaned, ttsOptions);
      });
    }
  }, [enqueueTTS, cleanForTTS]);


  // 更新指定 ID 的消息内容（流式用）
  const updateStreamMessage = useCallback((messageId: string, content: string, isComplete?: boolean) => {
    const { messages } = useConversationStore.getState();
    const index = messages.findIndex(m => m.id === messageId);
    if (index === -1) return;
    const updated = [...messages];
    updated[index] = { ...updated[index], content, ...(isComplete !== undefined ? { isComplete } : {}) };
    useConversationStore.setState({ messages: updated });
  }, []);

  // 控制指令（stop / retry / rewind）
  const { stop: stopAgent } = useCommands();
  const autoSpeak = useSettingsStore((state) => state.settings.autoSpeak);
  const setSetting = useSettingsStore((state) => state.setSetting);
  const toggleAutoSpeak = useCallback(() => setSetting('autoSpeak', !autoSpeak), [autoSpeak, setSetting]);

  // 唤醒词设置
  const { enabled: wakeWordEnabled, toggleWakeWord } = useWakeWordSettings();

  // 新语音输入 Hook（包含唤醒词能力）
  const { startWakeWord, stop: stopVoiceInput, start: startVoiceInput } = useVoiceInput({
    onFinalResult: (text) => handleSendMessage(text),
    onError: (error) => {
      const errorMsg = error?.message || '';
      if (errorMsg.includes('登录') || errorMsg.includes('authorization') || errorMsg.includes('401')) {
        showSnackbar(t('chat.voiceLoginRequired'));
        router.push('Auth');
      } else {
        showSnackbar(t('chat.voiceRecognitionError') + errorMsg);
      }
    },
    onWake: (detectedWord) => {
      stopTTS();
      const currentId = useConversationStore.getState().currentConversationId;
      if (currentId) {
        stopAgent(currentId, activeDeviceKey).catch(() => {});
      }
      ReactNativeHapticFeedback.trigger('notificationSuccess', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: false,
      });
      showSnackbar(t('chat.wakeWordDetected', { word: detectedWord }));
    },
    onInterrupt: () => {
      stopTTS();
      const currentId = useConversationStore.getState().currentConversationId;
      if (currentId) {
        stopAgent(currentId, activeDeviceKey).catch(() => {});
      }
    },
    // 本地意图拦截：识别到控制指令时直接执行 UI 动作，不发给云端 LLM
    onLocalIntent: (intent) => {
      if (intent.action === 'OPEN' && intent.object === 'HISTORY') {
        setShowHistoryDrawer(true);
      } else if (intent.action === 'CLOSE' && intent.object === 'HISTORY') {
        setShowHistoryDrawer(false);
      } else if (intent.action === 'MUTE') {
        setSetting('autoSpeak', false);
        showSnackbar(t('chat.tts.muted'));
      } else if (intent.action === 'UNMUTE') {
        setSetting('autoSpeak', true);
        showSnackbar(t('chat.tts.unmuted'));
      } else if (intent.action === 'RESET') {
        createConversation();
      }
    },
    // VAD 停止说话时，提前预热云端 TTS TCP 连接（省去 TLS 握手延迟 ~200ms）
    onVadEndPrewarm: prewarmTTS,
    // 传入当前 UI 状态，用于指代消解（如"把它关了"→历史已打开时消解为 HISTORY）
    uiState: { isHistoryOpen: showHistoryDrawer },
  });

  useEffect(() => {
    startVoiceInputRef.current = startVoiceInput;
  }, [startVoiceInput]);

  // Snackbar 工具函数（提前定义，供下方回调使用）
  const showSnackbar = useCallback((message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  }, []);

  // 唤醒词状态
  const [isWakeWordListening, setIsWakeWordListening] = useState(false);
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false);

  useEffect(() => {
    if (wakeWordEnabled && isLoggedIn) {
      startWakeWord().then(() => setIsWakeWordListening(true)).catch(() => {});
    } else {
      stopVoiceInput().then(() => {
        setIsWakeWordListening(false);
        setIsWakeWordDetected(false);
      }).catch(() => {});
    }
    return () => {
      stopVoiceInput().catch(() => {});
    };
  }, [wakeWordEnabled, isLoggedIn]);

  // ========== 设备控制（HTTP 版本） ==========
  // 使用 useCallback 稳定回调引用，避免 ChatScreen 重渲染导致 useDeviceControl 内部重建
  const handleDeviceError = useCallback((error: any) => {
    showSnackbar(t('chat.sendFailed') + error.message);
  }, [showSnackbar]);

  const handleMessageSent = useCallback((result: any) => {
    // 使用 getState() 避免依赖 currentConversationId 导致重建
    const currentId = useConversationStore.getState().currentConversationId;

    // 新会话时 Gateway 会返回 thread_id，必须设置到 currentConversationId
    // 否则后续 message_sync / command_complete 的 thread_id 匹配会失败，消息被丢弃
    if (result.threadId && !currentId) {
      // 跳过从 PHP 加载消息，后续 message_sync 会直接推送消息到 UI
      setCurrentConversation(result.threadId, true);
    }

    // 链路二（直连 LLM）：立即显示 AI 回复
    // 注意：SSE 流式场景中，aiMessage 为 undefined（消息已在流式过程中实时更新）
    if (result.aiMessage) {
      addMessage({
        id: generateUUID(),
        role: 'ai',
        content: result.aiMessage,
        timestamp: Date.now(),
        isComplete: true,
      });
    } else if (result.mode !== 'direct_llm') {
      // 链路一（转发 Desktop）：记录 command_id → local message id 映射
      if (result.mode === 'desktop' && result.commandId > 0) {
        // 获取最后一条 human 消息的 id（状态为 running）
        const msgs = useConversationStore.getState().messages;
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'human' && msgs[i].status === 'running') {
            commandIdMapRef.current.set(result.commandId, msgs[i].id);
            break;
          }
        }
      }
    }

    // Gateway 统一生成 message_id：用后端真实 id 替换本地乐观消息的临时 id
    if (result.messageId) {
      const msgs = useConversationStore.getState().messages;
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'human' && msgs[i].status === 'running') {
          replaceMessageId(msgs[i].id, result.messageId);
          updateMessageStatus(result.messageId, 'sent');
          break;
        }
      }
    } else {
      // 兜底：无 message_id 时直接标记最后一条 running 的 human 消息为已送达
      const msgs = useConversationStore.getState().messages;
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'human' && msgs[i].status === 'running') {
          updateMessageStatus(msgs[i].id, 'sent');
          break;
        }
      }
    }
  }, [setCurrentConversation, addMessage, replaceMessageId, updateMessageStatus]);

  const {
    state: deviceState,
    isSending,
    hitlRequest,
    isWaitingForHuman: isHITLWaiting,
    pendingCommand,
    quotaExhaustedInfo,
    isQuotaExhausted,
    setQuotaExhaustedInfo,
    sendMessage: sendMessageToDevice,
    confirmCommand,
    respondToHITL,
    cancelHITL,
    clearQuotaExhausted,
  } = useDeviceControl({
    onError: handleDeviceError,
    onMessageSent: handleMessageSent,
  });

  // 统一设备来源：所有需要 deviceKey 的地方统一使用 activeDeviceKey
  // selectedDevice 仅用于 UI 展示和触发同步
  const effectiveDeviceKey = activeDeviceKey;

  // 从 deviceStore 获取当前选中的设备
  const { currentDevice: selectedDevice } = useDeviceStore();

  // Gateway WebSocket 连接与设备-对话同步（提取为自定义 hooks）
  const {
    gatewayConnectionState,
    setCurrentConversationId,
  } = useChatGateway({
    isLoggedIn,
    syncMessages,
    onAgentRunCompleted: () => {
      setIsAgentProcessing(false);
    },
    onCommandStatusUpdate: useCallback((data) => {
      const messageId = commandIdMapRef.current.get(data.command_id);
      if (!messageId) return;

      if (data.status === 'completed' || data.status === 'delivered') {
        updateMessageStatus(messageId, 'sent');
      } else if (data.status === 'failed') {
        updateMessageStatus(messageId, 'failed');
      } else if (data.status === 'received') {
        updateMessageStatus(messageId, 'awaiting_delivered');
      }

      if (data.status === 'completed' || data.status === 'failed') {
        commandIdMapRef.current.delete(data.command_id);
      }
    }, [updateMessageStatus]),
    onReconnected: useCallback(async () => {
      if (currentConversationId) {
        loadMessages(currentConversationId, true);
      }
      loadConversations(true);

      // 命令最终状态由 WebSocket command.ack / agent.status 驱动，
      // 不再轮询已删除的 /gateway/api/v1/commands/:id 接口。
      // 重连后 Desktop Agent 会主动推送未完成命令的状态更新。
    }, [currentConversationId, loadMessages, loadConversations]),
    onNewThreadDetected: useCallback((_threadId) => {
      // 新会话的首次 message.sync 到达时，PHP MC 已消费队列的概率很高，刷新列表以获取 conversation 元数据
      loadConversations(true);
    }, [loadConversations]),
    onQuotaExhausted: useCallback((errorMessage: string) => {
      setQuotaExhaustedInfo({
        title: t('deviceControl.quotaExhaustedTitle'),
        message: errorMessage,
        hint: t('deviceControl.quotaExhaustedHint'),
      });
    }, [t]),
  });
  // 同步 currentConversationId 到 Gateway hook（避免 WebSocket 因 id 变化而重连）
  useEffect(() => {
    setCurrentConversationId(currentConversationId);
    // 进入会话或切换会话时，打断之前的 TTS 音频播放并清空队列
    stopTTS();
    clearTTSQueue();
    // 配额耗尽状态归属发起它的会话；切换/新建会话时清除，避免卡片/横幅泄漏到无关会话
    clearQuotaExhausted();
    if (currentConversationId) {
      clearUnread(currentConversationId);
      // 进入会话时同步标记后端已读
      conversationApi.markAsRead(currentConversationId).catch(() => {});
    }
  }, [currentConversationId, setCurrentConversationId, clearUnread, stopTTS, clearTTSQueue, clearQuotaExhausted]);

  const clearAgentProcessing = useCallback(() => {
    setIsAgentProcessing(false);
  }, []);

  // 重发失败消息
  const handleResend = useCallback(async (message: ChatMessage) => {
    // 状态更新由 WebSocket 驱动；重发前不再查询已删除的 /gateway/api/v1/commands/:id
    updateMessageStatus(message.id, 'sending');
    try {
      await sendMessageToDevice({
        type: 'text',
        text: message.content,
      }, {
        conversationId: currentConversationId || undefined,
        deviceKey: effectiveDeviceKey,
        references: message.references,
        projectId: currentProject?.id,
      });
      updateMessageStatus(message.id, 'sent');
    } catch (error: unknown) {
      updateMessageStatus(message.id, 'failed');
      const errorText = getErrorMessage(error);
      if (!isQuotaError(error)) {
        showSnackbar(t('chat.sendFailed') + errorText);
      }
    }
  }, [currentConversationId, sendMessageToDevice, effectiveDeviceKey, showSnackbar, t, updateMessageStatus, currentProject]);

  // 发送消息（HTTP 版本）
  const handleSendMessage = useCallback(async (text: string, options?: { references?: MessageReference[] }) => {
    // 空文本拦截（上游入口已有防护，此处做兜底）
    if (!text.trim() && !options?.references?.length) {
      return;
    }

    // 权限校验：未登录时拦截并跳转
    if (!isLoggedIn) {
      showSnackbar(t('chat.voiceLoginRequired'));
      router.push('Auth');
      return;
    }

    // deviceKey 是可选的，如果没有选择设备，直接通过 Gateway 和 LLM 对话

    // 不需要强制选择设备

    // 注意：不再调用 PHP createConversation API（list() 只是获取列表，不创建会话）
    // 新会话由 Gateway 在收到无 thread_id 的请求时自动生成，
    // 生成的 thread_id 通过 onMessageSent 回调返回并设置到 currentConversationId
    let conversationId = currentConversationId;

    let finalText = text;

    // 如果有引用，添加到消息中
    if (options?.references && options.references.length > 0) {
      const refText = options.references.map(r => `@${r.name}`).join(' ');
      finalText = `${refText} ${text}`;
    }

    // 立即将用户消息添加到本地消息列表（乐观更新）
    const userMessage: ChatMessage = {
      id: generateUUID(),
      role: 'human',
      content: finalText,
      timestamp: Date.now(),
      isComplete: true,
      status: 'running',
      references: options?.references,
    };
    addMessage(userMessage);

    // 清空 TTS buffer（新对话开始）
    ttsBufferRef.current = '';

    // 30s 超时检测：HTTP 请求超时或command_ack 未回
    const timeoutId = setTimeout(() => {
      updateMessageStatus(userMessage.id, 'timeout');
    }, 30000);

    // 通过 HTTP 发送消息到 Gateway
    try {
      await sendMessageToDevice({
        type: 'text',
        text: finalText,
      }, {
        conversationId: conversationId || undefined,
        deviceKey: effectiveDeviceKey,
        references: options?.references,
        projectId: currentProject?.id,
        // 流式回调（仅链路二生效）
        onStreamStart: () => {
          // 重置首句标志，确保每轮回复都以低门限切出首个片段，最小化 TTFS
          isFirstSegmentRef.current = true;
          const msgId = generateUUID();
          streamMessageIdRef.current = msgId;
          addMessage({
            id: msgId,
            role: 'ai',
            content: '',
            timestamp: Date.now(),
            isComplete: false,
            status: 'running',
          });
        },
        onStreamChunk: (chunk, fullText) => {
          console.log('[ChatScreen] onStreamChunk:', chunk, 'fullText:', fullText.slice(-20));
          const msgId = streamMessageIdRef.current;
          if (msgId) {
            updateStreamMessage(msgId, fullText);
          }
          // 流式 TTS：积累文字，切分完整句子后 enqueue
          ttsBufferRef.current += chunk;
          console.log('[ChatScreen] ttsBuffer before flush:', ttsBufferRef.current);
          flushTTSBuffer();
          console.log('[ChatScreen] ttsBuffer after flush:', ttsBufferRef.current);
        },
        onStreamDone: (fullText) => {
          console.log('[ChatScreen] onStreamDone, fullText length:', fullText.length);
          setIsStreaming(false);
          const msgId = streamMessageIdRef.current;
          if (msgId) {
            updateStreamMessage(msgId, fullText, true);
            streamMessageIdRef.current = null;
          }
          // 播放剩余未切分的 buffer
          flushTTSBuffer();
          const remaining = cleanForTTS(ttsBufferRef.current);
          console.log('[ChatScreen] onStreamDone remaining buffer:', remaining);
          if (remaining.length >= 2) {
            const ttsOptions = detectEmotionAndSpeed(remaining);
            enqueueTTS(remaining, ttsOptions);
          }
          ttsBufferRef.current = '';
        },
        onGatewayMetadata: (meta) => {
          console.log('[ChatScreen] gateway_metadata:', meta);
          // 链路二：Gateway 返回 human 消息的 message_id，替换本地乐观 id
          replaceMessageId(userMessage.id, meta.message_id);
          updateMessageStatus(meta.message_id, 'sent');
          // 确保当前会话 id 与 Gateway 一致（新会话场景）
          if (!currentConversationId) {
            setCurrentConversation(meta.thread_id, true);
          }
        },
      });

      clearTimeout(timeoutId);

      // 链路一（Desktop）：显示 AI 思考中指示器
      if (effectiveDeviceKey) {
        setIsAgentProcessing(true);
      }

    } catch (error: unknown) {
      clearTimeout(timeoutId);
      // 发送失败：标记为失败
      updateMessageStatus(userMessage.id, 'failed');

      const errorText = getErrorMessage(error);
      // 配额耗尽由专门的 UI 卡片提示，其他错误用 snackbar
      if (!isQuotaError(error)) {
        showSnackbar(t('chat.sendFailed') + errorText);
      }
    }
  }, [currentConversationId, sendMessageToDevice, effectiveDeviceKey, addMessage, updateMessageStatus, updateStreamMessage, flushTTSBuffer, enqueueTTS, cleanForTTS, currentProject, replaceMessageId, setCurrentConversation]);

  useSystemIntent(
    useCallback((text) => {
      handleSendMessage(text);
    }, [handleSendMessage])
  );

  // 请求麦克风权限
  const requestMicrophonePermission = useCallback(async () => {
    return requestMicPermission();
  }, []);

  // 按住说话模式（前置检查，实际录音由 VoiceInputWithEngine 内部管理）
  const handleBeforeStartRecording = useCallback(async (): Promise<boolean> => {
    console.log('[ChatScreen] handleBeforeStartRecording called');
    // 未登录时提示并跳转登录页
    if (!isLoggedIn) {
      showSnackbar(t('chat.voiceLoginRequired'));
      router.push('Auth');
      return false;
    }

    // 请求录音权限
    console.log('[ChatScreen] requesting microphone permission...');
    const hasPermission = await requestMicrophonePermission();
    console.log('[ChatScreen] microphone permission:', hasPermission);
    if (!hasPermission) {
      showSnackbar(t('chat.voicePermissionDenied'));
      return false;
    }

    // 停止唤醒词监听，释放麦克风给 ASR 使用
    if (wakeWordEnabled) {
      await stopVoiceInput();
      setIsWakeWordListening(false);
    }

    return true;
  }, [isLoggedIn, requestMicrophonePermission, showSnackbar, wakeWordEnabled, stopVoiceInput]);

  useEffect(() => {
    handleBeforeStartRecordingRef.current = handleBeforeStartRecording;
  }, [handleBeforeStartRecording]);

  // 切换自动朗读：如果正在播放，先停止当前 TTS
  const handleToggleAutoSpeak = useCallback(() => {
    if (isTTSSpeaking) {
      stopTTS();
    }
    toggleAutoSpeak();
  }, [isTTSSpeaking, stopTTS, toggleAutoSpeak]);

  const handleGoToProfile = useCallback(() => {
    router.push('Profile');
  }, []);

  // 稳定内联回调引用，避免传给 MessageList / VoiceInput 时导致子组件无辜重渲染
  const handleForward = useCallback((msg: ChatMessage) => {
    setPendingForwardContent(msg.content);
    setShowHistoryDrawer(true);
  }, []);

  const handleInterrupt = useCallback(() => {
    stopTTS();
    // 同时停止 Agent 生成（如果正在运行）
    if (currentConversationId && activeDeviceKey) {
      stopAgent(currentConversationId, activeDeviceKey).catch(() => {});
    }
  }, [stopTTS, currentConversationId, activeDeviceKey, stopAgent]);

  const handleToggleMode = useCallback(() => {
    setInputMode(m => m === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
  }, []);

  // 语音识别错误处理（稳定引用，避免 VoiceInputWithEngine 无辜重渲染）
  const handleNLSError = useCallback((error: Error) => {
    const errorMsg = error?.message || '';
    if (errorMsg.includes('登录') || errorMsg.includes('authorization') || errorMsg.includes('401')) {
      showSnackbar(t('chat.voiceLoginRequired'));
      router.push('Auth');
    } else {
      showSnackbar(t('chat.voiceRecognitionError') + errorMsg);
    }
  }, [showSnackbar]);

  // 处理选择历史会话
  const handleSelectThread = useCallback((threadId: string) => {
    // 转发模式：发送待转发内容到目标会话
    if (pendingForwardContent) {
      sendMessageToDevice({ type: 'text', text: pendingForwardContent }, { conversationId: threadId, deviceKey: effectiveDeviceKey, projectId: currentProject?.id })
        .then(() => {
          showSnackbar(t('chat.forwardSuccess'));
          setPendingForwardContent(null);
        })
        .catch(() => {
          showSnackbar(t('chat.forwardFailed'));
          setPendingForwardContent(null);
        });
      setShowHistoryDrawer(false);
      return;
    }
    setCurrentConversation(threadId);
    setShowHistoryDrawer(false);
  }, [setCurrentConversation, pendingForwardContent, sendMessageToDevice, currentProject]);



  // 处理新建会话
  const handleNewThread = useCallback(() => {
    // 转发模式：创建新会话并发送待转发内容
    if (pendingForwardContent) {
      createConversation(currentProject?.id || 0, pendingForwardContent)
        .then((newId) => {
            sendMessageToDevice({ type: 'text', text: pendingForwardContent }, { conversationId: newId, deviceKey: effectiveDeviceKey, projectId: currentProject?.id })
            .then(() => showSnackbar(t('chat.forwardSuccess')))
            .catch(() => showSnackbar(t('chat.forwardFailed')));
          setPendingForwardContent(null);
        })
        .catch(() => {
          showSnackbar(t('chat.createThreadFailed'));
          setPendingForwardContent(null);
        });
      setShowHistoryDrawer(false);
      return;
    }
    setCurrentConversation(null);
    setShowHistoryDrawer(false);
  }, [setCurrentConversation, pendingForwardContent, sendMessageToDevice, createConversation, currentProject]);

  // HITL 响应处理
  const handleHITLRespond = useCallback((value: string) => {
    respondToHITL(value);
  }, [respondToHITL]);

  // HITL 取消处理
  const handleHITLCancel = useCallback(() => {
    cancelHITL();
  }, [cancelHITL]);


  // 执行 Rewind
  const executeRewind = useCallback(async (messageId: string, revertFiles: boolean) => {
    if (!currentConversationId) {return;}

    // 立即停止当前语音播放，并清空语音队列
    stopTTS();
    clearTTSQueue();

    try {
      const result = await rewindConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(t('chat.rewindSuccess') + (result?.files_reverted ? ` ${t('chat.filesRevertedSuffix', { count: result?.files_reverted })}` : ''));
      setShowRewindDialog(false);

      if (pendingRewindContent) {
        voiceInputRef.current?.setText(pendingRewindContent);
        setInputMode(InputMode.TEXT);
        setPendingRewindContent('');
      }
    } catch (error: unknown) {
      showSnackbar(t('chat.rewindFailed') + getErrorMessage(error));
    }
  }, [currentConversationId, rewindConversation, pendingRewindContent, stopTTS, clearTTSQueue, t, showSnackbar]);

  // 执行 Retry
  const executeRetry = useCallback(async (messageId: string, revertFiles: boolean) => {
    if (!currentConversationId) {return;}

    // 立即停止当前语音播放，并清空语音队列
    stopTTS();
    clearTTSQueue();

    try {
      const result = await retryConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(t('chat.retrying') + (result?.files_reverted ? ` ${t('chat.filesRevertedSuffix', { count: result?.files_reverted })}` : ''));
      setShowRewindDialog(false);
    } catch (error: unknown) {
      showSnackbar(t('chat.retryFailed') + getErrorMessage(error));
    }
  }, [currentConversationId, retryConversation, stopTTS, clearTTSQueue]);

  // Rewind 处理
  const handleRewind = useCallback((messageId: string) => {
    const currentMessages = useConversationStore.getState().messages;
    const index = currentMessages.findIndex((m) => m.id === messageId);
    if (index === -1) return;

    const msg = currentMessages[index];
    if (msg.role === 'human') {
      setPendingRewindContent(msg.content);
    } else {
      setPendingRewindContent('');
    }

    const subMessages = currentMessages.slice(index);
    const hasFiles = subMessages.some((m) => m.has_file_operations);

    setPendingRewindMessageId(messageId);
    setHasFileOperations(hasFiles);

    if (hasFiles) {
      setShowRewindDialog(true);
    } else {
      // 直接回退，不回退文件
      executeRewind(messageId, false);
    }
  }, [executeRewind]);

  // Retry 处理
  const handleRetry = useCallback((messageId: string) => {
    const currentMessages = useConversationStore.getState().messages;
    const index = currentMessages.findIndex((m) => m.id === messageId);
    if (index === -1) return;

    const subMessages = currentMessages.slice(index + 1);
    const hasFiles = subMessages.some((m) => m.has_file_operations);

    setPendingRetryMessageId(messageId);
    setHasFileOperations(hasFiles);

    if (hasFiles) {
      setShowRewindDialog(true);
    } else {
      // 直接重试，不回退文件
      executeRetry(messageId, false);
    }
  }, [executeRetry]);

  // 添加到记忆
  const handleAddToMemory = useCallback(async (text: string, messageId?: string) => {
    if (!currentProject || !activeDeviceKey) {
      showSnackbar(t('chat.input.noProject'));
      return;
    }

    try {
      await addToMemory(currentProject.id, activeDeviceKey, {
        name: text,
        description: text,
      }, messageId, currentConversationId);
      showSnackbar(t('chat.addedToMemory'));
    } catch (error: unknown) {
      showSnackbar(t('chat.addMemoryFailed') + getErrorMessage(error));
    }
  }, [currentConversationId, currentProject, activeDeviceKey, addToMemory]);

  // 引用消息
  const voiceInputRef = useRef<VoiceInputWithEngineHandle>(null);

  // 引用消息：长按消息后，将消息添加到 VoiceInput 的引用列表
  const handleQuote = useCallback((message: ChatMessage) => {
    if (!message || !message.id) {return;}
    voiceInputRef.current?.addReference({
      type: 'message',
      id: String(message.id),
      name: message.content?.slice(0, 30) || t('chat.fallbackMessage'),
    });
  }, []);

  const isAgentSpeaking = isTTSSpeaking;

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : (Platform.OS === 'harmony' ? 'height' : undefined)}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* ===== 头部 ===== */}
        <View
          style={[
            styles.header,
            Platform.OS === 'harmony' && {
              paddingTop: insets.top + 8,
              paddingBottom: 12,
            },
          ]}
          collapsable={false}
        >
          {/* 历史按钮 */}
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => {
              if (!isLoggedIn) {
                // 未登录时从下往上滑出登录页
                router.push('Auth');
              } else {
                setShowHistoryDrawer(true);
              }
            }}
          >
            <MaterialIcons name="history" size={24} color={colors.primary} />
          </TouchableOpacity>

          {/* 设备选择器 - 点击进入设备列表页面 */}
          <TouchableOpacity
            style={styles.projectSelector}
            onPress={() => router.push('Devices')}
          >
            <MaterialIcons
              name="devices"
              size={18}
              color={selectedDevice ? colors.success : colors.onSurfaceVariant}
            />
            <Text
              variant="titleMedium"
              style={[styles.projectName, { color: selectedDevice ? colors.success : colors.onSurfaceVariant }]}
              numberOfLines={1}
            >
              {selectedDevice?.name || t('chat.selectDevice')}
            </Text>
            <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
          </TouchableOpacity>

          {/* 项目选择器 - 独立于设备，支持全局模式 */}
          <TouchableOpacity
            style={styles.projectSelector}
            onPress={() => {
              if (!isLoggedIn) {
                router.push('Auth');
              } else {
                router.push('Projects');
              }
            }}
          >
            <MaterialIcons
              name={currentProject?.isGlobal ? 'public' : 'folder'}
              size={18}
              color={colors.primary}
            />
            <Text
              variant="titleMedium"
              style={[styles.projectName, { color: colors.onSurface }]}
              numberOfLines={1}
            >
              {currentProject?.name || (isGlobalMode ? t('projects.currentGlobalMode') : t('projects.selectProject'))}
            </Text>
            <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
          </TouchableOpacity>

          {/* 右侧我的按钮 */}
          {__DEV__ ? (
            <Menu
              visible={debugMenuVisible}
              onDismiss={() => setDebugMenuVisible(false)}
              anchor={
                <TouchableOpacity
                  style={styles.iconBtn}
                  onPress={handleGoToProfile}
                  onLongPress={() => setDebugMenuVisible(true)}
                >
                  <MaterialIcons name="person" size={24} color={colors.primary} />
                </TouchableOpacity>
              }
            >
              <Menu.Item
                onPress={() => { debugManager?.injectInitialData(); setDebugMenuVisible(false); }}
                title={t('chat.debug.injectMockData')}
                leadingIcon="database-plus"
              />
              <Menu.Item
                onPress={() => { debugManager?.simulateAIStreaming(); setDebugMenuVisible(false); }}
                title={t('chat.debug.simulateStreaming')}
                leadingIcon="waves"
              />
              <Menu.Item
                onPress={() => { debugManager?.simulateHITLRequest('approval'); setDebugMenuVisible(false); }}
                title={t('chat.debug.simulateHitlApproval')}
                leadingIcon="shield-check"
              />
              <Menu.Item
                onPress={() => { debugManager?.simulateHITLRequest('choice'); setDebugMenuVisible(false); }}
                title={t('chat.debug.simulateHitlChoice')}
                leadingIcon="format-list-bulleted"
              />
              <Menu.Item
                onPress={() => { debugManager?.simulateHITLRequest('text'); setDebugMenuVisible(false); }}
                title={t('chat.debug.simulateHitlText')}
                leadingIcon="text-short"
              />

              <Divider />
              <Menu.Item
                onPress={() => { debugManager?.clearAll(); setDebugMenuVisible(false); }}
                title={t('chat.debug.clearAllData')}
                leadingIcon="delete-sweep"
                titleStyle={{ color: colors.error }}
              />
            </Menu>
          ) : (
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={handleGoToProfile}
            >
              <MaterialIcons name="person" size={24} color={colors.primary} />
            </TouchableOpacity>
          )}
        </View>


        {/* ===== 游客提示（未登录时显示） ===== */}
        {!isLoggedIn && (
          <TouchableOpacity
            style={[styles.guestBanner, { backgroundColor: colors.primaryContainer }]}
            onPress={() => router.push('Auth')}
          >
            <MaterialIcons name="info" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 8 }}>
              {t('chat.guestMode')}
            </Text>
          </TouchableOpacity>
        )}

        {/* ===== Gateway 连接状态提示（登录后非已连接状态时显示） ===== */}
        {isLoggedIn && gatewayConnectionState !== ConnectionState.CONNECTED && (
          <View style={[styles.connectionBanner, {
            backgroundColor:
              gatewayConnectionState === ConnectionState.ERROR ? colors.errorContainer :
              gatewayConnectionState === ConnectionState.RECONNECTING ? colors.warningContainer :
              colors.surfaceVariant,
          }]}>

            <MaterialIcons
              name={
                gatewayConnectionState === ConnectionState.ERROR ? 'error-outline' :
                gatewayConnectionState === ConnectionState.RECONNECTING ? 'sync' :
                'cloud-off'
              }
              size={16}
              color={
                gatewayConnectionState === ConnectionState.ERROR ? colors.error :
                gatewayConnectionState === ConnectionState.RECONNECTING ? colors.warning :
                colors.onSurfaceVariant
              }

            />
            <Text
              variant="bodySmall"
              style={{
                marginLeft: 8,
                color:
                  gatewayConnectionState === ConnectionState.ERROR ? colors.error :
                  gatewayConnectionState === ConnectionState.RECONNECTING ? colors.warning :
                  colors.onSurfaceVariant,

              }}
            >
              {gatewayConnectionState === ConnectionState.CONNECTING ? t('chat.connection.connecting') :
               gatewayConnectionState === ConnectionState.RECONNECTING ? t('chat.connection.reconnecting') :
               gatewayConnectionState === ConnectionState.ERROR ? t('chat.connection.error') :
               t('chat.connection.disconnected')}
            </Text>
          </View>
        )}

        {/* ===== 实时识别文字（独立组件，自行订阅 NLS Store） ===== */}
        <RecognizingBanner />

        {/* ===== HITL 横幅 ===== */}
        <HITLBanner />

        {/* ===== 配额耗尽横幅 ===== */}
        {isQuotaExhausted && (
          <QuotaExhaustedBanner
            title={quotaExhaustedInfo?.title}
            message={quotaExhaustedInfo?.message}
          />
        )}

        {/* ===== 消息列表 / 欢迎界面（核心区域） ===== */}
        <View style={styles.messagesArea}>
          {!hasMessages ? (
            <ChatWelcome />
          ) : (
            <MessageList
              onRewind={handleRewind}
              onRetry={handleRetry}
              onQuote={handleQuote}
              onForward={handleForward}
              onAddToMemory={handleAddToMemory}
              onResend={handleResend}
              isTyping={isAgentProcessing}
              hasMoreMessages={hasMoreMessages}
              isLoadingMessages={isLoadingMessages}
            />
          )}
          {isQuotaExhausted && (
            <QuotaExhaustedCard
              info={quotaExhaustedInfo}
              onContinue={() => {
                clearQuotaExhausted();
                handleSendMessage(t('chat.quota.continuePrompt'));
              }}
            />
          )}
        </View>

        {/* ===== HITL 请求卡片 ===== */}
        {hitlRequest && (
          <HumanRequestCard
            request={hitlRequest}
            onRespond={handleHITLRespond}
            onCancel={handleHITLCancel}
          />
        )}

        {/* ===== 底部输入区（VoiceInput + 新引擎自行管理） ===== */}
        <VoiceInputWithEngine
          ref={voiceInputRef}
          onSendText={handleSendMessage}
          onBeforeStartRecording={handleBeforeStartRecording}
          onFinalResult={handleSendMessage}
          onRecordingEnd={() => {
            if (wakeWordEnabled) {
              startWakeWord().then(() => setIsWakeWordListening(true)).catch(() => {});
            }
          }}
          onError={handleNLSError}
          onInterrupt={handleInterrupt}
          inputMode={inputMode}
          onToggleMode={handleToggleMode}
          autoSpeak={autoSpeak}
          onToggleAutoSpeak={handleToggleAutoSpeak}
          isSpeaking={isTTSSpeaking}
          projectId={currentProject?.id}
          conversationId={currentConversationId || undefined}
          wakeWordEnabled={wakeWordEnabled}
          isWakeWordListening={isWakeWordListening}
          isWakeWordDetected={isWakeWordDetected}
          onToggleWakeWord={toggleWakeWord}
        />

        {/* ===== TTS 自动朗读（副作用组件，自行订阅 messages） ===== */}
        <AutoSpeakHandler speak={speak} enabled={!isStreaming} />

        {/* ===== AI 思考中超时处理（副作用组件） ===== */}
        <AgentProcessingHandler isAgentProcessing={isAgentProcessing} onClear={() => setIsAgentProcessing(false)} />
      </KeyboardAvoidingView>

      {/* ===== TTS 音频播放器已移除，改用原生 VoiceEngine 播放 ===== */}

      {/* ===== Rewind/Retry 确认对话框 ===== */}
      <Portal>
        <Dialog visible={showRewindDialog} onDismiss={() => setShowRewindDialog(false)}>
          <Dialog.Title>{t('chat.rewindDialog.title')}</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              {t('chat.rewindDialog.description')}
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => {
              if (pendingRewindMessageId) {
                executeRewind(pendingRewindMessageId, false);
              } else if (pendingRetryMessageId) {
                executeRetry(pendingRetryMessageId, false);
              }
            }}>
              {t('chat.rewindDialog.keepFiles')}
            </Button>
            <Button onPress={() => {
              if (pendingRewindMessageId) {
                executeRewind(pendingRewindMessageId, true);
              } else if (pendingRetryMessageId) {
                executeRetry(pendingRetryMessageId, true);
              }
            }} mode="contained">
              {t('chat.rewindDialog.restoreFiles')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      {/* ===== Snackbar ===== */}
      <Snackbar
        visible={snackbarVisible}
        onDismiss={() => setSnackbarVisible(false)}
        duration={4000}
      >
        {snackbarMessage}
      </Snackbar>

      {/* ===== 历史会话抽屉 ===== */}
      <HistoryDrawer
        visible={showHistoryDrawer}
        onClose={() => setShowHistoryDrawer(false)}
        projectId={currentProject?.id}
        deviceKey={activeDeviceKey}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
      />
    </View>
  );
}

const isHarmony = Platform.OS === 'harmony';

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  // 头部
  header: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingTop: 0,
    paddingBottom: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  iconBtn: {
    padding: 8,
    marginRight: 4,
  },
  projectSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    ...(isHarmony ? { paddingVertical: 6 } : {}),
  },
  projectName: {
    marginLeft: 6,
    marginRight: 2,
    maxWidth: 120,
  },
  // 游客提示
  guestBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
  },
  connectionBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
  },
  // 识别中提示
  recognizingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
  },
  volumeIndicator: {
    height: 4,
    backgroundColor: '#109C8F',
    borderRadius: 2,
    maxWidth: 50,
  },
  // 消息区域
  messagesArea: {
    flex: 1,
    marginHorizontal: 12,
  },
});
