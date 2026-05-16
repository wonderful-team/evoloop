// 首页 - 语音对话主界面（支持游客模式，使用阿里云 NLS）

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
import {
  MessageList,
  VoiceInputWithNLS,
  VoiceInputWithNLSHandle,
  InputMode,
} from '@/components/voice';
import { HITLBanner, HumanRequestCard } from '@/components/hitl';
import { QuotaExhaustedBanner, QuotaExhaustedCard, HistoryDrawer, AutoSpeakHandler, AgentProcessingHandler, RecognizingBanner, ChatWelcome } from '@/components/chat';
// useNLS 已移到 VoiceInputWithNLS 内部，ChatScreen 不再直接订阅 NLS 高频状态
import { useDeviceControl } from '@/hooks/useDeviceControl';
import { useCommands } from '@/hooks/useCommands';
import { useTTS, useAutoSpeak } from '@/hooks/useTTS';
import { useWakeWord, useWakeWordSettings } from '@/hooks/useWakeWord';
import ReactNativeHapticFeedback from 'react-native-haptic-feedback';
import { useConversationStore } from '@/stores/conversationStore';
import { useTheme } from '@/theme';
import { useAuthStore } from '@/stores/authStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useProjects } from '@/hooks/useProjects';
import { useChatGateway } from '@/hooks/chat/useChatGateway';
import { useChatDeviceSync } from '@/hooks/chat/useChatDeviceSync';
import { ChatMessage, MessageReference } from '@/types/conversation';
import type { ChatAttachment } from '@/services/api/upload';
import Video from 'react-native-video';
import { generateUUID } from '@/utils/uuid';
import { ConnectionState } from '@/services/gateway/types';
import { getErrorMessage, isQuotaError } from '@/utils/error';
import { debugManager } from '@/utils/debugManager';
import { Menu, Divider } from 'react-native-paper';


