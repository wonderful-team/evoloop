// 首页 - 语音对话主界面（支持游客模式，使用阿里云 NLS）

import React, { useCallback, useEffect, useState, useRef } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  StatusBar,
  Alert,
  Modal,
  Animated,
  PermissionsAndroid,
} from 'react-native';
import { router } from '@/utils/navigation';
import { useTranslation } from 'react-i18next';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import {
  Text,
  Snackbar,
  Menu,
  Portal,
  Dialog,
  Button,
} from 'react-native-paper';
import {
  MessageList,
  VoiceInput,
  InputMode,
} from '@/components/voice';
import { HITLBanner, HumanRequestCard } from '@/components/hitl';
import { ThreadList, QuotaExhaustedBanner, QuotaExhaustedCard } from '@/components/chat';
import { useNLS } from '@/hooks/useNLS';
import { useDeviceControl } from '@/hooks/useDeviceControl';
import { useTTS, useAutoSpeak } from '@/hooks/useTTS';
import { useWakeWord, useWakeWordSettings } from '@/hooks/useWakeWord';
import { useConversationStore } from '@/stores/conversationStore';
import { useProjectStore } from '@/stores/projectStore';
import { useTheme } from '@/theme';
import { useAuthStore } from '@/stores/authStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { Project, Device } from '@/types';
import { ChatMessage, MessageReference } from '@/types/conversation';
import type { ChatAttachment } from '@/services/api/upload';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Video from 'react-native-video';
import { generateUUID } from '@/utils/uuid';

// 游客默认项目
const GUEST_PROJECTS: Project[] = [
  { id: 0, name: '示例项目', rootPath: '/demo', description: '游客体验项目', isActive: true },
];

