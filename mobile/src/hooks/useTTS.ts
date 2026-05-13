// TTS (文本转语音) Hook — 使用阿里云百炼 Qwen3-TTS HTTP API
// 与 NLS 语音识别解耦，TTS 独立使用 DashScope API Key

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import RNFS from 'react-native-fs';
import { DASHSCOPE_CONFIG } from '@/constants/config';

const DASHSCOPE_TTS_ENDPOINT = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation';

export interface TTSOptions {
  voiceId?: string;
  speed?: number;
  format?: 'mp3' | 'pcm' | 'wav';
  instructions?: string;
}

export interface TTSVoice {
  id: string;
  name: string;
  gender: string;
  description: string;
}

// Qwen3-TTS 预置音色（百炼控制台可查看完整列表）
export function getDefaultVoices(t: TFunction): TTSVoice[] {
  return [
    { id: 'Cherry', name: 'Cherry', gender: 'female', description: t('chat.tts.cherryDesc') },
    { id: 'Serena', name: 'Serena', gender: 'female', description: t('chat.tts.serenaDesc') },
  ];
}

// Qwen3-TTS 文本长度限制（约 800 个汉字）
const QWEN_TTS_MAX_TEXT_LENGTH = 800;

// 音频播放器回调类型
type AudioPlayerCallback = (uri: string, onEnd: () => void, onError: (error: any) => void) => void;

interface UseTTSReturn {
  isSpeaking: boolean;
  isLoading: boolean;
  error: string | null;
  voices: TTSVoice[];
  currentVoice: string;
  setCurrentVoice: (voice: string) => void;
  speak: (text: string, options?: TTSOptions) => Promise<void>;
  /** 加入播放队列（不打断当前播放） */
  enqueue: (text: string, options?: TTSOptions) => void;
  /** 清空队列并停止 */
  clearQueue: () => void;
  /** 当前队列长度 */
  queueLength: number;
  stop: () => void;
  fetchVoices: () => Promise<void>;
  setAudioPlayer: (player: AudioPlayerCallback) => void;
  setOnStop: (callback: (() => void) | null) => void;
}

