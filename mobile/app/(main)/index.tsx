// 首页 - 语音对话主界面（集成所有新功能）

import React, { useCallback, useEffect, useState, useRef } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  FlatList,
  RefreshControl,
  Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import { Text, IconButton, FAB, Portal, Snackbar } from 'react-native-paper';
import {
  VoiceStatusIndicator,
  MessageList,
  CommandConfirmCard,
  VoiceControlButton,
  VoiceInput,
  VolumeBar,
  InputMode,
} from '@/components/voice';
import { HumanRequestCard, HITLBanner } from '@/components/hitl';
import {
  ThreadList,
  RewindConfirmDialog,
  ArtifactCard,
  StepsIndicator,
  ThoughtCard,
} from '@/components/chat';
import { useVoice } from '@/hooks/useVoice';
import { useConversationStore } from '@/stores/conversationStore';
import { useTheme } from '@/theme';
import { TaskCommand } from '@/types/voice';
import { HumanRequest } from '@/types/hitl';
import { Artifact, AgentStep, AgentThought } from '@/types';
import type { ChatAttachment } from '@/services/api/upload';
import * as conversationApi from '@/services/api/conversations';
import * as artifactApi from '@/services/api/artifacts';

// 模拟数据 - 实际项目中应该从 API 获取
const MOCK_ARTIFACTS: Artifact[] = [
  {
    id: '1',
    type: 'test_report',
    name: '单元测试报告',
    status: 'completed',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    conversation_id: 'conv_1',
    data: {
      total_tests: 50,
      passed: 45,
      failed: 3,
      skipped: 2,
      duration: 12.5,
      suites: [],
      summary: '大部分测试通过，有 3 个失败需要修复',
    },
  } as Artifact,
];

const MOCK_STEPS: AgentStep[] = [
  { id: 1, name: '分析需求', status: 'done', type: 'ai' },
  { id: 2, name: '搜索相关文件', status: 'done', type: 'tool', input: { query: 'auth' } },
  { id: 3, name: '生成代码', status: 'running', type: 'ai' },
];

const MOCK_THOUGHTS: AgentThought[] = [
  {
    id: '1',
    type: 'thought',
    thought_type: 'intent',
    title: '理解用户意图',
    content: '用户想要创建一个用户认证系统',
    confidence: 0.95,
    timestamp: Date.now(),
  },
];

