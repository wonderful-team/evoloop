// 首页 - 语音对话主界面（按 PRD 设计重构）

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import { Text } from 'react-native-paper';
import {
  VoiceStatusIndicator,
  MessageList,
  CommandConfirmCard,
  VoiceControlButton,
  VoiceInput,
  VolumeBar,
  InputMode,
} from '@/components/voice';
import { 
  HumanRequestCard, 
  HITLBanner 
} from '@/components/hitl';
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
import { Artifact, TestReportArtifact } from '@/types/artifact';
import { AgentStep, AgentThought } from '@/types/agent';
import type { ChatAttachment } from '@/services/api/upload';
import * as conversationApi from '@/services/api/conversations';

export default function HomeScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  
  // 输入模式状态（默认语音模式）
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);

  // 使用语音 Hook
  const {
    state,
    isListening,
    isSpeaking,
    isThinking,
    volume,
    messages,
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
    },
  });

  // 页面加载时自动启动会话
  useEffect(() => {
    start();
    return () => {
      stop();
    };
  }, []);

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

  // 处理发送消息（支持附件）
  const handleSendMessage = useCallback((text: string, uploadedAttachments?: ChatAttachment[]) => {
    // 发送消息，包含已上传的附件
    if (uploadedAttachments && uploadedAttachments.length > 0) {
      console.log('发送消息:', text, '附件:', uploadedAttachments);
      // TODO: 在消息中显示附件
      // 这里可以将附件信息一起发送到 Gateway
    }
    sendTextMessage(text);
  }, [sendTextMessage]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* HITL 状态横幅 */}
        <HITLBanner />

        {/* 头部 - 按 PRD 设计 */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <MaterialIcons name="chat-bubble" size={24} color={colors.primary} />
            <Text variant="titleMedium" style={[styles.headerTitle, { color: colors.onBackground }]}>
              EvoLoop
            </Text>
          </View>
          
          {/* 设备状态指示器 */}
          <View style={[styles.deviceStatus, { backgroundColor: colors.primaryContainer }]}>
            <MaterialIcons name="flash-on" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.primary }}>
              在线
            </Text>
          </View>
        </View>

        {/* 语音状态指示器 */}
        <View style={styles.statusContainer}>
          <VoiceStatusIndicator state={state} volume={volume} />

          {/* 音量条（仅在监听状态时显示） */}
          {isListening && (
            <View style={styles.volumeContainer}>
              <VolumeBar volume={volume} />
            </View>
          )}
        </View>

        {/* 消息列表 */}
        <View style={styles.messagesContainer}>
          <MessageList messages={messages} />
        </View>

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
          {/* 大圆形语音按钮（语音模式下显示） */}
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

          {/* 语音/文本输入 */}
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
    paddingHorizontal: 16,
    paddingVertical: 12,
    height: 56,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontWeight: '600',
  },
  deviceStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusContainer: {
    paddingVertical: 8,
  },
  volumeContainer: {
    paddingHorizontal: 32,
    marginTop: -8,
  },
  messagesContainer: {
    flex: 1,
  },
  controlContainer: {
    paddingBottom: Platform.OS === 'ios' ? 16 : 8,
  },
  voiceButtonContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
  },
  voiceHint: {
    marginTop: 8,
  },
});
