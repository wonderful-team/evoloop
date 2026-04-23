// 语音对话页面 - 语音助手主界面

import React, { useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useRouter } from '@/utils/navigation';
import { useTranslation } from 'react-i18next';
import {
  VoiceStatusIndicator,
  MessageList,
  CommandConfirmCard,
  VoiceControlButton,
  VoiceInput,
  VolumeBar,
} from '@/components/voice';
import { useVoice } from '@/hooks/useVoice';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import { TaskCommand } from '@/types/voice';

export default function VoiceScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();

  // 使用语音 Hook
  const {
    state,
    isListening,
    isSpeaking,
    isThinking,
    volume,
    messages,
    currentCommand,
    start,
    stop,
    interrupt,
    sendMessage,
    confirmCommand,
  } = useVoice({
    onCommandReady: (command) => {
      console.log('指令待确认:', command);
    },
    onError: (error) => {
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

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* 头部 */}
        <Header
          title={t('voice.title')}
          showBack
          onBack={() => router.back()}
          rightAction={{
            icon: 'cog',
            onPress: () => router.push('SettingsVoice'),
          }}
        />

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

        {/* 底部控制区域 */}
        <View style={styles.controlContainer}>
          {/* 大圆形语音按钮（当没有文本输入时显示） */}
          {messages.length === 0 && !currentCommand && (
            <View style={styles.voiceButtonContainer}>
              <VoiceControlButton
                state={state}
                volume={volume}
                onPress={handleVoiceToggle}
              />
            </View>
          )}

          {/* 语音/文本输入 */}
          <VoiceInput
            state={state}
            onSendText={sendMessage}
            onToggleVoice={handleVoiceToggle}
            disabled={isThinking}
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
    paddingVertical: 24,
  },
});
