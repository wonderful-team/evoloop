// 语音/文本输入组件

import React, { useState, useCallback } from 'react';
import { View, StyleSheet, TextInput, Keyboard, TouchableOpacity } from 'react-native';
import { IconButton, Text } from 'react-native-paper';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/theme';
import { VoiceSessionState } from '@/services/voice/VoiceSessionManager';
import { AttachmentPicker, Attachment, ChatAttachment } from './AttachmentPicker';

export enum InputMode {
  VOICE = 'voice',
  TEXT = 'text',
}

interface VoiceInputProps {
  state: VoiceSessionState;
  onSendText: (text: string, uploadedAttachments?: ChatAttachment[]) => void;
  onToggleVoice: () => void;
  disabled?: boolean;
  placeholder?: string;
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
  
  const inputMode = externalInputMode ?? internalInputMode;
  const isTextMode = inputMode === InputMode.TEXT;
  const isListening = state === 'listening';
  const isProcessing = state === 'thinking' || state === 'recognizing';

  const handleSend = useCallback(() => {
    const hasContent = text.trim() || uploadedAttachments.length > 0;
    if (hasContent && !disabled) {
      onSendText(text.trim(), uploadedAttachments.length > 0 ? uploadedAttachments : undefined);
      setText('');
      setAttachments([]);
      setUploadedAttachments([]);
      Keyboard.dismiss();
    }
  }, [text, uploadedAttachments, disabled, onSendText]);

  const toggleMode = useCallback(() => {
    if (onToggleMode) {
      onToggleMode();
    } else {
      setInternalInputMode(prev => prev === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
    }
    if (isTextMode) Keyboard.dismiss();
  }, [isTextMode, onToggleMode]);

  const hasContent = text.trim() || uploadedAttachments.length > 0;

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* 附件预览 */}
      <AttachmentPicker
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        onUploadComplete={(newAtts) => setUploadedAttachments(prev => [...prev, ...newAtts])}
        maxAttachments={5}
      />

      {isTextMode ? (
        // ===== 文本输入模式 =====
        <View style={styles.inputRow}>
          <TextInput
            style={[styles.textInput, { color: colors.onSurface }]}
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
            style={[styles.sendBtn, { backgroundColor: hasContent ? colors.primary : 'transparent' }]}
          />
        </View>
      ) : (
        // ===== 语音输入模式 =====
        <View style={styles.voiceWrap}>
          {/* 拍照 | 语音按钮 | 键盘 */}
          <View style={styles.voiceRow}>
            <TouchableOpacity style={styles.sideBtn}>
              <MaterialIcons name="photo-camera" size={24} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
            
            <TouchableOpacity
              onPress={onToggleVoice}
              disabled={disabled || isProcessing}
              activeOpacity={0.8}
              style={[styles.voiceBtn, { backgroundColor: isListening ? colors.error : colors.primary }]}
            >
              <MaterialIcons
                name={isListening ? 'stop' : 'mic'}
                size={32}
                color={colors.onPrimary}
              />
            </TouchableOpacity>
            
            <TouchableOpacity style={styles.sideBtn} onPress={toggleMode}>
              <MaterialIcons name="keyboard" size={24} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          </View>
          
          <Text variant="bodySmall" style={[styles.hint, { color: colors.outline }]}>
            {isListening ? '点击停止' : '按住说话'}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(0, 0, 0, 0.1)',
  },
  // 文本输入
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    minHeight: 48,
  },
  textInput: {
    flex: 1,
    fontSize: 16,
    maxHeight: 100,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  sendBtn: {
    margin: 0,
    borderRadius: 20,
  },
  // 语音输入
  voiceWrap: {
    alignItems: 'center',
    paddingVertical: 16,
    paddingBottom: 24,
  },
  voiceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
  },
  sideBtn: {
    padding: 12,
  },
  voiceBtn: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 6,
  },
  hint: {
    marginTop: 12,
  },
});
