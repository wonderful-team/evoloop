// 唤醒词检测 Hook

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AudioRecorder } from '@/services/voice/AudioRecorder';
import { VADDetector, VADConfig } from '@/services/voice/VADDetector';

// 默认唤醒词配置
const DEFAULT_WAKE_WORD = '你好 EvoLoop';
const DEFAULT_SIMILARITY_THRESHOLD = 0.7;

export interface WakeWordConfig {
  wakeWord: string;
  enabled: boolean;
  threshold?: number;
}

export interface UseWakeWordReturn {
  isListening: boolean;
  isWakeWordDetected: boolean;
  lastDetectedWord: string | null;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
  checkWakeWord: (text: string) => boolean;
}

interface UseWakeWordOptions {
  onWake?: (detectedWord: string) => void;
  config?: WakeWordConfig;
}

/**
 * 计算两个字符串的相似度（简单的编辑距离）
 */
function calculateSimilarity(str1: string, str2: string): number {
  const s1 = str1.toLowerCase().replace(/\s+/g, '');
  const s2 = str2.toLowerCase().replace(/\s+/g, '');

  if (s1 === s2) return 1.0;

  const len = Math.max(s1.length, s2.length);
  if (len === 0) return 1.0;

  // 简单的编辑距离
  const matrix: number[][] = [];
  for (let i = 0; i <= s1.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= s2.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= s1.length; i++) {
    for (let j = 1; j <= s2.length; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + cost
      );
    }
  }

  const distance = matrix[s1.length][s2.length];
  return 1 - distance / len;
}

/**
 * 唤醒词检测 Hook
 * 使用 VAD 检测语音活动，然后通过 ASR 识别文本，最后匹配唤醒词
 */
