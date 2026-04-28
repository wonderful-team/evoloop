// 语音/文本输入组件 - 支持引用、TTS、语音打断

import React, { useState, useCallback, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { View, StyleSheet, TextInput, Keyboard, TouchableOpacity, ScrollView } from 'react-native';
import { IconButton, Text, Divider } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { ImageOrVideo } from 'react-native-image-crop-picker';
import { Alert } from 'react-native';
import { VoiceSessionState } from '@/types/voice';
import { AttachmentPicker, Attachment, ChatAttachment } from './AttachmentPicker';
import { uploadChatFile } from '@/services/api/upload';
import { VoiceInputReferencesBar } from './VoiceInputReferencesBar';
import { MessageReference } from '@/types/conversation';
import { ReferencePicker } from '@/components/chat/ReferencePicker';
import { VoiceInputVoicePanel } from './VoiceInputVoicePanel';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MediaPickerModal } from '@/components/common/MediaPickerModal';

export enum InputMode {
  VOICE = 'voice',
  TEXT = 'text',
}

export interface VoiceInputHandle {
  addReference: (reference: MessageReference) => void;
}

interface VoiceInputProps {
  state: VoiceSessionState;
  onSendText: (text: string, options?: {
    attachments?: ChatAttachment[];
    references?: MessageReference[];
  }) => void;
  onToggleVoice?: () => void;
  onInterrupt?: () => void; // 语音打断
  // 按住说话模式
  onPressIn?: () => void;   // 按住开始录音
  onPressOut?: () => void;  // 松开停止录音
  disabled?: boolean;
  placeholder?: string;
  inputMode?: InputMode;
  onToggleMode?: () => void;
  nlsVolume?: number;
  // TTS 相关
  autoSpeak?: boolean;
  onToggleAutoSpeak?: () => void;
  isSpeaking?: boolean;
  // 引用相关
  projectId?: number;
  conversationId?: string;
  // 唤醒词状态
  wakeWordEnabled?: boolean;
  isWakeWordListening?: boolean;
  isWakeWordDetected?: boolean;
  // 实时转录文字
  transcriptionText?: string;
}

