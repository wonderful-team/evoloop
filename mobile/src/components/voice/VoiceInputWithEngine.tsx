// 语音输入组件封装
// 替代 VoiceInputWithNLS，使用新版 useVoiceInput

import React, { forwardRef, useImperativeHandle, useRef, useCallback, useMemo, useEffect } from 'react';
import { VoiceInput, VoiceInputHandle, InputMode } from './VoiceInput';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useVoiceSessionStore } from '@/stores/voiceSessionStore';
import { MessageReference } from '@/types/conversation';

export interface VoiceInputWithEngineHandle extends VoiceInputHandle {
  startVoiceInput: () => Promise<void>;
  stopVoiceInput: () => Promise<void>;
  setText: (text: string) => void;
  isRecording: boolean;
}

interface VoiceInputWithEngineProps {
  onSendText: (text: string, options?: { references?: MessageReference[] }) => void;
  onInterrupt: () => void;
  inputMode: InputMode;
  onToggleMode: () => void;
  autoSpeak: boolean;
  onToggleAutoSpeak: () => void;
  isSpeaking: boolean;
  projectId?: number;
  conversationId?: string;
  wakeWordEnabled: boolean;
  isWakeWordListening: boolean;
  isWakeWordDetected: boolean;
  onToggleWakeWord?: () => void;
  onBeforeStartRecording?: () => Promise<boolean>;
  onFinalResult: (text: string) => void;
  onError?: (error: Error) => void;
  onRecordingEnd?: () => void;
}

export const VoiceInputWithEngine = forwardRef<VoiceInputWithEngineHandle, VoiceInputWithEngineProps>((props, ref) => {
  const {
    onSendText,
    onInterrupt,
    inputMode,
    onToggleMode,
    autoSpeak,
    onToggleAutoSpeak,
    isSpeaking,
    projectId,
    conversationId,
    wakeWordEnabled,
    isWakeWordListening,
    isWakeWordDetected,
    onToggleWakeWord,
    onBeforeStartRecording,
    onFinalResult,
    onError,
    onRecordingEnd,
  } = props;

  const voiceInputRef = useRef<VoiceInputHandle>(null);
  const onRecordingEndRef = useRef(onRecordingEnd);
  onRecordingEndRef.current = onRecordingEnd;

  const { pressIn, pressOut, toggle, stop } = useVoiceInput({
    onFinalResult,
    onError,
    onInterrupt,
  });

  const sessionState = useVoiceSessionStore((s) => s.state);
  const partialText = useVoiceSessionStore((s) => s.partialText);
  const finalText = useVoiceSessionStore((s) => s.finalText);
  const volume = useVoiceSessionStore((s) => s.volume);
  const isPressed = useVoiceSessionStore((s) => s.isPressed);

  const prevIsRecording = useRef(false);
  const isRecording = sessionState === 'listening' || sessionState === 'speaking' || sessionState === 'recognizing';

  useEffect(() => {
    if (prevIsRecording.current && !isRecording) {
      onRecordingEndRef.current?.();
    }
    prevIsRecording.current = isRecording;
  }, [isRecording]);

  const combinedState = useMemo(() => {
    if (!isRecording) {return 'idle';}
    if (sessionState === 'speaking') {return 'listening';}
    return sessionState;
  }, [sessionState, isRecording]);

  const transcriptionText = useMemo(() => {
    return partialText || finalText;
  }, [partialText, finalText]);

  useImperativeHandle(ref, () => ({
    addReference: (reference: MessageReference) => {
      voiceInputRef.current?.addReference(reference);
    },
    setText: (text: string) => {
      voiceInputRef.current?.setText(text);
    },
    startVoiceInput: async () => {
      const ok = onBeforeStartRecording ? await onBeforeStartRecording() : true;
      if (ok) {await toggle();}
    },
    stopVoiceInput: stop,
    isRecording,
  }), [voiceInputRef, onBeforeStartRecording, toggle, stop, isRecording]);

  const handlePressIn = useCallback(async () => {
    const ok = onBeforeStartRecording ? await onBeforeStartRecording() : true;
    if (!ok) {return;}
    await pressIn();
  }, [onBeforeStartRecording, pressIn]);

  const handlePressOut = useCallback(async () => {
    await pressOut();
  }, [pressOut]);

  return (
    <VoiceInput
      ref={voiceInputRef}
      state={combinedState}
      onSendText={onSendText}
      onInterrupt={onInterrupt}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      inputMode={inputMode}
      onToggleMode={onToggleMode}
      nlsVolume={volume}
      autoSpeak={autoSpeak}
      onToggleAutoSpeak={onToggleAutoSpeak}
      isSpeaking={isSpeaking}
      projectId={projectId}
      conversationId={conversationId}
      wakeWordEnabled={wakeWordEnabled}
      isWakeWordListening={isWakeWordListening}
      isWakeWordDetected={isWakeWordDetected}
      onToggleWakeWord={onToggleWakeWord}
      transcriptionText={transcriptionText}
      isPressed={isPressed}
    />
  );
});
