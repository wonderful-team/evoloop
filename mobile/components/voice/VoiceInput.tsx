// 语音/文本输入组件 - 支持语音、文本和附件（按 PRD 设计重构）

import React, { useState, useCallback, useEffect } from 'react';
import { View, StyleSheet, TextInput, Keyboard } from 'react-native';
import { IconButton, AnimatedFAB } from 'react-native-paper';
import { useTheme } from '@/theme';
import { VoiceSessionState } from '@/services/voice/VoiceSessionManager';
import { AttachmentPicker, Attachment, ChatAttachment } from './AttachmentPicker';

// 输入模式枚举
export enum InputMode {
  VOICE = 'voice',  // 语音模式（默认）
  TEXT = 'text',    // 文本模式
}

interface VoiceInputProps {
  state: VoiceSessionState;
  onSendText: (text: string, uploadedAttachments?: ChatAttachment[]) => void;
  onToggleVoice: () => void;
  disabled?: boolean;
  placeholder?: string;
  // 外部控制模式（可选）
  inputMode?: InputMode;
  onToggleMode?: () => void;
}

export function VoiceInput({
  state,
  onSendText,
  onToggleVoice,
  disabled = false,
  placeholder = '输入消息...',
  inputMode: externalInputMode,
  onToggleMode,
}: VoiceInputProps) {
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [internalInputMode, setInternalInputMode] = useState<InputMode>(InputMode.VOICE);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploadedAttachments, setUploadedAttachments] = useState<ChatAttachment[]>([]);
  
  // 使用外部控制或内部状态
  const inputMode = externalInputMode ?? internalInputMode;
  const isTextMode = inputMode === InputMode.TEXT;

  const isListening = state === 'listening';
  const isProcessing = state === 'thinking' || state === 'recognizing';

  // 发送文本消息
  const handleSend = useCallback(() => {
    const hasContent = text.trim() || uploadedAttachments.length > 0;
    if (hasContent && !disabled) {
      // 只传递已上传完成的附件
      onSendText(text.trim(), uploadedAttachments.length > 0 ? uploadedAttachments : undefined);
      setText('');
      setAttachments([]);
      setUploadedAttachments([]);
      Keyboard.dismiss();
    }
  }, [text, uploadedAttachments, disabled, onSendText]);

  // 切换输入模式
  const toggleMode = useCallback(() => {
    if (onToggleMode) {
      // 使用外部控制
      onToggleMode();
    } else {
      // 使用内部状态
      setInternalInputMode(prev => prev === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
    }
    
    if (isTextMode) {
      // 切换到语音模式时收起键盘
      Keyboard.dismiss();
    }
  }, [isTextMode, onToggleMode]);

  // 切换语音状态
  const handleToggleVoice = useCallback(() => {
    onToggleVoice();
  }, [onToggleVoice]);

  // 处理附件变化
  const handleAttachmentsChange = useCallback((newAttachments: Attachment[]) => {
    setAttachments(newAttachments);
  }, []);

  // 处理上传完成
  const handleUploadComplete = useCallback((newUploadedAttachments: ChatAttachment[]) => {
    setUploadedAttachments(prev => [...prev, ...newUploadedAttachments]);
  }, []);

  // 是否有内容可发送
  const hasContent = text.trim() || uploadedAttachments.length > 0;

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* 附件预览和选择 */}
      <AttachmentPicker
        attachments={attachments}
        onAttachmentsChange={handleAttachmentsChange}
        onUploadComplete={handleUploadComplete}
        maxAttachments={5}
      />

      {/* 文本输入模式 */}
      {isTextMode ? (
        <View style={styles.inputContainer}>
          <IconButton
            icon="microphone"
            size={24}
            iconColor={colors.onSurfaceVariant}
            onPress={toggleMode}
            style={styles.modeButton}
          />
          <TextInput
            style={[
              styles.textInput,
              { color: colors.onSurface },
            ]}
            value={text}
            onChangeText={setText}
            placeholder={placeholder}
            placeholderTextColor={colors.outline}
            multiline
            maxLength={500}
            editable={!disabled}
          />
          <IconButton
            icon="send"
            size={24}
            iconColor={hasContent ? colors.onPrimary : colors.outline}
            onPress={handleSend}
            disabled={!hasContent || disabled}
            style={[
              styles.sendButton,
              { 
                backgroundColor: hasContent ? colors.primary : 'transparent',
              },
            ]}
          />
        </View>
      ) : (
        /* 语音输入模式 */
        <View style={styles.voiceContainer}>
          <IconButton
            icon="keyboard"
            size={24}
            iconColor={colors.onSurfaceVariant}
            onPress={toggleMode}
            style={styles.modeButton}
          />

          {/* 语音按钮 */}
          <AnimatedFAB
            icon={isListening ? 'stop' : 'microphone'}
            label={isListening ? '停止' : '按住说话'}
            extended
            onPress={handleToggleVoice}
            disabled={disabled || isProcessing}
            style={[
              styles.voiceButton,
              { backgroundColor: isListening ? colors.error : colors.primary },
            ]}
            color={colors.onPrimary}
          />

          {/* 状态指示 */}
          <View style={styles.statusContainer}>
            {isProcessing && (
              <View style={[styles.statusDot, { backgroundColor: colors.tertiary }]} />
            )}
            {isListening && (
              <View style={[styles.statusDot, { backgroundColor: colors.error }]} />
            )}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(0, 0, 0, 0.1)',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 48,
    paddingHorizontal: 12,
  },
  textInput: {
    flex: 1,
    fontSize: 16,
    maxHeight: 100,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  modeButton: {
    margin: 0,
  },
  sendButton: {
    margin: 0,
    borderRadius: 20,
  },
  voiceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 56,
    paddingHorizontal: 12,
  },
  voiceButton: {
    flex: 1,
    marginHorizontal: 16,
    height: 44,
  },
  statusContainer: {
    width: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
});