export const VoiceInput = forwardRef<VoiceInputHandle, VoiceInputProps>(({
  state,
  onSendText,
  onToggleVoice,
  onInterrupt,
  onPressIn,
  onPressOut,
  disabled = false,
  placeholder = '输入消息...',
  inputMode: externalInputMode,
  onToggleMode,
  nlsVolume,
  autoSpeak = false,
  onToggleAutoSpeak,
  isSpeaking = false,
  projectId,
  conversationId,
  wakeWordEnabled = false,
  isWakeWordListening = false,
  isWakeWordDetected = false,
  // 实时转录文字
  transcriptionText = '',
}, ref) => {
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [internalInputMode, setInternalInputMode] = useState<InputMode>(InputMode.VOICE);
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  // 草稿保存 key
  const draftKey = `chat_draft_${conversationId || 'global'}`;

  // 挂载时恢复草稿
  useEffect(() => {
    AsyncStorage.getItem(draftKey).then((draft) => {
      if (draft) {setText(draft);}
    }).catch(() => {});
  }, [draftKey]);

  // 文本变化时 debounce 保存草稿
  const draftTimerRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    if (draftTimerRef.current) {clearTimeout(draftTimerRef.current);}
    draftTimerRef.current = setTimeout(() => {
      if (text.trim()) {
        AsyncStorage.setItem(draftKey, text).catch(() => {});
      } else {
        AsyncStorage.removeItem(draftKey).catch(() => {});
      }
    }, 500);
    return () => {
      if (draftTimerRef.current) {clearTimeout(draftTimerRef.current);}
    };
  }, [text, draftKey]);
  const [uploadedAttachments, setUploadedAttachments] = useState<ChatAttachment[]>([]);
  const [references, setReferences] = useState<MessageReference[]>([]);
  const [showReferencePicker, setShowReferencePicker] = useState(false);
  const [showReferenceHint, setShowReferenceHint] = useState(false);
  const [showMediaPicker, setShowMediaPicker] = useState(false);

  const inputMode = externalInputMode ?? internalInputMode;
  const isTextMode = inputMode === InputMode.TEXT;
  const isListening = state === 'listening' || state === 'recognizing';
  const isProcessing = state === 'thinking';
  const isAgentSpeaking = state === 'speaking' || isSpeaking;

  const inputRef = useRef<TextInput>(null);

  // 处理 @ 符号输入
  const handleTextChange = useCallback((newText: string) => {
    setText(newText);

    // 检测 @ 符号
    const lastChar = newText.slice(-1);
    const hasAtSymbol = newText.includes('@') && !newText.endsWith('@');

    if (lastChar === '@') {
      setShowReferenceHint(true);
    } else if (showReferenceHint && !hasAtSymbol) {
      setShowReferenceHint(false);
    }
  }, [showReferenceHint]);

  const handleSend = useCallback(() => {
    const hasContent = text.trim() || uploadedAttachments.length > 0 || references.length > 0;
    if (hasContent && !disabled) {
      onSendText(text.trim(), {
        attachments: uploadedAttachments.length > 0 ? uploadedAttachments : undefined,
        references: references.length > 0 ? references : undefined,
      });
      setText('');
      setAttachments([]);
      setUploadedAttachments([]);
      setReferences([]);
      Keyboard.dismiss();
    }
  }, [text, uploadedAttachments, references, disabled, onSendText]);

  const toggleMode = useCallback(() => {
    if (onToggleMode) {
      onToggleMode();
    } else {
      setInternalInputMode(prev => prev === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
    }
    if (isTextMode) {Keyboard.dismiss();}
  }, [isTextMode, onToggleMode]);

  // 暴露 addReference 方法给父组件（如 ChatScreen 的长按引用）
  useImperativeHandle(ref, () => ({
    addReference: (reference: MessageReference) => {
      // 避免重复引用
      if (!references.some(r => r.id === reference.id)) {
        setReferences(prev => [...prev, reference]);
      }
      // 在文本中插入引用标记
      const refText = `@${reference.name} `;
      setText(prev => prev + refText);
    },
  }), [references]);

  // 添加引用（内部使用，与 useImperativeHandle 保持逻辑一致）
  const handleAddReference = useCallback((reference: MessageReference) => {
    // 避免重复引用
    if (!references.some(r => r.id === reference.id)) {
      setReferences(prev => [...prev, reference]);
    }
    // 在文本中插入引用标记
    const refText = `@${reference.name} `;
    setText(prev => prev + refText);
  }, [references]);

  // 移除引用
  const handleRemoveReference = useCallback((index: number) => {
    const ref = references[index];
    setReferences(prev => prev.filter((_, i) => i !== index));
    // 从文本中移除引用标记
    if (ref) {
      setText(prev => prev.replace(`@${ref.name} `, '').replace(`@${ref.name}`, ''));
    }
  }, [references]);

  // 处理语音按钮按下：先打断（如有），再开始录音
  const handleVoicePressIn = useCallback(() => {
    if (isAgentSpeaking && onInterrupt) {
      onInterrupt();
    }
    if (!isListening && onPressIn) {
      onPressIn();
    }
  }, [isAgentSpeaking, isListening, onInterrupt, onPressIn]);

  // 处理语音按钮松开（松开发送）
  const handleVoicePressOut = useCallback(() => {
    if (isListening && onPressOut) {
      // 录音状态下松开停止录音
      onPressOut();
    }
  }, [isListening, onPressOut]);

  // 底部媒体面板
  const openMediaPicker = useCallback(() => {
    if (attachments.length >= 5) {
      Alert.alert('提示', '最多只能添加 5 个附件');
      return;
    }
    setShowMediaPicker(true);
  }, [attachments.length]);

  const closeMediaPicker = useCallback(() => {
    setShowMediaPicker(false);
  }, []);

  const handleSelectImage = useCallback((images: ImageOrVideo[]) => {
    const newAtts: Attachment[] = images.map((asset, index) => ({
      id: `media_${Date.now()}_${index}`,
      type: asset.mime?.startsWith('video/') ? 'video' : 'image',
      uri: asset.path,
      name: asset.filename || `media_${Date.now()}_${index}.${asset.mime?.startsWith('video/') ? 'mp4' : 'jpg'}`,
      mimeType: asset.mime || 'image/jpeg',
      size: asset.size,
      uploading: false,
      uploaded: false,
    }));
    setAttachments(prev => [...prev, ...newAtts]);
  }, []);

  const handleSelectFile = useCallback(async (files: any[]) => {
    const newAtts: ChatAttachment[] = [];
    for (const file of files.slice(0, 5 - attachments.length)) {
      try {
        const uploaded = await uploadChatFile(file.uri, file.name);
        newAtts.push(uploaded);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : '文件上传失败';
        Alert.alert('上传失败', msg);
      }
    }
    if (newAtts.length > 0) {
      setUploadedAttachments(prev => [...prev, ...newAtts]);
    }
  }, [attachments.length]);

  const hasContent = text.trim() || uploadedAttachments.length > 0 || references.length > 0;

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* 附件预览 */}
      <AttachmentPicker
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        onUploadComplete={(newAtts) => setUploadedAttachments(prev => [...prev, ...newAtts])}
        maxAttachments={5}
      />

      {/* 引用预览 */}
      <VoiceInputReferencesBar references={references} onRemove={handleRemoveReference} />

      {isTextMode ? (
        // ===== 文本输入模式 =====
        <View style={styles.inputRow}>
          <TouchableOpacity style={styles.modeSwitchBtn} onPress={toggleMode}>
            <MaterialIcons name="mic" size={24} color={colors.primary} />
          </TouchableOpacity>

          <View style={styles.inputContainer}>
            <TextInput
              ref={inputRef}
              style={[styles.textInput, { color: colors.onSurface }]}
              value={text}
              onChangeText={handleTextChange}
              placeholder={placeholder}
              placeholderTextColor={colors.onSurfaceVariant}
              multiline
              maxLength={500}
              editable={!disabled}
            />

            {/* @ 提示 */}
            {showReferenceHint && (
              <TouchableOpacity
                style={[styles.atHint, { backgroundColor: colors.primaryContainer }]}
                onPress={() => {
                  setShowReferenceHint(false);
                  setShowReferencePicker(true);
                }}
              >
                <MaterialIcons name="alternate-email" size={16} color={colors.primary} />
                <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 4 }}>
                  引用消息/文件
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* 附件按钮 */}
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={openMediaPicker}
          >
            <MaterialIcons name="attach-file" size={22} color={colors.onSurfaceVariant} />
          </TouchableOpacity>

          {/* 引用按钮 */}
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => setShowReferencePicker(true)}
          >
            <MaterialIcons name="alternate-email" size={22} color={colors.primary} />
          </TouchableOpacity>

          {/* TTS 自动朗读开关 */}
          {onToggleAutoSpeak && (
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={onToggleAutoSpeak}
            >
              <MaterialIcons
                name={autoSpeak ? 'volume-up' : 'volume-off'}
                size={22}
                color={autoSpeak ? colors.primary : colors.onSurfaceVariant}
              />
            </TouchableOpacity>
          )}

          <IconButton
            icon="send"
            size={24}
            iconColor={hasContent ? colors.onPrimary : colors.onSurfaceVariant}
            onPress={handleSend}
            disabled={!hasContent || disabled}
            style={[styles.sendBtn, { backgroundColor: hasContent ? colors.primary : 'transparent' }]}
          />
        </View>
      ) : (
        // ===== 语音输入模式 =====
        <View style={styles.voiceWrap}>
          {/* 工具栏 */}
          <View style={styles.toolbar}>
            {/* 引用按钮 */}
            <TouchableOpacity
              style={styles.toolbarBtn}
              onPress={() => setShowReferencePicker(true)}
            >
              <MaterialIcons name="alternate-email" size={20} color={colors.primary} />
              <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 4 }}>
                引用
              </Text>
            </TouchableOpacity>

            {/* TTS 开关 */}
            {onToggleAutoSpeak && (
              <TouchableOpacity
                style={styles.toolbarBtn}
                onPress={onToggleAutoSpeak}
              >
                <MaterialIcons
                  name={autoSpeak ? 'volume-up' : 'volume-off'}
                  size={20}
                  color={autoSpeak ? colors.primary : colors.onSurfaceVariant}
                />
                <Text
                  variant="bodySmall"
                  style={{ color: autoSpeak ? colors.primary : colors.onSurfaceVariant, marginLeft: 4 }}
                >
                  {autoSpeak ? '朗读中' : '朗读关'}
                </Text>
              </TouchableOpacity>
            )}

            {/* 唤醒词状态 */}
            {wakeWordEnabled && (
              <View style={[styles.toolbarBtn, { opacity: 0.6 }]}>
                <MaterialIcons
                  name={isWakeWordDetected ? 'notifications-active' : isWakeWordListening ? 'hearing' : 'hearing-disabled'}
                  size={20}
                  color={isWakeWordDetected ? colors.primary : isWakeWordListening ? colors.success : colors.onSurfaceVariant}
                />
                <Text
                  variant="bodySmall"
                  style={{
                    color: isWakeWordDetected ? colors.primary : isWakeWordListening ? colors.success : colors.onSurfaceVariant,
                    marginLeft: 4,
                  }}
                >
                  {isWakeWordDetected ? '已唤醒' : isWakeWordListening ? '监听中' : '待机'}
                </Text>
              </View>
            )}
          </View>

          <Divider style={{ width: '100%', marginVertical: 8 }} />

          <VoiceInputVoicePanel
            isListening={isListening}
            nlsVolume={nlsVolume}
            transcriptionText={transcriptionText}
          />

          {/* 拍照 | 语音按钮 | 键盘 */}
          <View style={styles.voiceRow}>
            <TouchableOpacity style={styles.sideBtn} onPress={openMediaPicker}>
              <MaterialIcons name="photo-camera" size={28} color={colors.onSurfaceVariant} />
            </TouchableOpacity>

            <TouchableOpacity
              onPressIn={handleVoicePressIn}
              onPressOut={handleVoicePressOut}
              disabled={!isListening && isProcessing}
              activeOpacity={0.8}
              style={[
                styles.voiceBtn,
                {
                  backgroundColor: isListening ? colors.success : colors.primary,
                },
              ]}
            >
              <MaterialIcons
                name="mic"
                size={36}
                color={colors.onPrimary}
              />
            </TouchableOpacity>

            <TouchableOpacity style={styles.sideBtn} onPress={toggleMode}>
              <MaterialIcons name="keyboard" size={28} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          </View>

          <Text variant="bodySmall" style={[styles.hint, { color: colors.onSurfaceVariant }]}>
            {isListening ? '松开发送' : '按住说话'}
          </Text>
        </View>
      )}

      {/* 引用选择器 */}
      <ReferencePicker
        visible={showReferencePicker}
        onDismiss={() => setShowReferencePicker(false)}
        onSelect={handleAddReference}
        projectId={projectId}
        conversationId={conversationId}
      />

      {/* 底部媒体选择面板 */}
      <MediaPickerModal
        visible={showMediaPicker}
        onClose={closeMediaPicker}
        options={['camera', 'video', 'album', 'file']}
        maxFiles={5 - attachments.length}
        onSelectImage={handleSelectImage}
        onSelectFile={handleSelectFile}
      />
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(0, 0, 0, 0.1)',
  },
  // 文本输入
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 8,
    minHeight: 56,
  },
  inputContainer: {
    flex: 1,
    position: 'relative',
  },
  modeSwitchBtn: {
    padding: 8,
    marginRight: 4,
  },
  iconBtn: {
    padding: 6,
    marginHorizontal: 2,
  },
  textInput: {
    flex: 1,
    fontSize: 16,
    maxHeight: 100,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  atHint: {
    position: 'absolute',
    right: 8,
    top: '50%',
    marginTop: -12,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  sendBtn: {
    margin: 0,
    borderRadius: 20,
  },
  // 语音输入
  voiceWrap: {
    alignItems: 'center',
    paddingVertical: 12,
    paddingBottom: 24,
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    marginBottom: 4,
  },
  toolbarBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
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
  sideBtnPlaceholder: {
    width: 52,
    height: 52,
  },
  voiceBtn: {
    width: 200,
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
