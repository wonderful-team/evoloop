// TTS (文本转语音) Hook — 使用阿里云百炼 Qwen3-TTS HTTP API
// 与 NLS 语音识别解耦，TTS 独立使用 DashScope API Key

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
export const DEFAULT_VOICES: TTSVoice[] = [
  { id: 'Cherry', name: 'Cherry', gender: 'female', description: '★ 中文女声，对话感强' },
  { id: 'Serena', name: 'Serena', gender: 'female', description: '★ 英文女声，自然流畅' },
];

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
  const [voices, setVoices] = useState<TTSVoice[]>(DEFAULT_VOICES);
  const [currentVoice, setCurrentVoiceState] = useState('Cherry');

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

    setIsSpeaking(false);
    setIsLoading(false);
  }, []);

  const speak = useCallback(async (text: string, options: TTSOptions = {}) => {
    if (!audioPlayerRef.current) {
      console.warn('Audio player not set. Call setAudioPlayer first.');
      return;
    }

    // 停止当前播放
    stop();

    if (!text.trim()) return;

    // Qwen3-TTS 文本长度限制：在句末/标点处截断，避免语义断裂
    const truncatedText = truncateAtSentenceBoundary(text, QWEN_TTS_MAX_TEXT_LENGTH);

    setIsLoading(true);
    setError(null);

    try {
      const voice = options.voiceId || currentVoice;

      // 1. 调用 DashScope HTTP API 获取音频 URL
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
          // 响应体不是 JSON，用 status text
        }
        throw new Error(errMsg);
      }

      const data = await apiResponse.json();
      const audioUrl = data?.output?.audio?.url;

      if (!audioUrl) {
        throw new Error('API 未返回音频 URL');
      }

      // 2. 下载音频文件到本地
      const timestamp = Date.now();
      const localPath = `${RNFS.DocumentDirectoryPath}/qwen_tts_${timestamp}.wav`;

      const downloadRes = await RNFS.downloadFile({
        fromUrl: audioUrl,
        toFile: localPath,
      }).promise;

      if (downloadRes.statusCode !== 200) {
        throw new Error(`下载音频失败: ${downloadRes.statusCode}`);
      }

      // 3. 检查是否已被打断（stop 被调用，controller 已被替换）
      if (abortControllerRef.current !== controller) {
        // 已被中断，清理刚下载的文件
        RNFS.unlink(localPath).catch(() => {});
        return;
      }

      currentAudioUriRef.current = localPath;
      setIsSpeaking(true);
      setIsLoading(false);

      // 4. 调用外部音频播放器播放
      audioPlayerRef.current(
        localPath,
        () => {
          // 播放完成
          setIsSpeaking(false);
          const path = currentAudioUriRef.current;
          currentAudioUriRef.current = null;
          if (path) {
            RNFS.unlink(path).catch(() => {});
          }
        },
        (err) => {
          // 播放错误
          setError(t('chat.tts.playbackError', '播放失败'));
          setIsSpeaking(false);
          const path = currentAudioUriRef.current;
          currentAudioUriRef.current = null;
          if (path) {
            RNFS.unlink(path).catch(() => {});
          }
        }
      );

    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const msg = err instanceof Error ? err.message : t('chat.tts.error', '语音合成失败');
      console.error('TTS 合成失败:', msg);
      setError(msg);
      setIsSpeaking(false);
      setIsLoading(false);
      const path = currentAudioUriRef.current;
      currentAudioUriRef.current = null;
      if (path) {
        RNFS.unlink(path).catch(() => {});
      }
    }
  }, [currentVoice, stop, t]);

  const fetchVoices = useCallback(async () => {
    // Qwen3-TTS 音色列表以百炼控制台为准，这里提供预置列表
    setVoices(DEFAULT_VOICES);
  }, []);

  return {
    isSpeaking,
    isLoading,
    error,
    voices,
    currentVoice,
    setCurrentVoice,
    speak,
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

  return text.slice(0, truncateIndex).trimEnd() + '……';
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

// 队列式 TTS（用于顺序播放）
export function useTTSQueue() {
  const { speak, stop, isSpeaking, ...rest } = useTTS();
  const queueRef = useRef<string[]>([]);
  const [queueLength, setQueueLength] = useState(0);
  const isProcessingRef = useRef(false);

  const speakNext = useCallback(async () => {
    if (isProcessingRef.current || queueRef.current.length === 0) return;

    isProcessingRef.current = true;
    const text = queueRef.current.shift();
    setQueueLength(queueRef.current.length);

    if (text) {
      await speak(text);
      isProcessingRef.current = false;
      speakNext();
    } else {
      isProcessingRef.current = false;
    }
  }, [speak]);

  const enqueue = useCallback((text: string) => {
    queueRef.current.push(text);
    setQueueLength(queueRef.current.length);
    speakNext();
  }, [speakNext]);

  const clearQueue = useCallback(() => {
    queueRef.current = [];
    setQueueLength(0);
    stop();
    isProcessingRef.current = false;
  }, [stop]);

  return {
    ...rest,
    isSpeaking,
    queueLength,
    enqueue,
    clearQueue,
    stop,
  };
}
