// 唤醒词检测 Hook
// 提供唤醒词监听控制和设置管理

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';
import { WakeWordService } from '@/services/voice/WakeWordService';

export interface UseWakeWordOptions {
  onWake?: (detectedWord: string) => void;
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
  const { onWake, onError } = options;

  const [isListening, setIsListening] = useState(false);
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false);
  const serviceRef = useRef<WakeWordService | null>(null);
  const wakeWordDetectedTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 从 settingsStore 读取配置
  const settings = useSettingsStore((state) => state.settings);
  const enabled = settings.wakeWordEnabled;
  const wakeWord = settings.wakeWord;
  const threshold = settings.wakeWordThreshold;
  const vadThreshold = settings.wakeWordVadThreshold;

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
        threshold,
        vadThreshold,
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
  }, [enabled, wakeWord, threshold, vadThreshold, onWake, onError]);

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
  }, [enabled, wakeWord, threshold, vadThreshold]);

  return {
    isListening,
    isWakeWordDetected,
    startListening,
    stopListening,
  };
}

/**
 * 唤醒词设置管理 Hook
 * 统一使用 settingsStore（zustand persist），废弃独立 AsyncStorage
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

  const setThreshold = useCallback(
    (value: number) => {
      setSetting('wakeWordThreshold', value);
    },
    [setSetting]
  );

  const setVadThreshold = useCallback(
    (value: number) => {
      setSetting('wakeWordVadThreshold', value);
    },
    [setSetting]
  );

  return {
    enabled: settings.wakeWordEnabled,
    wakeWord: settings.wakeWord,
    threshold: settings.wakeWordThreshold,
    vadThreshold: settings.wakeWordVadThreshold,
    toggleWakeWord,
    setWakeWord,
    setThreshold,
    setVadThreshold,
  };
}