export default function ChatScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);

  // 从 MC 拉取项目列表（登录后才请求）
  // 从 MC 拉取项目列表（登录后才请求）
  const { currentProject, isGlobalMode, setCurrentProject, setGlobalMode } = useProjects({ autoFetch: isLoggedIn });

  // 输入模式
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);

  // UI 状态
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [showRewindDialog, setShowRewindDialog] = useState(false);
  const [pendingRewindMessageId, setPendingRewindMessageId] = useState<string | null>(null);
  const [pendingRetryMessageId, setPendingRetryMessageId] = useState<string | null>(null);
  const [hasFileOperations, setHasFileOperations] = useState(false);
  const [pendingForwardContent, setPendingForwardContent] = useState<string | null>(null);
  const [isAgentProcessing, setIsAgentProcessing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [debugMenuVisible, setDebugMenuVisible] = useState(false);


  // TTS 音频播放器引用
  const ttsPlayerRef = useRef<Video | null>(null);
  const [ttsAudioUri, setTtsAudioUri] = useState<string | null>(null);
  const ttsOnEndRef = useRef<(() => void) | null>(null);
  const ttsOnErrorRef = useRef<((error: any) => void) | null>(null);

  // Store 状态订阅
  const conversations = useConversationStore((state) => state.conversations);
  const currentConversationId = useConversationStore((state) => state.currentConversationId);
  const activeDeviceKey = useConversationStore((state) => state.activeDeviceKey);
  const hasMessages = useConversationStore((state) => state.messages.length > 0);

  // 方法 - Zustand action 引用稳定，单独 selector
  const loadConversations = useConversationStore((state) => state.loadConversations);
  const setCurrentConversation = useConversationStore((state) => state.setCurrentConversation);
  const createConversation = useConversationStore((state) => state.createConversation);
  const addMessage = useConversationStore((state) => state.addMessage);
  const loadMessages = useConversationStore((state) => state.loadMessages);
  const syncMessages = useConversationStore((state) => state.syncMessages);
  const updateMessageStatus = useConversationStore((state) => state.updateMessageStatus);
  const rewindConversation = useConversationStore((state) => state.rewindConversation);
  const retryConversation = useConversationStore((state) => state.retryConversation);
  const addToMemory = useConversationStore((state) => state.addToMemory);

  // TTS
  const { speak, enqueue: enqueueTTS, clearQueue: clearTTSQueue, stop: stopTTS, isSpeaking: isTTSSpeaking, setAudioPlayer, setOnStop } = useTTS();

  // SSE 流式状态
  const streamMessageIdRef = useRef<string | null>(null);
  const ttsBufferRef = useRef('');

  // 清理 markdown 标记，避免 TTS 朗读 ** * 等符号
  const cleanForTTS = useCallback((text: string): string => {
    return text
      .replace(/\*\*(.+?)\*\*/g, '$1')   // **bold**
      .replace(/\*(.+?)\*/g, '$1')         // *italic*
      .replace(/`{1,3}(.+?)`{1,3}/g, '$1') // `code` / ```code```
      .replace(/[#>\-\[\]\(\)]/g, '')     // markdown 符号
      .trim();
  }, []);

  // 流式 TTS：按标点切分句子 + 超过 8 字强制切分
  const flushTTSBuffer = useCallback(() => {
    let buffer = ttsBufferRef.current;
    console.log('[flushTTSBuffer] raw buffer:', buffer);

    const sentences: string[] = [];
    let lastIndex = 0;

    // 1. 按标点切分（句号/问号/感叹号优先，逗号/分号/换行次之）
    const punctuationRegex = /(.+?[。！？.!?；;\n]+)/g;
    let match;
    while ((match = punctuationRegex.exec(buffer)) !== null) {
      const cleaned = cleanForTTS(match[1]);
      if (cleaned.length >= 2) {
        sentences.push(cleaned);
      }
      lastIndex = punctuationRegex.lastIndex;
    }

    // 2. 逗号切分（积累 ≥ 8 字时遇到逗号就切，避免长列举积压）
    buffer = buffer.slice(lastIndex);
    const commaRegex = /(.{8,}?[，,])\s*/g;
    let commaMatch;
    while ((commaMatch = commaRegex.exec(buffer)) !== null) {
      const cleaned = cleanForTTS(commaMatch[1]);
      if (cleaned.length >= 4) {
        sentences.push(cleaned);
      }
      lastIndex = commaRegex.lastIndex;
    }

    // 3. 兜底：剩余 buffer 超过 8 个有效字符，强制切分播放
    buffer = buffer.slice(lastIndex);
    const cleanedRemaining = cleanForTTS(buffer);
    if (cleanedRemaining.length >= 8) {
      sentences.push(cleanedRemaining);
      lastIndex = ttsBufferRef.current.length;
      buffer = '';
    }

    console.log('[flushTTSBuffer] sentences found:', sentences.length, sentences);
    if (sentences.length > 0) {
      ttsBufferRef.current = buffer;
      sentences.forEach((sentence) => {
        console.log('[flushTTSBuffer] enqueueTTS:', sentence);
        enqueueTTS(sentence);
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
  const { autoSpeak, toggleAutoSpeak } = useAutoSpeak();

  // 唤醒词设置
  const { enabled: wakeWordEnabled, toggleWakeWord } = useWakeWordSettings();

  // 设置音频播放器
  useEffect(() => {
    setAudioPlayer((uri: string, onEnd: () => void, onError: (error: any) => void) => {
      setTtsAudioUri(uri);
      ttsOnEndRef.current = onEnd;
      ttsOnErrorRef.current = onError;
    });
  }, [setAudioPlayer]);

  // 注册 TTS 停止回调：stopTTS() 被调用时自动卸载 Video 组件（彻底停止音频播放）
  useEffect(() => {
    setOnStop(() => {
      setTtsAudioUri(null);
      ttsOnEndRef.current = null;
      ttsOnErrorRef.current = null;
    });
  }, [setOnStop]);

  // Snackbar 工具函数（提前定义，供下方回调使用）
  const showSnackbar = useCallback((message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  }, []);

  const {
    isListening: isWakeWordListening,
    isWakeWordDetected,
    startListening: startWakeWord,
    stopListening: stopWakeWord,
  } = useWakeWord({
    // eslint-disable-next-line react-hooks/exhaustive-deps
    onWake: (detectedWord: string) => {
      // 1. 停止唤醒词监听（释放麦克风，避免与 NLS 冲突）
      stopWakeWord();
      // 2. 打断当前 TTS 和 Agent 生成（让用户可以直接开始新对话）
      stopTTS();
      const currentId = useConversationStore.getState().currentConversationId;
      if (currentId) {
        stopAgent(currentId, activeDeviceKey).catch(() => {});
      }
      // 3. Haptic 震动反馈
      ReactNativeHapticFeedback.trigger('notificationSuccess', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: false,
      });
      // 4. 显示提示
      showSnackbar(t('chat.wakeWordDetected', { word: detectedWord }));
      // 5. 自动启动 NLS 语音识别
      voiceInputRef.current?.startNLS();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    onSpeechDetected: (text: string) => {
      // TTS 播放时检测到非唤醒词的人声，直接说话打断
      if (isTTSSpeaking) {
        console.log('[ChatScreen] 语音打断 TTS:', text);
        stopTTS();
        const currentId = useConversationStore.getState().currentConversationId;
        if (currentId) {
          stopAgent(currentId, activeDeviceKey).catch(() => {});
        }
        showSnackbar(t('chat.interrupted'));
        voiceInputRef.current?.startNLS();
      }
    },
  });

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
      // 链路一（转发 Desktop）：显示发送成功，等待后台轮询
      showSnackbar(t('chat.messageSent'));
    }
  }, [setCurrentConversation, addMessage, showSnackbar]);

  const {
    state: deviceState,
    isSending,
    hitlRequest,
    isWaitingForHuman: isHITLWaiting,
    pendingCommand,
    quotaExhaustedInfo,
    isQuotaExhausted,
    sendMessage: sendMessageToDevice,
    confirmCommand,
    respondToHITL,
    cancelHITL,
    clearQuotaExhausted,
  } = useDeviceControl({
    onError: handleDeviceError,
    onCommandReady: () => {},
    onHITLRequest: () => {},
    onMessageSent: handleMessageSent,
  });

  // 从 deviceStore 获取当前选中的设备
  const { currentDevice: selectedDevice } = useDeviceStore();

  // Gateway WebSocket 连接与设备-对话同步（提取为自定义 hooks）
  const { gatewayConnectionState, setCurrentConversationId } = useChatGateway({
    isLoggedIn,
    syncMessages,
    onAgentRunCompleted: () => {
      setIsAgentProcessing(false);
    }
  });
  const { deviceConversationMap, saveDeviceConversation } = useChatDeviceSync({
    isLoggedIn,
    selectedDeviceKey: selectedDevice?.deviceKey,
    projectId: currentProject?.id,
    setGlobalMode,
    loadConversations,
  });

  // 同步 currentConversationId 到 Gateway hook（避免 WebSocket 因 id 变化而重连）
  useEffect(() => {
    setCurrentConversationId(currentConversationId);
  }, [currentConversationId, setCurrentConversationId]);

  const clearAgentProcessing = useCallback(() => {
    setIsAgentProcessing(false);
  }, []);

  useEffect(() => {
    // 只有在未选择设备（全局 AI 模式）时，项目切换才触发这里的列表加载
    // 已选择设备时，由 useChatDeviceSync 内部处理级联加载
    if (isLoggedIn && !selectedDevice?.deviceKey) {
      if (currentProject) {
        setCurrentProject(null); // 清除具体的项目选择，变为“选择项目”占位状态
      }
      setCurrentConversation(null); // 立即重置
      loadConversations(0, true); // 强制请求 0+0 数据
    }
  }, [isLoggedIn, currentProject?.id, currentProject?.isGlobal, selectedDevice?.deviceKey, loadConversations, setGlobalMode]);

  // 重发失败消息
  const handleResend = useCallback(async (message: ChatMessage) => {
    updateMessageStatus(message.id, 'sending');
    try {
      await sendMessageToDevice({
        type: 'text',
        text: message.content,
      }, {
        conversationId: currentConversationId || undefined,
        deviceKey: selectedDevice?.deviceKey,
        references: message.references,
      });
      updateMessageStatus(message.id, 'sent');
    } catch (error: unknown) {
      updateMessageStatus(message.id, 'failed');
      const errorText = getErrorMessage(error);
      if (!isQuotaError(error)) {
        showSnackbar(t('chat.sendFailed') + errorText);
      }
    }
  }, [currentConversationId, sendMessageToDevice, selectedDevice, updateMessageStatus]);

  // 发送消息（HTTP 版本）
  const handleSendMessage = useCallback(async (text: string, options?: { attachments?: ChatAttachment[]; references?: MessageReference[] }) => {
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

    // 如果有附件，将附件信息拼接到消息文本中
    if (options?.attachments && options.attachments.length > 0) {
      const attachmentTexts = options.attachments.map(att => {
        if (att.type === 'image' || att.type === 'video') {
          return `![${att.name}](${att.url})`;
        }
        return `[${t('chat.attachmentLabel', { name: att.name })}](${att.url})`;
      }).join('\n');
      finalText = finalText ? `${finalText}\n\n${attachmentTexts}` : attachmentTexts;
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
      attachments: options?.attachments ? options.attachments.map(a => ({
        id: a.id || `att-${Date.now()}`,
        type: (a.type === 'image' || a.type === 'audio' || a.type === 'file') ? a.type as any : 'file',
        url: a.url,
        name: a.name,
      })) : undefined,
    };
    addMessage(userMessage);

    // 清空 TTS buffer（新对话开始）
    ttsBufferRef.current = '';

    // 通过 HTTP 发送消息到 Gateway
    try {
      await sendMessageToDevice({
        type: 'text',
        text: finalText,
      }, {
        conversationId: conversationId || undefined,
        deviceKey: selectedDevice?.deviceKey,
        references: options?.references,
        // 流式回调（仅链路二生效）
        onStreamStart: () => {
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
            enqueueTTS(remaining);
          }
          ttsBufferRef.current = '';
        },
      });

      // 发送成功：标记为已送达
      updateMessageStatus(userMessage.id, 'sent');

      // 链路一（Desktop）：显示 AI 思考中指示器
      if (selectedDevice?.deviceKey) {
        setIsAgentProcessing(true);
      }

      // 发送成功：更新设备-对话映射
      if (selectedDevice?.deviceKey && conversationId) {
        saveDeviceConversation(selectedDevice.deviceKey, conversationId);
      }
    } catch (error: unknown) {
      // 发送失败：标记为失败
      updateMessageStatus(userMessage.id, 'failed');

      const errorText = getErrorMessage(error);
      // 配额耗尽由专门的 UI 卡片提示，其他错误用 snackbar
      if (!isQuotaError(error)) {
        showSnackbar(t('chat.sendFailed') + errorText);
      }
    }
  }, [currentConversationId, sendMessageToDevice, selectedDevice, addMessage, saveDeviceConversation, updateMessageStatus, updateStreamMessage, flushTTSBuffer, enqueueTTS, cleanForTTS]);

  // 请求麦克风权限
  const requestMicrophonePermission = useCallback(async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: t('chat.micPermission.title'),
            message: t('chat.micPermission.message'),
            buttonPositive: t('chat.micPermission.allow'),
            buttonNegative: t('chat.micPermission.deny'),
          }
        );
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.error('请求录音权限失败:', err);
        return false;
      }
    }
    // iOS 权限在 Info.plist 中配置，首次使用时会自动请求
    return true;
  }, []);

  // ========== 按住说话模式（前置检查，实际录音由 VoiceInputWithNLS 内部管理） ==========
  const handleBeforeStartRecording = useCallback(async (): Promise<boolean> => {
    // 未登录时提示并跳转登录页
    if (!isLoggedIn) {
      showSnackbar(t('chat.voiceLoginRequired'));
      router.push('Auth');
      return false;
    }

    // 请求录音权限
    const hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
      showSnackbar(t('chat.voicePermissionDenied'));
      return false;
    }

    // 停止唤醒词监听，释放麦克风给 NLS 使用
    if (wakeWordEnabled) {
      await stopWakeWord();
    }

    return true;
  }, [isLoggedIn, requestMicrophonePermission, showSnackbar, wakeWordEnabled, stopWakeWord]);

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
    if (currentConversationId) {
      stopAgent(currentConversationId).catch(() => {});
    }
  }, [stopTTS, currentConversationId, stopAgent]);

  const handleToggleMode = useCallback(() => {
    setInputMode(m => m === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
  }, []);

  // NLS 错误处理（稳定引用，避免 VoiceInputWithNLS 无辜重渲染）
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
      sendMessageToDevice({ type: 'text', text: pendingForwardContent }, { conversationId: threadId, deviceKey: selectedDevice?.deviceKey })
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
    // 更新设备-对话映射
    if (selectedDevice?.deviceKey) {
      saveDeviceConversation(selectedDevice.deviceKey, threadId);
    }
  }, [setCurrentConversation, selectedDevice, saveDeviceConversation, pendingForwardContent, sendMessageToDevice]);



  // 处理新建会话
  const handleNewThread = useCallback(() => {
    // 转发模式：创建新会话并发送待转发内容
    if (pendingForwardContent) {
      createConversation(currentProject?.id || 0, pendingForwardContent)
        .then((newId) => {
          sendMessageToDevice({ type: 'text', text: pendingForwardContent }, { conversationId: newId, deviceKey: selectedDevice?.deviceKey })
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
    // 清除当前设备的对话映射（新对话尚未发送消息，不绑定设备）
    if (selectedDevice?.deviceKey) {
      saveDeviceConversation(selectedDevice.deviceKey, null);
    }
  }, [setCurrentConversation, selectedDevice, saveDeviceConversation, pendingForwardContent, sendMessageToDevice, createConversation, currentProject]);

  // HITL 响应处理
  const handleHITLRespond = useCallback((value: string) => {
    respondToHITL(value);
  }, [respondToHITL]);

  // HITL 取消处理
  const handleHITLCancel = useCallback(() => {
    cancelHITL();
  }, [cancelHITL]);


  // Rewind 处理
  const handleRewind = useCallback((messageId: string, hasFiles: boolean) => {
    setPendingRewindMessageId(messageId);
    setHasFileOperations(hasFiles);

    if (hasFiles) {
      setShowRewindDialog(true);
    } else {
      // 直接回退，不回退文件
      executeRewind(messageId, false);
    }
  }, []);

  // Retry 处理
  const handleRetry = useCallback((messageId: string, hasFiles: boolean) => {
    setPendingRetryMessageId(messageId);
    setHasFileOperations(hasFiles);

    if (hasFiles) {
      setShowRewindDialog(true);
    } else {
      // 直接重试，不回退文件
      executeRetry(messageId, false);
    }
  }, []);

  // 执行 Rewind
  const executeRewind = useCallback(async (messageId: string, revertFiles: boolean) => {
    if (!currentConversationId) {return;}

    try {
      const result = await rewindConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(t('chat.rewindSuccess') + (result.files_reverted ? ` (${t('chat.filesReverted', { count: result.files_reverted })})` : ''));
      setShowRewindDialog(false);
    } catch (error: unknown) {
      showSnackbar(t('chat.rewindFailed') + getErrorMessage(error));
    }
  }, [currentConversationId, rewindConversation]);

  // 执行 Retry
  const executeRetry = useCallback(async (messageId: string, revertFiles: boolean) => {
    if (!currentConversationId) {return;}

    try {
      const result = await retryConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(t('chat.retrying') + (result.files_reverted ? ` (${t('chat.filesReverted', { count: result.files_reverted })})` : ''));
      setShowRewindDialog(false);
    } catch (error: unknown) {
      showSnackbar(t('chat.retryFailed') + getErrorMessage(error));
    }
  }, [currentConversationId, retryConversation]);

  // 添加到记忆
  const handleAddToMemory = useCallback(async (text: string) => {
    if (!currentProject) {
      showSnackbar(t('chat.input.noProject'));
      return;
    }
    if (currentProject.isGlobal) {
      showSnackbar(t('chat.globalModeNoMemory'));
      return;
    }

    try {
      await addToMemory(currentProject.id, {
        name: t('chat.learnFromConversation'),
        description: text,
      });
      showSnackbar(t('chat.addedToMemory'));
    } catch (error: unknown) {
      showSnackbar(t('chat.addMemoryFailed') + getErrorMessage(error));
    }
  }, [currentProject, addToMemory]);

  // 引用消息
  const voiceInputRef = useRef<VoiceInputWithNLSHandle>(null);

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
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* ===== 头部 ===== */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
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
          </View>

          {/* 右侧我的按钮 */}
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
              onPress={() => { debugManager.injectInitialData(); setDebugMenuVisible(false); }} 
              title="注入模拟数据" 
              leadingIcon="database-plus"
            />
            <Menu.Item 
              onPress={() => { debugManager.simulateAIStreaming(); setDebugMenuVisible(false); }} 
              title="模拟流式输出" 
              leadingIcon="waves"
            />
            <Menu.Item 
              onPress={() => { debugManager.simulateHITLRequest('approval'); setDebugMenuVisible(false); }} 
              title="模拟 HITL (授权)" 
              leadingIcon="shield-check"
            />
            <Menu.Item 
              onPress={() => { debugManager.simulateHITLRequest('choice'); setDebugMenuVisible(false); }} 
              title="模拟 HITL (选择)" 
              leadingIcon="format-list-bulleted"
            />
            <Menu.Item 
              onPress={() => { debugManager.simulateHITLRequest('text'); setDebugMenuVisible(false); }} 
              title="模拟 HITL (文本)" 
              leadingIcon="text-short"
            />

            <Divider />
            <Menu.Item 
              onPress={() => { debugManager.clearAll(); setDebugMenuVisible(false); }} 
              title="清空所有数据" 
              leadingIcon="delete-sweep"
              titleStyle={{ color: colors.error }}
            />
          </Menu>
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

        {/* ===== 底部输入区（VoiceInput + NLS 自行管理） ===== */}
        <VoiceInputWithNLS
          ref={voiceInputRef}
          onSendText={handleSendMessage}
          onBeforeStartRecording={handleBeforeStartRecording}
          onFinalResult={handleSendMessage}
          onRecordingEnd={() => {
            if (wakeWordEnabled) {
              startWakeWord();
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

      {/* ===== TTS 音频播放器（隐藏） ===== */}
      {/* paused 绑定 isTTSSpeaking：stopTTS() 后自动暂停，不需要手动清空 ttsAudioUri */}
      {ttsAudioUri && (
        <Video
          ref={ttsPlayerRef}
          source={{ uri: ttsAudioUri }}
          // audioOnly removed in react-native-video v6
          paused={!isTTSSpeaking}
          onEnd={() => {
            setTtsAudioUri(null);
            ttsOnEndRef.current?.();
            ttsOnEndRef.current = null;
            ttsOnErrorRef.current = null;
          }}
          onError={(error) => {
            setTtsAudioUri(null);
            ttsOnErrorRef.current?.(error);
            ttsOnEndRef.current = null;
            ttsOnErrorRef.current = null;
          }}
          style={{ width: 0, height: 0 }}
        />
      )}

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
        deviceKey={selectedDevice?.deviceKey}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  // 头部
  header: {
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
