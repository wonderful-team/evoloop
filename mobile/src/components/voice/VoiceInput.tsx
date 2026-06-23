// 语音/文本输入组件 - 支持引用、TTS、语音打断

import React, { useState, useCallback, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { View, StyleSheet, TextInput, Keyboard, TouchableOpacity } from 'react-native';
import { Text, Divider } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { ImageOrVideo } from 'react-native-image-crop-picker';
import { Alert } from 'react-native';
import { VoiceSessionState } from '@/types/voice';
import { FilePicker, PickedFile, UploadedFile } from './FilePicker';
import { uploadChatFile } from '@/services/api/upload';
import { VoiceInputReferencesBar } from './VoiceInputReferencesBar';
import { MessageReference } from '@/types/conversation';
import { ReferencePicker } from '@/components/chat/ReferencePicker';
import { VoiceInputVoicePanel } from './VoiceInputVoicePanel';
import { useTranslation } from 'react-i18next';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MediaPickerModal } from '@/components/common/MediaPickerModal';
import { useAuthStore } from '@/stores/authStore';
import { router } from '@/utils/navigation';

export enum InputMode {
  VOICE = 'voice',
  TEXT = 'text',
}

export interface VoiceInputHandle {
  addReference: (reference: MessageReference) => void;
  setText: (text: string) => void;
}

