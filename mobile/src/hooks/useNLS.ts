// 阿里云 NLS 语音识别 Hook

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NLSClient } from '@/services/nls/NLSClient';
import { AudioStreamRecorder } from '@/services/audio/AudioStreamRecorder';
import { nlsTokenManager } from '@/services/nls/NLSTokenManager';
import { NLSState } from '@/services/nls/types';
import { useNLSStore } from '@/stores/nlsStore';

export interface UseNLSOptions {
  onResult?: (text: string, isFinal: boolean) => void;
  onError?: (error: Error) => void;
  onStateChange?: (state: NLSState) => void;
}

export interface UseNLSReturn {
  state: NLSState;
  isRecording: boolean;
  currentText: string;
  volume: number;
  
  // 控制方法
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

export function useNLS(options: UseNLSOptions = {}): UseNLSReturn {
  const { t } = useTranslation();
  const { onResult, onError, onStateChange } = options;

  const [state, setState] = useState<NLSState>('idle');
  const [currentText, setCurrentText] = useState('');
  const [volume, setVolume] = useState(0);

  const nlsClientRef = useRef<NLSClient | null>(null);
  const audioRecorderRef = useRef<AudioStreamRecorder | null>(null);
  const stoppingRef = useRef<boolean>(false);

  // 同时更新共享 store，让不直接调用 useNLS 的组件也能获取状态
  const storeSetState = useNLSStore.getState().setState;
  const storeSetCurrentText = useNLSStore.getState().setCurrentText;
  const storeSetVolume = useNLSStore.getState().setVolume;

  // 更新状态
  const updateState = useCallback((newState: NLSState) => {
    setState(newState);
    storeSetState(newState as any);
    onStateChange?.(newState);
  }, [onStateChange, storeSetState]);

  // 初始化 NLS 客户端
  const initNLSClient = useCallback(async () => {
    try {
      // 获取 Token 和 AppKey（从 Gateway）
      const token = await nlsTokenManager.getValidToken();
      const appKey = nlsTokenManager.getAppKey();

      if (!appKey) {
        throw new Error(t('nls.errors.appKeyInvalid'));
      }

      // 创建 NLS 客户端
      // 注意：AudioStreamRecorder 输出的是 PCM 格式，不是 opus
      const client = new NLSClient(
        {
          appKey,
          token,
          sampleRate: 16000,
          format: 'pcm',
        },
        {
          onConnected: () => {
            console.log('NLS 已连接');
            updateState('connected');
          },
          onDisconnected: () => {
            console.log('NLS 已断开');
            updateState('idle');
          },
          onError: (error) => {
            console.error('NLS 错误:', error);
            onError?.(error);
            updateState('error');
          },
          onRecognitionStarted: () => {
            console.log('识别已开始');
            updateState('recognizing');
          },
          onResultChanged: (text) => {
            // 中间结果
            setCurrentText(text);
            storeSetCurrentText(text);
            onResult?.(text, false);
          },
          onSentenceEnd: (text) => {
            // 一句结束，最终结果
            setCurrentText(text);
            storeSetCurrentText(text);
            onResult?.(text, true);
          },
          onRecognitionCompleted: () => {
            console.log('识别完成');
          },
        }
      );

      nlsClientRef.current = client;
      return client;
    } catch (error) {
      console.error('初始化 NLS 失败:', error);
      onError?.(error as Error);
      throw error;
    }
  }, [onError, onResult, updateState]);

  // 开始识别
  const start = useCallback(async () => {
    if (state !== 'idle') {
      console.warn('NLS 已经在运行中');
      return;
    }

    try {
      updateState('connecting');

      // 1. 初始化 NLS 客户端
      const nlsClient = await initNLSClient();

      // 2. 连接 NLS
      await nlsClient.connect();

      // 3. 启动音频录制（实时流）
      // AudioStreamRecorder 输出 PCM 格式，NLS 需要配置为 pcm
      stoppingRef.current = false;
      const audioRecorder = new AudioStreamRecorder(
        {
          sampleRate: 16000,
          audioFormat: 'pcm',
          chunkSize: 3200,
        },
        {
          onAudioChunk: (chunk) => {
            // 如果正在停止，不再发送音频数据
            if (stoppingRef.current) return;
            // 发送音频数据到 NLS
            nlsClient.sendAudio(chunk);
          },
          onVolumeChange: (vol) => {
            setVolume(vol);
            storeSetVolume(vol);
          },
          onError: (error) => {
            console.error('录音错误:', error);
            onError?.(error);
          },
        }
      );

      await audioRecorder.start();
      audioRecorderRef.current = audioRecorder;

    } catch (error) {
      console.error('启动 NLS 失败:', error);
      updateState('error');
      onError?.(error as Error);
    }
  }, [initNLSClient, onError, state, updateState]);

  // 停止识别
  const stop = useCallback(async () => {
    try {
      // 1. 先标记为正在停止，防止继续发送音频数据
      stoppingRef.current = true;

      // 2. 停止音频录制
      await audioRecorderRef.current?.stop();
      audioRecorderRef.current = null;

      // 3. 发送停止识别指令，等待最后结果
      nlsClientRef.current?.stopRecognition();

      // 4. 等待一段时间让最后结果返回（NLS 需要时间处理缓冲区）
      await new Promise(resolve => setTimeout(resolve, 500));

      // 5. 断开 NLS 连接
      nlsClientRef.current?.disconnect();
      nlsClientRef.current = null;

      // 6. 重置状态
      setCurrentText('');
      setVolume(0);
      storeSetCurrentText('');
      storeSetVolume(0);
      updateState('idle');

    } catch (error) {
      console.error('停止 NLS 失败:', error);
    }
  }, [updateState]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    state,
    isRecording: state === 'connected' || state === 'recognizing',
    currentText,
    volume,
    start,
    stop,
  };
}
