// 唤醒词检测 Hook
// 提供唤醒词监听控制和设置管理

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';
import { WakeWordService } from '@/services/voice/WakeWordService';

export interface UseWakeWordOptions {
  onWake?: (detectedWord: string) => void;
  onSpeechDetected?: (text: string) => void;
  onError?: (error: Error) => void;
}

export interface UseWakeWordReturn {
  isListening: boolean;
  isWakeWordDetected: boolean;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
}

/**
 * 唤醒词检测 Hook
 * 自动根据 settingsStore 中的 enabled 状态启动/停止监听
 */
export function useWakeWord(options: UseWakeWordOptions = {}): UseWakeWordReturn {
  const { onWake, onSpeechDetected, onError } = options;

  const [isListening, setIsListening] = useState(false);
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false);
  const serviceRef = useRef<WakeWordService | null>(null);
  const wakeWordDetectedTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 从 settingsStore 读取配置
  const settings = useSettingsStore((state) => state.settings);
  const enabled = settings.wakeWordEnabled;
  const wakeWord = settings.wakeWord;

  const startListening = useCallback(async () => {
    if (!enabled) {
      return;
    }

    // 如果已有服务在运行，先停止它（确保新配置生效）
    if (serviceRef.current) {
      try {
        await serviceRef.current.stop();
      } catch (e) {
        // 忽略停止错误（可能正在停止中）
      }
      serviceRef.current = null;
    }

    try {
      const service = new WakeWordService({
        wakeWord,
        onWake: (text) => {
          setIsWakeWordDetected(true);
          onWake?.(text);

          // 3 秒后自动重置检测状态
          if (wakeWordDetectedTimerRef.current) {
            clearTimeout(wakeWordDetectedTimerRef.current);
          }
          wakeWordDetectedTimerRef.current = setTimeout(() => {
            setIsWakeWordDetected(false);
          }, 3000);
        },
        onSpeechDetected: (text) => {
          onSpeechDetected?.(text);
        },
        onError: (error) => {
          console.error('[useWakeWord] 检测错误:', error);
          onError?.(error);
        },
      });

      await service.start();
      serviceRef.current = service;
      setIsListening(true);
      console.log('[useWakeWord] 监听已启动');
    } catch (error) {
      console.error('[useWakeWord] 启动监听失败:', error);
      onError?.(error as Error);
    }
  }, [enabled, wakeWord, onWake, onSpeechDetected, onError]);

  const stopListening = useCallback(async () => {
    try {
      await serviceRef.current?.stop();
      serviceRef.current = null;
      setIsListening(false);
      setIsWakeWordDetected(false);
      console.log('[useWakeWord] 监听已停止');
    } catch (error) {
      console.error('[useWakeWord] 停止监听失败:', error);
    }
  }, []);

  // 当 enabled 状态变化时自动启动/停止
  useEffect(() => {
    if (enabled) {
      startListening();
    } else {
      stopListening();
    }

    return () => {
      stopListening();
      if (wakeWordDetectedTimerRef.current) {
        clearTimeout(wakeWordDetectedTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, wakeWord]);

  return {
    isListening,
    isWakeWordDetected,
    startListening,
    stopListening,
  };
}

/**
 * 唤醒词设置管理 Hook
 * 统一使用 settingsStore（zustand persist）
 */
export function useWakeWordSettings() {
  const settings = useSettingsStore((state) => state.settings);
  const setSetting = useSettingsStore((state) => state.setSetting);

  const toggleWakeWord = useCallback(() => {
    setSetting('wakeWordEnabled', !settings.wakeWordEnabled);
  }, [settings.wakeWordEnabled, setSetting]);

  const setWakeWord = useCallback(
    (word: string) => {
      setSetting('wakeWord', word);
    },
    [setSetting]
  );

  return {
    enabled: settings.wakeWordEnabled,
    wakeWord: settings.wakeWord,
    toggleWakeWord,
    setWakeWord,
  };
}
