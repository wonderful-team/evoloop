// VoiceInput + NLS 封装组件
// 将 useNLS Hook 从 ChatScreen 中移出，自行管理语音识别状态，
// 切断 nlsCurrentText / nlsVolume 的高频变化对 ChatScreen 的影响。
// ChatScreen 通过 ref 暴露的 startNLS / stopNLS 控制录音启停。

import React, { forwardRef, useImperativeHandle, useRef, useCallback, useMemo, useEffect } from 'react';
import { VoiceInput, VoiceInputHandle, InputMode } from './VoiceInput';
import { useNLS } from '@/hooks/useNLS';
import { useNLSStore } from '@/stores/nlsStore';
import { MessageReference } from '@/types/conversation';

export interface VoiceInputWithNLSHandle extends VoiceInputHandle {
  /** 启动 NLS 语音识别 */
  startNLS: () => Promise<void>;
  /** 停止 NLS 语音识别 */
  stopNLS: () => Promise<void>;
  /** 当前是否正在录音 */
  nlsIsRecording: boolean;
}

interface VoiceInputWithNLSProps {
  /** 发送文本消息 */
  onSendText: (text: string, options?: {
    attachments?: any[];
    references?: MessageReference[];
  }) => void;
  /** 打断 TTS/Agent */
  onInterrupt: () => void;
  /** 当前输入模式 */
  inputMode: InputMode;
  /** 切换输入模式 */
  onToggleMode: () => void;
  /** 自动朗读 */
  autoSpeak: boolean;
  /** 切换自动朗读 */
  onToggleAutoSpeak: () => void;
  /** TTS 是否正在播放 */
  isSpeaking: boolean;
  /** 项目 ID */
  projectId?: number;
  /** 会话 ID */
  conversationId?: string;
  /** 唤醒词开关 */
  wakeWordEnabled: boolean;
  /** 唤醒词监听中 */
  isWakeWordListening: boolean;
  /** 唤醒词已检测到 */
  isWakeWordDetected: boolean;
  /** 切换唤醒词开关 */
  onToggleWakeWord?: () => void;
  /** 录音启动前的前置检查（权限、登录等），返回 false 则取消录音 */
  onBeforeStartRecording?: () => Promise<boolean>;
  /** 语音识别最终结果回调 */
  onFinalResult: (text: string) => void;
  /** 语音识别错误回调 */
  onError?: (error: Error) => void;
  /** NLS 录音结束回调（无论是否有结果、无论通过何种方式停止） */
  onRecordingEnd?: () => void;
}

export const VoiceInputWithNLS = forwardRef<VoiceInputWithNLSHandle, VoiceInputWithNLSProps>((props, ref) => {
  const voiceInputRef = useRef<VoiceInputHandle>(null);
  const accumulatedTextRef = useRef<string>('');
  const onRecordingEndRef = useRef(props.onRecordingEnd);
  onRecordingEndRef.current = props.onRecordingEnd;
  const prevNlsIsRecording = useRef(false);

  // NLS Hook：累积识别结果，不在 onResult 中直接发送（避免一句一发）
  const { start, stop } = useNLS({
    onResult: (text, _isFinal) => {
      // 实时保存最新识别文本（中间结果和最终结果都更新，保证完整性）
      accumulatedTextRef.current = text;
    },
    onError: props.onError,
  });

  // 从共享 store 读取高频变化状态（避免通过 props 传递到 ChatScreen）
  const nlsState = useNLSStore((s) => s.state);
  const nlsIsRecording = useNLSStore((s) => s.isRecording);
  const nlsCurrentText = useNLSStore((s) => s.currentText);
  const nlsVolume = useNLSStore((s) => s.volume);

  // 监听 NLS 录音状态变化：从录音变为停止时，通知外层恢复唤醒词
  useEffect(() => {
    if (prevNlsIsRecording.current && !nlsIsRecording) {
      onRecordingEndRef.current?.();
    }
    prevNlsIsRecording.current = nlsIsRecording;
  }, [nlsIsRecording]);

  // 映射 NLS 状态到 VoiceInput 需要的 VoiceSessionState
  const combinedState = useMemo(() => {
    if (!nlsIsRecording) return 'idle';
    switch (nlsState) {
      case 'connected': return 'listening';
      case 'error': return 'idle';
      default: return nlsState;
    }
  }, [nlsState, nlsIsRecording]);

  // 暴露方法给父组件（ChatScreen）
  useImperativeHandle(ref, () => ({
    addReference: (reference: MessageReference) => {
      voiceInputRef.current?.addReference(reference);
    },
    startNLS: start,
    stopNLS: stop,
    nlsIsRecording,
  }), [start, stop, nlsIsRecording]);

  // 按下录音按钮
  const handlePressIn = useCallback(async () => {
    accumulatedTextRef.current = '';
    // 执行外部前置检查（如权限、登录状态、TTS 打断等）
    if (props.onBeforeStartRecording) {
      const shouldProceed = await props.onBeforeStartRecording();
      if (!shouldProceed) return;
    }
    try {
      await start();
    } catch (error: any) {
      props.onError?.(error);
    }
  }, [props.onBeforeStartRecording, start, props.onError]);

  // 松开录音按钮
  const handlePressOut = useCallback(async () => {
    if (nlsIsRecording) {
      await stop();
      // 只在录音完全结束后统一发送一次最终结果
      const finalText = accumulatedTextRef.current.trim();
      if (finalText) {
        props.onFinalResult(finalText);
        accumulatedTextRef.current = '';
      }
    }
  }, [nlsIsRecording, stop, props.onFinalResult]);

  return (
    <VoiceInput
      ref={voiceInputRef}
      state={combinedState}
      onSendText={props.onSendText}
      onInterrupt={props.onInterrupt}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      inputMode={props.inputMode}
      onToggleMode={props.onToggleMode}
      nlsVolume={nlsVolume}
      autoSpeak={props.autoSpeak}
      onToggleAutoSpeak={props.onToggleAutoSpeak}
      isSpeaking={props.isSpeaking}
      projectId={props.projectId}
      conversationId={props.conversationId}
      wakeWordEnabled={props.wakeWordEnabled}
      isWakeWordListening={props.isWakeWordListening}
      isWakeWordDetected={props.isWakeWordDetected}
      onToggleWakeWord={props.onToggleWakeWord}
      transcriptionText={nlsCurrentText}
    />
  );
});