export function useWakeWord(options: UseWakeWordOptions = {}): UseWakeWordReturn {
  const { t } = useTranslation();
  const { onWake, config } = options;

  const [isListening, setIsListening] = useState(false);
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false);
  const [lastDetectedWord, setLastDetectedWord] = useState<string | null>(null);

  const wakeWord = config?.wakeWord || DEFAULT_WAKE_WORD;
  const enabled = config?.enabled ?? true;
  const threshold = config?.threshold || DEFAULT_SIMILARITY_THRESHOLD;

  const vadRef = useRef<VADDetector | null>(null);
  const audioRecorderRef = useRef<AudioRecorder | null>(null);
  const isProcessingRef = useRef(false);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 检查唤醒词
  const checkWakeWord = useCallback((text: string): boolean => {
    if (!text.trim()) return false;

    // 支持多个唤醒词（逗号分隔）
    const wakeWords = wakeWord.split(',').map(w => w.trim());

    for (const word of wakeWords) {
      // 精确匹配
      if (text.toLowerCase().includes(word.toLowerCase())) {
        return true;
      }

      // 模糊匹配
      const similarity = calculateSimilarity(text, word);
      if (similarity >= threshold) {
        return true;
      }

      // 检查是否包含关键词
      const keywords = word.toLowerCase().split(/\s+/);
      const textLower = text.toLowerCase();
      const allKeywordsPresent = keywords.every(kw => textLower.includes(kw));
      if (allKeywordsPresent) {
        return true;
      }
    }

    return false;
  }, [wakeWord, threshold]);

  // 处理检测到的语音
  const handleSpeechDetected = useCallback(async () => {
    if (isProcessingRef.current) return;

    isProcessingRef.current = true;

    try {
      // 开始录音
      await audioRecorderRef.current?.initialize();

      // 等待一小段语音
      await new Promise(resolve => setTimeout(resolve, 1500));

      // 停止录音并获取音频
      const audioUri = await audioRecorderRef.current?.stop();

      if (audioUri) {
        // 这里应该调用 ASR 服务识别语音
        // 由于唤醒词检测通常在本地完成，我们可以使用轻量级的 ASR
        // 或者将音频发送到后端进行识别

        // 简化实现：通过 VAD 的音量变化来粗略判断是否可能是唤醒词
        // 实际项目中应该使用专门的唤醒词检测模型

        // 清理音频文件
        await audioRecorderRef.current?.deleteAudioFile(audioUri);
      }
    } catch (error) {
      console.error('Wake word detection error:', error);
    } finally {
      isProcessingRef.current = false;
    }
  }, []);

  // 开始监听
  const startListening = useCallback(async () => {
    if (!enabled || isListening) return;

    try {
      // 初始化音频录制器
      audioRecorderRef.current = new AudioRecorder();

      // 初始化 VAD 检测器
      vadRef.current = new VADDetector(
        { threshold: 0.1, sampleRate: 16000 },
        {
          onSpeechStart: () => {
            console.log('Speech start detected');
            // 清除静默定时器
            if (silenceTimerRef.current) {
              clearTimeout(silenceTimerRef.current);
              silenceTimerRef.current = null;
            }
          },
          onSpeechEnd: () => {
            console.log('Speech end detected');
            // 设置静默定时器，一段时间后触发检测
            silenceTimerRef.current = setTimeout(() => {
              handleSpeechDetected();
            }, 500);
          },
          onVolumeChange: (volume) => {
            // 可以在这里更新音量指示器
          },
        }
      );

      await vadRef.current.start();
      setIsListening(true);
    } catch (error) {
      console.error('Failed to start wake word listening:', error);
    }
  }, [enabled, isListening, handleSpeechDetected]);

  // 停止监听
  const stopListening = useCallback(async () => {
    try {
      await vadRef.current?.stop();
      await audioRecorderRef.current?.cleanup();

      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }

      setIsListening(false);
      setIsWakeWordDetected(false);
    } catch (error) {
      console.error('Failed to stop wake word listening:', error);
    }
  }, []);

  // 模拟唤醒词检测（用于测试）
  const simulateWakeWordDetection = useCallback((text: string) => {
    if (checkWakeWord(text)) {
      setIsWakeWordDetected(true);
      setLastDetectedWord(text);
      onWake?.(text);

      // 自动重置检测状态
      setTimeout(() => {
        setIsWakeWordDetected(false);
      }, 3000);
    }
  }, [checkWakeWord, onWake]);

  // 清理
  useEffect(() => {
    return () => {
      stopListening();
    };
  }, [stopListening]);

  return {
    isListening,
    isWakeWordDetected,
    lastDetectedWord,
    startListening,
    stopListening,
    checkWakeWord,
  };
}

// 唤醒词设置 Hook
export function useWakeWordSettings() {
  const [settings, setSettings] = useState<WakeWordConfig>({
    wakeWord: DEFAULT_WAKE_WORD,
    enabled: false,
    threshold: DEFAULT_SIMILARITY_THRESHOLD,
  });

  // 从存储加载设置
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
        const saved = await AsyncStorage.getItem('evoloop_wake_word_settings');
        if (saved) {
          setSettings(prev => ({ ...prev, ...JSON.parse(saved) }));
        }
      } catch (e) {
        console.error('Failed to load wake word settings:', e);
      }
    };
    loadSettings();
  }, []);

  // 保存设置
  const saveSettings = useCallback(async (newSettings: Partial<WakeWordConfig>) => {
    const updated = { ...settings, ...newSettings };
    setSettings(updated);
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem('evoloop_wake_word_settings', JSON.stringify(updated));
    } catch (e) {
      console.error('Failed to save wake word settings:', e);
    }
  }, [settings]);

  const toggleWakeWord = useCallback(() => {
    saveSettings({ enabled: !settings.enabled });
  }, [settings.enabled, saveSettings]);

  const setWakeWord = useCallback((word: string) => {
    saveSettings({ wakeWord: word });
  }, [saveSettings]);

  const setThreshold = useCallback((threshold: number) => {
    saveSettings({ threshold });
  }, [saveSettings]);

  return {
    ...settings,
    toggleWakeWord,
    setWakeWord,
    setThreshold,
  };
}