export default function ChatScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const authStore = useAuthStore();
  const isLoggedIn = authStore.isLoggedIn;

  console.log('[ChatScreen] Render - authStore:', {
    isLoggedIn,
    token: authStore.token ? 'exists' : 'null',
    hasUserInfo: !!authStore.userInfo
  });
  const { currentProject } = useProjectStore();

  // 输入模式
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);

  // UI 状态
  const [showProjectMenu, setShowProjectMenu] = useState(false);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [showRewindDialog, setShowRewindDialog] = useState(false);
  const [pendingRewindMessageId, setPendingRewindMessageId] = useState<string | null>(null);
  const [pendingRetryMessageId, setPendingRetryMessageId] = useState<string | null>(null);
  const [hasFileOperations, setHasFileOperations] = useState(false);

  // 设备-对话映射缓存
  const [deviceConversationMap, setDeviceConversationMap] = useState<Record<string, string>>({});

  // 加载设备-对话映射
  useEffect(() => {
    AsyncStorage.getItem('device_conversation_map').then((map) => {
      if (map) {
        try {
          setDeviceConversationMap(JSON.parse(map));
        } catch (e) {
          console.error('[ChatScreen] Failed to parse device_conversation_map:', e);
        }
      }
    });
  }, []);

  // 保存设备-对话映射
  const saveDeviceConversation = useCallback(async (deviceKey: string, conversationId: string | null) => {
    const map = { ...deviceConversationMap };
    if (conversationId) {
      map[deviceKey] = conversationId;
    } else {
      delete map[deviceKey];
    }
    setDeviceConversationMap(map);
    await AsyncStorage.setItem('device_conversation_map', JSON.stringify(map));
  }, [deviceConversationMap]);

  // 设备变化时：恢复该设备的最近对话，没有则显示 Welcome
  useEffect(() => {
    if (!isLoggedIn || !selectedDevice?.deviceKey) return;

    const conversationId = deviceConversationMap[selectedDevice.deviceKey];
    if (conversationId) {
      // 检查该对话是否还在列表中（可能被删除）
      const exists = conversations.some(c => c.id === conversationId);
      if (exists && currentConversationId !== conversationId) {
        console.log('[ChatScreen] Restore device conversation:', selectedDevice.deviceKey, '->', conversationId);
        setCurrentConversation(conversationId);
      } else if (!exists) {
        // 对话已被删除，清除映射
        saveDeviceConversation(selectedDevice.deviceKey, null);
        if (currentConversationId !== null) {
          setCurrentConversation(null);
        }
      }
    } else {
      // 没有映射，显示 Welcome
      if (currentConversationId !== null) {
        setCurrentConversation(null);
      }
    }
  }, [selectedDevice?.deviceKey, isLoggedIn, deviceConversationMap, conversations, currentConversationId, setCurrentConversation, saveDeviceConversation]);

  // 项目状态
  const [projects, setProjects] = useState<Project[]>(GUEST_PROJECTS);
  const [currentProjectState, setCurrentProjectState] = useState<Project>(GUEST_PROJECTS[0]);

  // TTS 音频播放器引用
  const ttsPlayerRef = useRef<Video | null>(null);
  const [ttsAudioUri, setTtsAudioUri] = useState<string | null>(null);

  // Store
  const {
    messages,
    conversations,
    currentConversationId,
    loadConversations,
    setCurrentConversation,
    createConversation,
    addMessage,
    rewindConversation,
    retryConversation,
    addToMemory,
  } = useConversationStore();

  // TTS
  const { speak, stop: stopTTS, isSpeaking: isTTSSpeaking, setAudioPlayer } = useTTS();
  const { autoSpeak, toggleAutoSpeak } = useAutoSpeak();

  // 唤醒词
  const { wakeWordEnabled, isListening: isWakeWordListening, startListening: startWakeWord, stopListening: stopWakeWord } = useWakeWordSettings();

  // 设置音频播放器
  useEffect(() => {
    setAudioPlayer((uri: string, onEnd: () => void, onError: (error: any) => void) => {
      setTtsAudioUri(uri);
    });
  }, [setAudioPlayer]);

  // 加载项目
  useEffect(() => {
    const loadProjects = async () => {
      if (!isLoggedIn) {
        const saved = await AsyncStorage.getItem('guest_current_project');
        if (saved) setCurrentProjectState(JSON.parse(saved));
      } else if (currentProject) {
        setCurrentProjectState(currentProject);
      }
    };
    loadProjects();
  }, [isLoggedIn, currentProject]);

  // ========== NLS 语音识别 ==========
  const {
    state: nlsState,
    isRecording: nlsIsRecording,
    currentText: nlsCurrentText,
    volume: nlsVolume,
    start: startNLS,
    stop: stopNLS,
  } = useNLS({
    onResult: (text, isFinal) => {
      console.log('[ChatScreen] NLS onResult:', { text: text.substring(0, 30), isFinal });
      if (isFinal) {
        // 一句话识别完成，发送给后端对话
        handleSendMessage(text);
      }
    },
    onError: (error: any) => {
      const errorMsg = error?.message || '';
      // 检查是否为登录相关错误
      if (errorMsg.includes('登录') || errorMsg.includes('authorization') || errorMsg.includes('401')) {
        showSnackbar('语音功能需要登录');
        router.push('Auth');
      } else {
        showSnackbar('语音识别错误: ' + errorMsg);
      }
    },
  });

  // ========== 设备控制（HTTP 版本） ==========
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
    onError: (error: any) => showSnackbar('发送失败: ' + error.message),
    onCommandReady: (command) => {
      console.log('指令待确认:', command);
    },
    onHITLRequest: (request) => {
      console.log('HITL 请求:', request);
    },
    onMessageSent: (result) => {
      console.log('消息已发送:', result);
      // 链路二（直连 LLM）：立即显示 AI 回复
      if (result.aiMessage) {
        const aiMessage: ChatMessage = {
          id: generateUUID(),
          role: 'assistant',
          content: result.aiMessage,
          timestamp: Date.now(),
          isComplete: true,
        };
        addMessage(aiMessage);
        showSnackbar('AI 回复已接收');
      } else {
        // 链路一（转发 Desktop）：显示发送成功，等待后台轮询
        showSnackbar('消息已发送');
      }
    },
  });

  // 从 deviceStore 获取当前选中的设备
  const { currentDevice: selectedDevice } = useDeviceStore();

  // 自动朗读 AI 回复
  useEffect(() => {
    if (autoSpeak && messages.length > 0) {
      const lastMessage = messages[messages.length - 1];
      if (lastMessage.role === 'assistant' && lastMessage.isComplete) {
        speak(lastMessage.content);
      }
    }
  }, [messages, autoSpeak, speak]);

  useEffect(() => {
    console.log('[ChatScreen] loadConversations effect triggered, isLoggedIn:', isLoggedIn);
    if (isLoggedIn) {
      console.log('[ChatScreen] Calling loadConversations');
      loadConversations(undefined, true);
    }
  }, [isLoggedIn]);

  const showSnackbar = (message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  };

  // 发送消息（HTTP 版本）
  const handleSendMessage = useCallback(async (text: string, options?: { attachments?: ChatAttachment[]; references?: MessageReference[] }) => {
    console.log('[ChatScreen] handleSendMessage called:', text.substring(0, 50) + '...', { currentConversationId });

    // deviceKey 是可选的，如果没有选择设备，直接通过 Gateway 和 LLM 对话
    // 不需要强制选择设备

    // 如果没有会话，先创建会话
    let conversationId = currentConversationId;
    if (!conversationId) {
      console.log('[ChatScreen] No conversation, creating new one...');
      try {
        conversationId = await createConversation(currentProjectState?.id);
        console.log('[ChatScreen] Created conversation:', conversationId);
      } catch (error: any) {
        console.error('[ChatScreen] Failed to create conversation:', error);
        showSnackbar('创建会话失败: ' + error.message);
        return;
      }
    }

    let finalText = text;

    // 如果有引用，添加到消息中
    if (options?.references && options.references.length > 0) {
      const refText = options.references.map(r => `@${r.name}`).join(' ');
      finalText = `${refText} ${text}`;
    }

    // 如果有附件，先上传再发送
    if (options?.attachments && options.attachments.length > 0) {
      // 处理附件上传逻辑
      // ...
    }

    // 立即将用户消息添加到本地消息列表（乐观更新）
    const userMessage: ChatMessage = {
      id: generateUUID(),
      role: 'user',
      content: finalText,
      timestamp: Date.now(),
      isComplete: true,
    };
    addMessage(userMessage);

    // 通过 HTTP 发送消息到 Gateway
    try {
      await sendMessageToDevice({
        type: 'text',
        text: finalText,
      }, {
        conversationId: conversationId || undefined,
        deviceKey: selectedDevice?.deviceKey,
        references: options?.references,
      });

      // 发送成功：更新设备-对话映射
      if (selectedDevice?.deviceKey && conversationId) {
        saveDeviceConversation(selectedDevice.deviceKey, conversationId);
      }
    } catch (error: any) {
      const errorText = error?.message || '未知错误';
      // 配额耗尽由专门的 UI 卡片提示，其他错误用 snackbar
      if (!error?.__quota_exhausted) {
        console.log('[ChatScreen] Send failed:', errorText);
        showSnackbar('发送失败: ' + errorText);
      } else {
        console.log('[ChatScreen] Send failed (quota exhausted):', errorText);
      }
    }
  }, [currentConversationId, sendMessageToDevice, createConversation, currentProjectState, selectedDevice, addMessage, saveDeviceConversation]);

  // 请求麦克风权限
  const requestMicrophonePermission = useCallback(async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: '需要录音权限',
            message: '语音对话需要使用麦克风，请允许访问。',
            buttonPositive: '允许',
            buttonNegative: '拒绝',
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

  // ========== 按住说话模式 ==========
  const handleVoicePressIn = useCallback(async () => {
    console.log('[VoicePressIn] 按住语音按钮');
    if (isTTSSpeaking) {
      // 打断 AI 讲话
      stopTTS();
      return;
    }

    // 未登录时提示并跳转登录页
    if (!isLoggedIn) {
      console.log('[VoicePressIn] 未登录，跳转到登录页');
      showSnackbar('语音功能需要登录');
      router.push('Auth');
      return;
    }

    // 请求录音权限
    const hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
      showSnackbar('没有录音权限，无法使用语音功能');
      return;
    }

    // 启动 NLS 录音
    try {
      console.log('[VoicePressIn] 启动 NLS 录音');
      await startNLS();
      console.log('[VoicePressIn] NLS 启动成功');
    } catch (error: any) {
      console.error('[VoicePressIn] NLS 启动失败:', error);
      showSnackbar('语音识别启动失败: ' + error.message);
    }
  }, [isTTSSpeaking, isLoggedIn, startNLS, stopTTS, requestMicrophonePermission]);

  const handleVoicePressOut = useCallback(async () => {
    console.log('[VoicePressOut] 松开语音按钮');
    if (nlsIsRecording) {
      console.log('[VoicePressOut] 停止 NLS 录音');
      await stopNLS();
      // 注意：实际发送在 useNLS 的 onResult 回调中处理（isFinal=true 时）
    }
  }, [nlsIsRecording, stopNLS]);

  const handleSwitchProject = useCallback(async (project: Project) => {
    setCurrentProjectState(project);
    setShowProjectMenu(false);
    if (!isLoggedIn) {
      await AsyncStorage.setItem('guest_current_project', JSON.stringify(project));
    }
    showSnackbar(`已切换到: ${project.name}`);
  }, [isLoggedIn]);

  const handleGoToProfile = useCallback(() => {
    router.push('Profile');
  }, []);

  // 处理选择历史会话
  const handleSelectThread = useCallback((threadId: string) => {
    setCurrentConversation(threadId);
    setShowHistoryDrawer(false);
    // 更新设备-对话映射
    if (selectedDevice?.deviceKey) {
      saveDeviceConversation(selectedDevice.deviceKey, threadId);
    }
  }, [setCurrentConversation, selectedDevice, saveDeviceConversation]);

  // 抽屉动画
  const slideAnim = useRef(new Animated.Value(-320)).current;

  useEffect(() => {
    if (showHistoryDrawer) {
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 250,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(slideAnim, {
        toValue: -320,
        duration: 200,
        useNativeDriver: true,
      }).start();
    }
  }, [showHistoryDrawer]);

  // 处理新建会话
  const handleNewThread = useCallback(() => {
    setCurrentConversation(null);
    setShowHistoryDrawer(false);
    // 清除当前设备的对话映射（新对话尚未发送消息，不绑定设备）
    if (selectedDevice?.deviceKey) {
      saveDeviceConversation(selectedDevice.deviceKey, null);
    }
  }, [setCurrentConversation, selectedDevice, saveDeviceConversation]);

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
    if (!currentConversationId) return;

    try {
      const result = await rewindConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(`已回退到指定位置${result.files_reverted ? ` (${result.files_reverted} 个文件已恢复)` : ''}`);
      setShowRewindDialog(false);
    } catch (error: any) {
      showSnackbar('回退失败: ' + error.message);
    }
  }, [currentConversationId, rewindConversation]);

  // 执行 Retry
  const executeRetry = useCallback(async (messageId: string, revertFiles: boolean) => {
    if (!currentConversationId) return;

    try {
      const result = await retryConversation(currentConversationId, {
        message_id: messageId,
        revert_files: revertFiles,
      });

      showSnackbar(`正在重试${result.files_reverted ? ` (${result.files_reverted} 个文件已恢复)` : ''}`);
      setShowRewindDialog(false);
    } catch (error: any) {
      showSnackbar('重试失败: ' + error.message);
    }
  }, [currentConversationId, retryConversation]);

  // 添加到记忆
  const handleAddToMemory = useCallback(async (text: string) => {
    if (!currentProjectState?.id) {
      showSnackbar('请先选择项目');
      return;
    }

    try {
      await addToMemory(currentProjectState.id, {
        name: '从对话学习',
        description: text,
      });
      showSnackbar('已添加到记忆');
    } catch (error: any) {
      showSnackbar('添加记忆失败: ' + error.message);
    }
  }, [currentProjectState?.id, addToMemory]);

  // 引用消息
  const handleQuote = useCallback((message: ChatMessage) => {
    // 引用消息的逻辑在 VoiceInput 中处理
    // 这里可以触发一个全局事件或更新状态
  }, []);

  // 状态（仅 NLS）
  // 将 NLSState 映射为 VoiceSessionState
  const mapNLSStateToVoiceState = (nlsState: string): string => {
    switch (nlsState) {
      case 'connected': return 'listening';  // NLS 连接成功 = 正在监听
      case 'error': return 'idle';           // 错误状态显示为 idle
      default: return nlsState;              // idle, connecting, recognizing 直接映射
    }
  };
  const combinedState = nlsIsRecording ? mapNLSStateToVoiceState(nlsState) : 'idle';
  const isAgentSpeaking = isTTSSpeaking;

  // 调试：监听 NLS 状态变化
  useEffect(() => {
    console.log('[ChatScreen] NLS state changed:', { nlsState, nlsIsRecording, combinedState });
  }, [nlsState, nlsIsRecording, combinedState]);

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

            {/* 项目选择器 */}
            <Menu
              visible={showProjectMenu}
              onDismiss={() => setShowProjectMenu(false)}
              anchor={
                <TouchableOpacity
                  style={styles.projectSelector}
                  onPress={() => setShowProjectMenu(true)}
                >
                  <MaterialIcons name="folder" size={18} color={colors.primary} />
                  <Text
                    variant="titleMedium"
                    style={[styles.projectName, { color: colors.onSurface }]}
                    numberOfLines={1}
                  >
                    {currentProjectState?.name}
                  </Text>
                  <MaterialIcons name="arrow-drop-down" size={20} color={colors.onSurfaceVariant} />
                </TouchableOpacity>
              }
            >
              {projects.map((p) => (
                <Menu.Item
                  key={p.id}
                  onPress={() => handleSwitchProject(p)}
                  title={p.name}
                  leadingIcon={currentProjectState?.id === p.id ? 'check' : undefined}
                />
              ))}
            </Menu>

            {/* 设备选择器 - 点击进入设备列表页面 */}
            <TouchableOpacity
              style={[styles.projectSelector, { marginLeft: 8 }]}
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
                {selectedDevice?.name || '选择设备'}
              </Text>
              <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          </View>

          {/* 调试按钮（仅开发模式） */}
          {__DEV__ && (
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={() => router.push('Debug')}
            >
              <MaterialIcons name="bug-report" size={24} color={colors.warning} />
            </TouchableOpacity>
          )}

          {/* 右侧我的按钮 */}
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={handleGoToProfile}
          >
            <MaterialIcons name="person" size={24} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {/* ===== 游客提示（未登录时显示） ===== */}
        {!isLoggedIn && (
          <TouchableOpacity
            style={[styles.guestBanner, { backgroundColor: colors.primaryContainer }]}
            onPress={() => router.push('Auth')}
          >
            <MaterialIcons name="info" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 8 }}>
              游客模式 - 点击登录
            </Text>
          </TouchableOpacity>
        )}

        {/* ===== 实时识别文字（显示在顶部） ===== */}
        {nlsIsRecording && nlsCurrentText && (
          <View style={[styles.recognizingBanner, { backgroundColor: colors.surfaceVariant }]}>
            <MaterialIcons name="mic" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.onSurface, marginLeft: 8, flex: 1 }}>
              {nlsCurrentText}
            </Text>
            <View style={[styles.volumeIndicator, { width: nlsVolume * 50 }]} />
          </View>
        )}

        {/* ===== HITL 横幅 ===== */}
        <HITLBanner />

        {/* ===== 配额耗尽横幅 ===== */}
        {isQuotaExhausted && (
          <QuotaExhaustedBanner
            title={quotaExhaustedInfo?.title}
            message={quotaExhaustedInfo?.message}
          />
        )}

        {/* ===== 消息列表（核心区域） ===== */}
        <View style={styles.messagesArea}>
          <MessageList
            messages={messages}
            onRewind={handleRewind}
            onRetry={handleRetry}
            onQuote={handleQuote}
            onAddToMemory={handleAddToMemory}
          />
          {isQuotaExhausted && (
            <QuotaExhaustedCard
              info={quotaExhaustedInfo}
              onContinue={() => {
                clearQuotaExhausted();
                handleSendMessage(t('chat.quota.continuePrompt') || '继续');
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

        {/* ===== 底部输入区 ===== */}
        <VoiceInput
          state={combinedState}
          onSendText={handleSendMessage}
          onPressIn={handleVoicePressIn}
          onPressOut={handleVoicePressOut}
          onInterrupt={() => {
            stopTTS();
          }}
          disabled={false}
          inputMode={inputMode}
          onToggleMode={() => setInputMode(m => m === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE)}
          nlsVolume={nlsVolume}
          autoSpeak={autoSpeak}
          onToggleAutoSpeak={toggleAutoSpeak}
          isSpeaking={isTTSSpeaking}
          projectId={currentProjectState?.id}
          conversationId={currentConversationId || undefined}
          wakeWordEnabled={wakeWordEnabled}
          isWakeWordListening={isWakeWordListening}
          transcriptionText={nlsCurrentText}
        />
      </KeyboardAvoidingView>

      {/* ===== TTS 音频播放器（隐藏） ===== */}
      {ttsAudioUri && (
        <Video
          ref={ttsPlayerRef}
          source={{ uri: ttsAudioUri }}
          audioOnly
          paused={false}
          onEnd={() => setTtsAudioUri(null)}
          onError={() => setTtsAudioUri(null)}
          style={{ width: 0, height: 0 }}
        />
      )}

      {/* ===== Rewind/Retry 确认对话框 ===== */}
      <Portal>
        <Dialog visible={showRewindDialog} onDismiss={() => setShowRewindDialog(false)}>
          <Dialog.Title>确认操作</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              此操作将回退后续的文件修改。是否同时恢复文件到之前的状态？
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
              保留文件
            </Button>
            <Button onPress={() => {
              if (pendingRewindMessageId) {
                executeRewind(pendingRewindMessageId, true);
              } else if (pendingRetryMessageId) {
                executeRetry(pendingRetryMessageId, true);
              }
            }} mode="contained">
              恢复文件
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
      <Modal
        visible={showHistoryDrawer}
        transparent={true}
        animationType="none"
        onRequestClose={() => setShowHistoryDrawer(false)}
      >
        <View style={styles.modalContainer}>
          <Animated.View
            style={[
              styles.drawer,
              { backgroundColor: colors.background },
              { transform: [{ translateX: slideAnim }] },
            ]}
          >
            <ThreadList
              projectId={currentProjectState?.id}
              onSelectThread={handleSelectThread}
              onNewThread={handleNewThread}
            />
          </Animated.View>
          <TouchableOpacity
            style={styles.overlay}
            activeOpacity={1}
            onPress={() => setShowHistoryDrawer(false)}
          />
        </View>
      </Modal>
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
  // 抽屉模态框
  modalContainer: {
    flex: 1,
    flexDirection: 'row',
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  drawer: {
    width: 320,
    height: '100%',
  },
});