export function useTTS(): UseTTSReturn {
  const { t } = useTranslation();
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<TTSVoice[]>(getDefaultVoices(t));
  const [currentVoice, setCurrentVoiceState] = useState('Cherry');
  const [queueLength, setQueueLength] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);

  // 加载保存的声音设置
  useEffect(() => {
    const loadVoice = async () => {
      try {
        const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
        const saved = await AsyncStorage.getItem('evoloop_tts_voice');
        if (saved) {
          setCurrentVoiceState(saved);
        }
      } catch (e) {
        // 忽略加载错误，使用默认
      }
    };
    loadVoice();
  }, []);

  const setCurrentVoice = useCallback(async (voice: string) => {
    setCurrentVoiceState(voice);
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem('evoloop_tts_voice', voice);
    } catch (e) {
      // 忽略保存错误
    }
  }, []);

  const audioPlayerRef = useRef<AudioPlayerCallback | null>(null);
  const onStopRef = useRef<(() => void) | null>(null);
  const currentAudioUriRef = useRef<string | null>(null);

  // 设置音频播放器
  const setAudioPlayer = useCallback((player: AudioPlayerCallback) => {
    audioPlayerRef.current = player;
  }, []);

  // 注册 TTS 停止回调（供外部组件在 stop 时清理状态，如卸载 Video）
  const setOnStop = useCallback((callback: (() => void) | null) => {
    onStopRef.current = callback;
  }, []);

  // 清理函数：组件卸载时确保停止播放并删除音频文件
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      const path = currentAudioUriRef.current;
      currentAudioUriRef.current = null;
      if (path) {
        RNFS.unlink(path).catch(() => {});
      }
    };
  }, []);

  const stop = useCallback(() => {
    // 中断正在进行的请求
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    // 先通知外部卸载 Video，再删除文件
    onStopRef.current?.();

    // 原子删除：先取路径、立即清空 ref、再删文件，防止和 onEnd 回调并发重复删除
    const path = currentAudioUriRef.current;
    currentAudioUriRef.current = null;
    if (path) {
      RNFS.unlink(path).catch(() => {});
    }

    // 重置处理状态，避免队列卡死
    isProcessingRef.current = false;

    setIsSpeaking(false);
    setIsLoading(false);
  }, []);

  // 核心 TTS 合成+播放逻辑（不调用 stop，返回 Promise）
  const playCore = useCallback(async (text: string, options: TTSOptions = {}): Promise<void> => {
    console.log('[useTTS] playCore start:', text.slice(0, 30));
    if (!audioPlayerRef.current) {
      console.warn('Audio player not set. Call setAudioPlayer first.');
      return;
    }
    if (!text.trim()) return;

    const truncatedText = truncateAtSentenceBoundary(text, QWEN_TTS_MAX_TEXT_LENGTH);
    setIsLoading(true);
    setError(null);

    try {
      const voice = options.voiceId || currentVoice;
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const apiResponse = await fetch(DASHSCOPE_TTS_ENDPOINT, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${DASHSCOPE_CONFIG.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'qwen3-tts-flash',
          input: {
            text: truncatedText,
            voice,
            language_type: 'Chinese',
          },
        }),
        signal: controller.signal,
      });

      if (!apiResponse.ok) {
        let errMsg = `HTTP ${apiResponse.status}`;
        try {
          const errData = await apiResponse.json();
          errMsg = errData.message || errData.code || errMsg;
        } catch {
          // 忽略
        }
        throw new Error(errMsg);
      }

      const data = await apiResponse.json();
      const audioUrl = data?.output?.audio?.url;
      if (!audioUrl) throw new Error(t('chat.tts.apiNoAudioUrl'));

      const timestamp = Date.now();
      const localPath = `${RNFS.DocumentDirectoryPath}/qwen_tts_${timestamp}.wav`;

      const downloadRes = await RNFS.downloadFile({
        fromUrl: audioUrl,
        toFile: localPath,
      }).promise;

      if (downloadRes.statusCode !== 200) {
        throw new Error(t('chat.tts.downloadFailed', { statusCode: downloadRes.statusCode }));
      }

      if (abortControllerRef.current !== controller) {
        RNFS.unlink(localPath).catch(() => {});
        return;
      }

      currentAudioUriRef.current = localPath;
      setIsSpeaking(true);
      setIsLoading(false);
      console.log('[useTTS] playCore start playing:', text.slice(0, 30));

      return new Promise<void>((resolve, reject) => {
        audioPlayerRef.current!(
          localPath,
          () => {
            setIsSpeaking(false);
            const path = currentAudioUriRef.current;
            currentAudioUriRef.current = null;
            if (path) RNFS.unlink(path).catch(() => {});
            resolve();
          },
          (err) => {
            setError(t('chat.tts.playbackError'));
            setIsSpeaking(false);
            const path = currentAudioUriRef.current;
            currentAudioUriRef.current = null;
            if (path) RNFS.unlink(path).catch(() => {});
            reject(new Error(err));
          }
        );
      });

    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : t('chat.tts.error');
      console.error('TTS 合成失败:', msg);
      setError(msg);
      setIsSpeaking(false);
      setIsLoading(false);
      const path = currentAudioUriRef.current;
      currentAudioUriRef.current = null;
      if (path) RNFS.unlink(path).catch(() => {});
    }
  }, [currentVoice, t]);

  // 播放队列
  const queueRef = useRef<Array<{ text: string; options: TTSOptions }>>([]);
  const isProcessingRef = useRef(false);

  const processQueue = useCallback(async () => {
    if (isProcessingRef.current || queueRef.current.length === 0) {
      setQueueLength(queueRef.current.length);
      return;
    }
    isProcessingRef.current = true;
    setQueueLength(queueRef.current.length);
    const item = queueRef.current.shift();
    console.log('[useTTS] processQueue shift:', item?.text.slice(0, 30), 'queue left:', queueRef.current.length);
    try {
      if (item) {
        await playCore(item.text, item.options);
      }
    } catch (error) {
      console.error('[useTTS] playCore error:', error);
    } finally {
      isProcessingRef.current = false;
      setQueueLength(queueRef.current.length);
      processQueue();
    }
  }, [playCore]);

  // 加入队列（不打断当前播放）
  const enqueue = useCallback((text: string, options: TTSOptions = {}) => {
    console.log('[useTTS] enqueue:', text.slice(0, 30));
    queueRef.current.push({ text, options });
    setQueueLength(queueRef.current.length);
    processQueue();
  }, [processQueue]);

  // 清空队列并停止
  const clearQueue = useCallback(() => {
    queueRef.current = [];
    stop();
  }, [stop]);

  // speak 保持现有行为：停止当前，播放新文本
  const speak = useCallback(async (text: string, options: TTSOptions = {}) => {
    clearQueue();
    await playCore(text, options);
  }, [clearQueue, playCore]);

  const fetchVoices = useCallback(async () => {
    // Qwen3-TTS 音色列表以百炼控制台为准，这里提供预置列表
    setVoices(getDefaultVoices(t));
  }, []);

  return {
    isSpeaking,
    isLoading,
    error,
    voices,
    currentVoice,
    setCurrentVoice,
    speak,
    enqueue,
    clearQueue,
    queueLength,
    stop,
    fetchVoices,
    setAudioPlayer,
    setOnStop,
  };
}