interface VoiceInputProps {
  state: VoiceSessionState;
  onSendText: (text: string, options?: {
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
  onToggleWakeWord?: () => void;
  // 实时转录文字
  transcriptionText?: string;
}

export const VoiceInput = forwardRef<VoiceInputHandle, VoiceInputProps>(({
  state,
  onSendText,
  onToggleVoice: _onToggleVoice,
  onInterrupt,
  onPressIn,
  onPressOut,
  disabled = false,
  placeholder = '',
  inputMode: externalInputMode,
  onToggleMode,
  nlsVolume,
  autoSpeak = false,
  onToggleAutoSpeak,
  isSpeaking = false,
  projectId,
  conversationId,
  wakeWordEnabled: _wakeWordEnabled = false,
  isWakeWordListening = false,
  isWakeWordDetected = false,
  onToggleWakeWord,
  // 实时转录文字
  transcriptionText = '',
}, ref) => {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
  const [text, setText] = useState('');
  const [internalInputMode, setInternalInputMode] = useState<InputMode>(InputMode.VOICE);
  const [pickedFiles, setPickedFiles] = useState<PickedFile[]>([]);

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
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
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
    const hasContent = text.trim() || uploadedFiles.length > 0 || references.length > 0;
    if (hasContent && !disabled) {
      const mappedUploadedFiles = uploadedFiles.map(file => ({
        id: file.url,
        type: file.type === 'video' ? 'file' : file.type as any,
        target_id: file.url,
        target_name: file.name,
        meta_data: { ext: file.ext }
      }));

      const combinedRefs = [...references, ...mappedUploadedFiles];

      onSendText(text.trim(), {
        references: combinedRefs.length > 0 ? combinedRefs : undefined,
      });
      setText('');
      setPickedFiles([]);
      setUploadedFiles([]);
      setReferences([]);
      Keyboard.dismiss();
    }
  }, [text, uploadedFiles, references, disabled, onSendText]);

  const toggleMode = useCallback(() => {
    if (onToggleMode) {
      onToggleMode();
    } else {
      setInternalInputMode(prev => prev === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE);
    }
    if (isTextMode) {Keyboard.dismiss();}
  }, [isTextMode, onToggleMode]);

  // 暴露给外部调用（引用面板等）
  useImperativeHandle(ref, () => ({
    addReference: (reference: MessageReference) => {
      // 避免重复添加
      if (!references.some(r => r.id === reference.id)) {
        setReferences(prev => [...prev, reference]);
      }
      // 在文本中插入引用标记
      const refText = `@${reference.name} `;
      setText(prev => prev + refText);
    },
    setText: (newText: string) => {
      setText(newText);
    }
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
    if (!isLoggedIn) {
      router.push('Auth');
      return;
    }
    if (pickedFiles.length >= 5) {
      Alert.alert(t('common.tip'), t('chat.pickedFiles.maxLimit'));
      return;
    }
    setShowMediaPicker(true);
  }, [isLoggedIn, pickedFiles.length, t]);

  const closeMediaPicker = useCallback(() => {
    setShowMediaPicker(false);
  }, []);

  const handleSelectImage = useCallback((images: ImageOrVideo[]) => {
    const newFiles: PickedFile[] = images.map((asset, index) => ({
      id: `media_${Date.now()}_${index}`,
      type: asset.mime?.startsWith('video/') ? 'video' : 'image',
      uri: asset.path,
      name: asset.filename || `media_${Date.now()}_${index}.${asset.mime?.startsWith('video/') ? 'mp4' : 'jpg'}`,
      mimeType: asset.mime || 'image/jpeg',
      size: asset.size,
      uploading: false,
      uploaded: false,
    }));
    setPickedFiles(prev => [...prev, ...newFiles]);
  }, []);

  const handleSelectFile = useCallback(async (files: any[]) => {
    const newUploadedFiles: UploadedFile[] = [];
    for (const file of files.slice(0, 5 - pickedFiles.length)) {
      try {
        const uploaded = await uploadChatFile(file.uri, file.name);
        newUploadedFiles.push(uploaded);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : t('voice.input.uploadFailed');
        Alert.alert(t('voice.input.uploadErrorTitle'), msg);
      }
    }
    if (newUploadedFiles.length > 0) {
      setUploadedFiles(prev => [...prev, ...newUploadedFiles]);
    }
  }, [pickedFiles.length, t]);

  const hasContent = text.trim() || uploadedFiles.length > 0 || references.length > 0;

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* 附件预览 */}
      <FilePicker
        files={pickedFiles}
        onFilesChange={setPickedFiles}
        onUploadComplete={(newFiles) => setUploadedFiles(prev => [...prev, ...newFiles])}
        maxFiles={5}
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
              placeholder={placeholder || t('voice.input.placeholder')}
              placeholderTextColor={colors.onSurfaceVariant}
              multiline
              maxLength={500}
              editable={!disabled}
            />

            {/* @ 提示 - 暂时关闭引用功能入口 */}
            {/* {showReferenceHint && (
              <TouchableOpacity
                style={[styles.atHint, { backgroundColor: colors.primaryContainer }]}
                onPress={() => {
                  setShowReferenceHint(false);
                  setShowReferencePicker(true);
                }}
              >
                <MaterialIcons name="alternate-email" size={16} color={colors.primary} />
                <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 4 }}>
                  {t('voice.input.quoteMessage')}
                </Text>
              </TouchableOpacity>
            )} */}
          </View>


          {/* 附件按钮 */}
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={openMediaPicker}
          >
            <MaterialIcons name="attach-file" size={22} color={colors.onSurfaceVariant} />
          </TouchableOpacity>

          {/* 引用按钮 - 暂时关闭 */}
          {/* <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => setShowReferencePicker(true)}
          >
            <MaterialIcons name="alternate-email" size={22} color={colors.primary} />
          </TouchableOpacity> */}


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

          {/* 发送按钮 - 仅在有内容时显示 */}
          {hasContent && (
            <TouchableOpacity
              onPress={handleSend}
              disabled={disabled}
              style={[
                styles.sendBtn,
                {
                  backgroundColor: colors.primary,
                }
              ]}
            >
              <MaterialIcons
                name="arrow-upward"
                size={24}
                color={colors.onPrimary}
              />
            </TouchableOpacity>
          )}
        </View>


      ) : (
        // ===== 语音输入模式 =====
        <View style={styles.voiceWrap}>
          {/* 工具栏 */}
          <View style={styles.toolbar}>
            {/* 引用按钮 - 暂时关闭 */}
            {/* <TouchableOpacity
              style={styles.toolbarBtn}
              onPress={() => setShowReferencePicker(true)}
            >
              <MaterialIcons name="alternate-email" size={20} color={colors.primary} />
              <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 4 }}>
                {t('voice.input.quote')}
              </Text>
            </TouchableOpacity> */}


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
                  {isSpeaking ? t('voice.input.speaking') : autoSpeak ? t('voice.input.speakOn') : t('voice.input.speakOff')}
                </Text>
              </TouchableOpacity>
            )}

            {/* 唤醒词状态 */}
            {onToggleWakeWord && (
              <TouchableOpacity style={styles.toolbarBtn} onPress={onToggleWakeWord}>
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
                  {isWakeWordDetected ? t('voice.input.awakened') : isWakeWordListening ? t('voice.input.listening') : t('voice.input.standby')}
                </Text>
              </TouchableOpacity>
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
                size={28}
                color={isListening ? colors.onSuccess : colors.onPrimary}
              />
              <Text
                variant="titleMedium"
                style={[
                  styles.voiceBtnText,
                  { color: isListening ? colors.onSuccess : colors.onPrimary },
                ]}
              >
                {isListening ? t('voice.input.releaseToSend') : t('voice.input.holdToSpeak')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.sideBtn} onPress={toggleMode}>
              <MaterialIcons name="keyboard" size={28} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          </View>
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
        maxFiles={5 - pickedFiles.length}
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
    width: '100%',
    fontSize: 16,
    minHeight: 40,
    maxHeight: 120,
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
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },

  // 语音输入
  voiceWrap: {
    alignItems: 'center',
    paddingVertical: 12,
    paddingBottom: 16, // 减小底部间距
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
    width: 220,
    height: 56, // 降低高度
    borderRadius: 28,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 6,
  },
  voiceBtnText: {
    marginLeft: 12,
    fontWeight: 'bold',
  },

});