export default function HomeScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  
  // 输入模式状态
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);
  
  // UI 状态
  const [showThreadList, setShowThreadList] = useState(false);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [showRewindDialog, setShowRewindDialog] = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [rewindMode, setRewindMode] = useState<'rewind' | 'retry'>('rewind');
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');

  // 数据状态
  const [artifacts, setArtifacts] = useState<Artifact[]>(MOCK_ARTIFACTS);
  const [steps, setSteps] = useState<AgentStep[]>(MOCK_STEPS);
  const [thoughts, setThoughts] = useState<AgentThought[]>(MOCK_THOUGHTS);

  // Store
  const {
    conversations,
    currentConversationId,
    messages,
    isLoadingConversations,
    isLoadingMessages,
    hasMoreConversations,
    hasMoreMessages,
    loadConversations,
    loadMoreConversations,
    createConversation,
    deleteConversation,
    setCurrentConversation,
    addMessage,
    updateLastMessage,
  } = useConversationStore();

  // 使用语音 Hook
  const {
    state,
    isListening,
    isSpeaking,
    isThinking,
    volume,
    currentCommand,
    hitlRequest,
    isWaitingForHuman,
    start,
    stop,
    interrupt,
    sendText: sendTextMessage,
    confirmCommand,
    respondToHITL,
    cancelHITL,
  } = useVoice({
    onCommandReady: (command: TaskCommand) => {
      console.log('指令待确认:', command);
    },
    onHITLRequest: (request: HumanRequest) => {
      console.log('HITL 请求:', request);
    },
    onError: (error: Error) => {
      console.error('语音错误:', error);
      showSnackbar('语音错误: ' + error.message);
    },
  });

  // 加载会话列表
  useEffect(() => {
    loadConversations(undefined, true);
  }, []);

  // 页面加载时自动启动会话
  useEffect(() => {
    start();
    return () => {
      stop();
    };
  }, []);

  // 显示 Snackbar
  const showSnackbar = (message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  };

  // 处理语音按钮点击
  const handleVoiceToggle = useCallback(async () => {
    if (isListening) {
      await stop();
    } else if (isSpeaking) {
      await interrupt();
    } else {
      await start();
    }
  }, [isListening, isSpeaking, start, stop, interrupt]);

  // 处理指令确认
  const handleConfirmCommand = useCallback(
    (confirmed: boolean) => {
      confirmCommand(confirmed);
    },
    [confirmCommand]
  );

  // 处理取消指令
  const handleCancelCommand = useCallback(() => {
    confirmCommand(false);
  }, [confirmCommand]);

  // 处理 HITL 响应
  const handleHITLResponse = useCallback(
    (value: string) => {
      respondToHITL(value);
      showSnackbar('回复已发送');
    },
    [respondToHITL]
  );

  // 处理 HITL 取消
  const handleHITLCancel = useCallback(() => {
    cancelHITL('用户取消');
  }, [cancelHITL]);

  // 切换输入模式
  const toggleInputMode = useCallback(() => {
    setInputMode(prev => prev === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
  }, []);

  // 处理发送消息
  const handleSendMessage = useCallback((text: string, uploadedAttachments?: ChatAttachment[]) => {
    if (uploadedAttachments && uploadedAttachments.length > 0) {
      console.log('发送消息:', text, '附件:', uploadedAttachments);
    }
    sendTextMessage(text);
  }, [sendTextMessage]);

  // 新建会话
  const handleNewConversation = useCallback(async () => {
    try {
      const id = await createConversation();
      setShowThreadList(false);
      showSnackbar('新会话已创建');
    } catch (error) {
      console.error('创建会话失败:', error);
      showSnackbar('创建会话失败');
    }
  }, [createConversation]);

  // 选择会话
  const handleSelectConversation = useCallback((id: string) => {
    setCurrentConversation(id);
    setShowThreadList(false);
  }, [setCurrentConversation]);

  // Rewind 消息
  const handleRewind = useCallback((messageId: string) => {
    setSelectedMessageId(messageId);
    setRewindMode('rewind');
    setShowRewindDialog(true);
  }, []);

  // Retry 消息
  const handleRetry = useCallback((messageId: string) => {
    setSelectedMessageId(messageId);
    setRewindMode('retry');
    setShowRewindDialog(true);
  }, []);

  // 确认 Rewind/Retry
  const handleConfirmRewind = useCallback(async (revertFiles: boolean) => {
    if (!currentConversationId || !selectedMessageId) return;

    try {
      if (rewindMode === 'rewind') {
        await conversationApi.rewindConversation(currentConversationId, {
          message_id: selectedMessageId,
          revert_files: revertFiles,
        });
        showSnackbar('已撤回消息');
      } else {
        await conversationApi.retryConversation(currentConversationId, {
          message_id: selectedMessageId,
          revert_files: revertFiles,
        });
        showSnackbar('正在重试...');
      }
    } catch (error) {
      console.error(`${rewindMode} 失败:`, error);
      showSnackbar(`${rewindMode === 'rewind' ? '撤回' : '重试'}失败`);
    }
    
    setShowRewindDialog(false);
    setSelectedMessageId(null);
  }, [rewindMode, currentConversationId, selectedMessageId]);

  // 查看 Artifact
  const handleViewArtifact = useCallback((artifact: Artifact) => {
    console.log('查看 Artifact:', artifact);
    showSnackbar(`查看: ${artifact.name}`);
  }, []);

  // 下载 Artifact
  const handleDownloadArtifact = useCallback(async (artifact: Artifact) => {
    try {
      const response = await artifactApi.getArtifactDownloadUrl(artifact.id);
      console.log('下载链接:', response.download_url);
      showSnackbar('开始下载...');
    } catch (error) {
      console.error('下载失败:', error);
      showSnackbar('下载失败');
    }
  }, []);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* HITL 状态横幅 */}
        <HITLBanner />

        {/* 头部 */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <TouchableOpacity 
              style={styles.headerButton}
              onPress={() => setShowThreadList(true)}
            >
              <MaterialIcons name="history" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text variant="titleMedium" style={[styles.headerTitle, { color: colors.onBackground }]}>
              {currentConversationId 
                ? conversations.find(c => c.id === currentConversationId)?.title || '新对话'
                : 'EvoLoop'
              }
            </Text>
          </View>
          
          <View style={styles.headerRight}>
            {/* 步骤指示器按钮 */}
            {steps.length > 0 && (
              <TouchableOpacity
                style={[styles.headerButton, { marginRight: 8 }]}
                onPress={() => setShowSteps(!showSteps)}
              >
                <MaterialIcons name="account-tree" size={22} color={colors.primary} />
                {steps.some(s => s.status === 'running') && (
                  <View style={[styles.badge, { backgroundColor: colors.primary }]} />
                )}
              </TouchableOpacity>
            )}
            
            {/* Artifacts 按钮 */}
            {artifacts.length > 0 && (
              <TouchableOpacity
                style={[styles.headerButton, { marginRight: 8 }]}
                onPress={() => setShowArtifacts(!showArtifacts)}
              >
                <MaterialIcons name="folder-open" size={22} color={colors.primary} />
                <View style={[styles.badge, { backgroundColor: colors.error }]}>
                  <Text style={styles.badgeText}>{artifacts.length}</Text>
                </View>
              </TouchableOpacity>
            )}

            {/* 设备状态 */}
            <View style={[styles.deviceStatus, { backgroundColor: colors.primaryContainer }]}>
              <MaterialIcons name="flash-on" size={14} color={colors.primary} />
              <Text variant="bodySmall" style={{ color: colors.primary, fontSize: 12 }}>
                在线
              </Text>
            </View>
          </View>
        </View>

        {/* 语音状态指示器 */}
        <View style={styles.statusContainer}>
          <VoiceStatusIndicator state={state} volume={volume} />

          {isListening && (
            <View style={styles.volumeContainer}>
              <VolumeBar volume={volume} />
            </View>
          )}
        </View>

        {/* 步骤指示器（紧凑模式） */}
        {showSteps && steps.length > 0 && (
          <StepsIndicator steps={steps} compact />
        )}

        {/* 主内容区域 */}
        <View style={styles.mainContent}>
          {/* 消息列表 */}
          <View style={styles.messagesContainer}>
            <MessageList 
              messages={messages}
              onRewind={handleRewind}
              onRetry={handleRetry}
            />
          </View>

          {/* Artifacts 侧边栏 */}
          {showArtifacts && artifacts.length > 0 && (
            <View style={[styles.artifactsPanel, { backgroundColor: colors.surface }]}>
              <View style={[styles.artifactsHeader, { borderBottomColor: colors.outline + '30' }]}>
                <Text variant="titleSmall" style={{ color: colors.onSurface }}>
                  生成的文件
                </Text>
                <IconButton
                  icon="close"
                  size={20}
                  iconColor={colors.outline}
                  onPress={() => setShowArtifacts(false)}
                />
              </View>
              <FlatList
                data={artifacts}
                keyExtractor={(item) => item.id}
                renderItem={({ item }) => (
                  <ArtifactCard
                    artifact={item}
                    onView={handleViewArtifact}
                    onDownload={handleDownloadArtifact}
                  />
                )}
                showsVerticalScrollIndicator={false}
              />
            </View>
          )}
        </View>

        {/* 思考过程展示 */}
        {thoughts.length > 0 && (
          <View style={styles.thoughtsContainer}>
            <ThoughtCard thought={thoughts[thoughts.length - 1]} />
          </View>
        )}

        {/* 指令确认卡片 */}
        {currentCommand && (
          <CommandConfirmCard
            command={currentCommand}
            onConfirm={() => handleConfirmCommand(true)}
            onCancel={handleCancelCommand}
          />
        )}

        {/* HITL 人类请求卡片 */}
        {hitlRequest && (
          <HumanRequestCard
            request={hitlRequest}
            onRespond={handleHITLResponse}
            onCancel={handleHITLCancel}
          />
        )}

        {/* 底部控制区域 */}
        <View style={styles.controlContainer}>
          {inputMode === InputMode.VOICE && messages.length === 0 && !currentCommand && (
            <View style={styles.voiceButtonContainer}>
              <VoiceControlButton
                state={state}
                volume={volume}
                onPress={handleVoiceToggle}
              />
              <Text variant="bodySmall" style={[styles.voiceHint, { color: colors.outline }]}>
                {isListening ? '松开发送' : '按住说话'}
              </Text>
            </View>
          )}

          <VoiceInput
            state={state}
            onSendText={handleSendMessage}
            onToggleVoice={handleVoiceToggle}
            disabled={isThinking}
            inputMode={inputMode}
            onToggleMode={toggleInputMode}
          />
        </View>
      </KeyboardAvoidingView>

      {/* 会话列表模态框 */}
      <Modal
        visible={showThreadList}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowThreadList(false)}
      >
        <ThreadList
          projectId={undefined}
          onSelectThread={handleSelectConversation}
          onNewThread={handleNewConversation}
        />
      </Modal>

      {/* Rewind/Retry 确认对话框 */}
      <RewindConfirmDialog
        visible={showRewindDialog}
        onDismiss={() => setShowRewindDialog(false)}
        onConfirm={handleConfirmRewind}
        mode={rewindMode}
        hasFileOperations={true}
      />

      {/* Snackbar */}
      <Snackbar
        visible={snackbarVisible}
        onDismiss={() => setSnackbarVisible(false)}
        duration={3000}
        action={{
          label: '关闭',
          onPress: () => setSnackbarVisible(false),
        }}
      >
        {snackbarMessage}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
    height: 56,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  headerButton: {
    padding: 8,
    position: 'relative',
  },
  headerTitle: {
    fontWeight: '600',
    fontSize: 18,
  },
  deviceStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badge: {
    position: 'absolute',
    top: 4,
    right: 4,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },
  statusContainer: {
    paddingVertical: 6,
  },
  volumeContainer: {
    paddingHorizontal: 32,
    marginTop: -6,
  },
  mainContent: {
    flex: 1,
    flexDirection: 'row',
  },
  messagesContainer: {
    flex: 1,
  },
  artifactsPanel: {
    width: 300,
    borderLeftWidth: 1,
    borderLeftColor: '#e5e7eb',
  },
  artifactsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    borderBottomWidth: 1,
  },
  thoughtsContainer: {
    maxHeight: 200,
  },
  controlContainer: {
    paddingBottom: Platform.OS === 'ios' ? 16 : 8,
  },
  voiceButtonContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
  },
  voiceHint: {
    marginTop: 8,
  },
});