// 在标点符号处截断文本，避免句中截断导致语义断裂和 TTS 不自然
function truncateAtSentenceBoundary(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;

  // 在 maxLength 之前找最后一个句末标点
  const punctuationRegex = /[。！？.!?；;\n]/;
  let truncateIndex = maxLength;

  // 往回找，至少保留 70% 的长度
  for (let i = maxLength; i >= Math.floor(maxLength * 0.7); i--) {
    if (punctuationRegex.test(text[i])) {
      truncateIndex = i + 1;
      break;
    }
  }

  return text.slice(0, truncateIndex).trimEnd() + '...';
}

// 自动朗读设置 Hook
export function useAutoSpeak() {
  const [autoSpeak, setAutoSpeakState] = useState(false);

  useEffect(() => {
    const loadSetting = async () => {
      try {
        const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
        const saved = await AsyncStorage.getItem('evoloop_auto_speak');
        if (saved !== null) {
          setAutoSpeakState(saved === 'true');
        }
      } catch (e) {
        console.error('Failed to load auto speak setting:', e);
      }
    };
    loadSetting();
  }, []);

  const toggleAutoSpeak = useCallback(async () => {
    const newValue = !autoSpeak;
    setAutoSpeakState(newValue);
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem('evoloop_auto_speak', newValue.toString());
    } catch (e) {
      console.error('Failed to save auto speak setting:', e);
    }
  }, [autoSpeak]);

  const setAutoSpeak = useCallback(async (value: boolean) => {
    setAutoSpeakState(value);
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem('evoloop_auto_speak', value.toString());
    } catch (e) {
      console.error('Failed to save auto speak setting:', e);
    }
  }, []);

  return { autoSpeak, toggleAutoSpeak, setAutoSpeak };
}

// 队列式 TTS（用于顺序播放）— 复用 useTTS 内部的队列
export function useTTSQueue() {
  const { enqueue, clearQueue, stop, isSpeaking, queueLength, ...rest } = useTTS();

  return {
    ...rest,
    isSpeaking,
    queueLength: queueLength || 0,
    enqueue,
    clearQueue,
    stop,
  };
}
