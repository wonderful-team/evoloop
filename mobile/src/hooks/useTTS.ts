// TTS (文本转语音) Hook

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/services/api/client';
import RNFS from 'react-native-fs';
import { BASE_URL } from '@/constants/config';

export interface TTSOptions {
  voiceId?: string;
  speed?: number;
  format?: 'mp3' | 'opus' | 'aac' | 'flac';
}

export interface TTSVoice {
  id: string;
  name: string;
  gender: string;
  description: string;
}

const DEFAULT_VOICES: TTSVoice[] = [
  { id: 'zh-CN-XiaoxiaoNeural', name: '晓晓', gender: 'female', description: '温柔自然，最推荐' },
  { id: 'zh-CN-YunxiNeural', name: '云希', gender: 'male', description: '年轻阳光，最推荐' },
  { id: 'zh-CN-YunjianNeural', name: '云健', gender: 'male', description: '新闻播报风格' },
  { id: 'zh-CN-XiaoyiNeural', name: '小艺', gender: 'female', description: '活泼年轻' },
];

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
  // 音频播放器的引用，由外部注入
  setAudioPlayer: (player: AudioPlayerCallback) => void;
}

export function useTTS(): UseTTSReturn {
  const { t } = useTranslation();
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<TTSVoice[]>(DEFAULT_VOICES);
  const [currentVoice, setCurrentVoice] = useState('zh-CN-XiaoxiaoNeural');

  const audioPlayerRef = useRef<AudioPlayerCallback | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentAudioUriRef = useRef<string | null>(null);

  // 设置音频播放器
  const setAudioPlayer = useCallback((player: AudioPlayerCallback) => {
    audioPlayerRef.current = player;
  }, []);

  // 清理函数：组件卸载时确保停止播放并删除音频文件
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (currentAudioUriRef.current) {
        RNFS.unlink(currentAudioUriRef.current).catch(() => {});
      }
    };
  }, []);

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // 清理当前音频文件
    if (currentAudioUriRef.current) {
      RNFS.unlink(currentAudioUriRef.current).catch(console.error);
      currentAudioUriRef.current = null;
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

    setIsLoading(true);
    setError(null);

    try {
      const voiceId = options.voiceId || currentVoice;
      const speed = options.speed ?? 1.0;
      const format = options.format || 'mp3';

      const formData = new FormData();
      formData.append('text', text);
      formData.append('voice_id', voiceId);
      formData.append('speed', speed.toString());
      formData.append('format', format);

      const response = await fetch(`${BASE_URL}/member/api/v1/audio/tts-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'TTS failed');
      }

      // 获取音频 blob
      const blob = await response.blob();
      const reader = new FileReader();

      const audioPath = await new Promise<string>((resolve, reject) => {
        reader.onloadend = () => {
          const base64data = reader.result as string;
          const base64Audio = base64data.split(',')[1];
          const path = `${RNFS.CachesDirectoryPath}/tts_${Date.now()}.mp3`;

          RNFS.writeFile(path, base64Audio, 'base64')
            .then(() => resolve(path))
            .catch(reject);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });

      currentAudioUriRef.current = audioPath;
      setIsSpeaking(true);
      setIsLoading(false);

      // 调用外部音频播放器
      audioPlayerRef.current(
        audioPath,
        () => {
          // 播放完成
          setIsSpeaking(false);
          if (currentAudioUriRef.current) {
            RNFS.unlink(currentAudioUriRef.current).catch(console.error);
            currentAudioUriRef.current = null;
          }
        },
        (err) => {
          // 播放错误
          setError(t('chat.tts.playbackError', '播放失败'));
          setIsSpeaking(false);
          if (currentAudioUriRef.current) {
            RNFS.unlink(currentAudioUriRef.current).catch(() => {});
            currentAudioUriRef.current = null;
          }
        }
      );

    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const msg = err instanceof Error ? err.message : t('chat.tts.error', '语音合成失败');
      setError(msg);
      setIsSpeaking(false);
      setIsLoading(false);
      // 合成失败时清理已生成的音频文件
      if (currentAudioUriRef.current) {
        RNFS.unlink(currentAudioUriRef.current).catch(() => {});
        currentAudioUriRef.current = null;
      }
    }
  }, [currentVoice, stop, t]);

  const fetchVoices = useCallback(async () => {
    try {
      const data = await api.get('/api/v1/audio/voices') as { voices: TTSVoice[] };
      if (data.voices && Array.isArray(data.voices)) {
        setVoices(data.voices);
      }
    } catch (err) {
      console.warn('Failed to fetch voices:', err);
      // 保持默认语音列表
    }
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
  };
}

// 自动朗读设置 Hook
export function useAutoSpeak() {
  const [autoSpeak, setAutoSpeakState] = useState(false);

  // 从存储加载设置
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
      // 播放完成后继续下一个
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
