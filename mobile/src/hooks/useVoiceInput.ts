// 新版语音输入 Hook
// 支持：按住说话、点击说话、连续对话、语音打断、本地意图拦截

import { useCallback, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { voiceEngine, type VoiceEngineEventCallbacks } from '@/services/voice/VoiceEngine';
import { useVoiceSessionStore } from '@/stores/voiceSessionStore';
import { useAuthStore } from '@/stores/authStore';
import i18n from '@/locales';
import { parseLocalIntent, type LocalIntent } from '@/services/voice/localNLU';

export interface UseVoiceInputOptions {
  onFinalResult?: (text: string) => void;
  onError?: (error: Error) => void;
  onInterrupt?: () => void;
  /** 本地意图拦截回调：ASR 识别出控制指令时触发，不转发给 LLM */
  onLocalIntent?: (intent: LocalIntent) => void;
  /** VAD 静音检测结束时回调：用于提前预热 TTS TCP 连接 */
  onVadEndPrewarm?: () => void;
  /** 当前 UI 状态（用于指代消解） */
  uiState?: { isHistoryOpen: boolean };
}

export function useVoiceInput(options: UseVoiceInputOptions = {}) {
  const { onFinalResult, onError, onInterrupt, onLocalIntent, onVadEndPrewarm, uiState } = options;
  // 使用 ref 保持最新的 uiState 引用，避免 stale closure
  const uiStateRef = useRef(uiState ?? { isHistoryOpen: false });
  useEffect(() => { uiStateRef.current = uiState ?? { isHistoryOpen: false }; }, [uiState]);

  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);

  const {
    setState,
    setPartialText,
    appendFinalText,
    clearFinalText,
    setVolume,
    setError,
    setContinuousMode,
    setPressed,
  } = useVoiceSessionStore.getState();

  const sessionTextRef = useRef('');
  const isRunningRef = useRef(false);
  const pendingFinalRef = useRef(false);
  const isContinuousRef = useRef(false);
  const pendingPeriodRef = useRef(false);
  const vadConfirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechConfirmedRef = useRef(false);

  // 连续对话模式设置函数定义前置以在 useEffect 中安全引用
  const setContinuous = useCallback((enabled: boolean) => {
    isContinuousRef.current = enabled;
    setContinuousMode(enabled);
  }, [setContinuousMode]);

  // 初始化
  useEffect(() => {
    console.log('[useVoiceInput] init effect, isLoggedIn:', isLoggedIn);
    if (!isLoggedIn) {return;}

    console.log('[useVoiceInput] calling voiceEngine.initialize');
    voiceEngine.initialize({
      modelDir: 'sherpa-asr/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23',
      sampleRate: 16000,
      numThreads: 2,
      vadThreshold: 0.7,
      energyThreshold: 0.02,
      silenceTimeoutMs: 800,
    }).then(() => {
      console.log('[useVoiceInput] initialize done');
    }).catch((err) => {
      console.error('[useVoiceInput] initialize failed:', err);
    });

    // 从 AsyncStorage 读取本地连续对话设置并初始化
    const loadVoiceSettings = async () => {
      try {
        const val = await AsyncStorage.getItem('voice_settings');
        if (val) {
          const parsed = JSON.parse(val);
          if (parsed && typeof parsed.continuousListening === 'boolean') {
            setContinuous(parsed.continuousListening);
          }
        }
      } catch {}
    };
    loadVoiceSettings();

    return () => {
      voiceEngine.release().catch(() => {});
    };
  }, [isLoggedIn, setContinuous]);

  const flushFinal = useCallback(() => {
    const text = sessionTextRef.current.trim();
    if (text) {
      onFinalResult?.(text);
    }
    sessionTextRef.current = '';
    clearFinalText();
  }, [onFinalResult, clearFinalText]);

  const callbacksRef = useRef<VoiceEngineEventCallbacks>({});
  callbacksRef.current = {
    onVadStart: () => {
      if (!isRunningRef.current) return;
      // 噪音抑制：VAD 激活后等 150ms 确认真是人声再改变状态
      if (!speechConfirmedRef.current) {
        if (vadConfirmTimerRef.current) return;
        vadConfirmTimerRef.current = setTimeout(() => {
          vadConfirmTimerRef.current = null;
          speechConfirmedRef.current = true;
          if (!isRunningRef.current) return;
          setState('speaking');
          onInterrupt?.();
        }, 150);
        return;
      }
      setState('speaking');
      onInterrupt?.();
    },
    onVadEnd: () => {
      if (!isRunningRef.current) return;
      // 尚未确认的语音（<150ms 瞬态噪音）直接忽略
      if (!speechConfirmedRef.current) {
        if (vadConfirmTimerRef.current) {
          clearTimeout(vadConfirmTimerRef.current);
          vadConfirmTimerRef.current = null;
        }
        return;
      }
      setState('recognizing');
      pendingFinalRef.current = true;
      pendingPeriodRef.current = true;
      onVadEndPrewarm?.();
    },
    onPartial: (text) => {
      // 语音未确认前不展示转写文字（过滤噪音导致的伪识别）
      if (!speechConfirmedRef.current && !pendingFinalRef.current) return;
      setPartialText(text);
    },
    onFinal: (text) => {
      // 未经过 onVadEnd 的 final 结果（噪音瞬态残留）直接丢弃
      if (!pendingFinalRef.current) {
        return;
      }

      // ① 本地意图拦截：识别到控制指令则直接执行，不发给云端 LLM
      const intent = parseLocalIntent(text, uiStateRef.current);
      if (intent) {
        onLocalIntent?.(intent);
        clearFinalText();
        sessionTextRef.current = '';
        pendingFinalRef.current = false;
        return;
      }

      // ② 非本地指令：累积到 sessionText，但不自动发送
      let prefix = '';
      if (pendingPeriodRef.current && sessionTextRef.current) {
        prefix = '，';
      }
      pendingPeriodRef.current = false;
      sessionTextRef.current += prefix + text;
      appendFinalText(text);
      pendingFinalRef.current = false;
    },
    onVolume: (value) => {
      setVolume(value);
    },
    onError: (error) => {
      setError(error.message);
      setState('error');
      onError?.(error);
    },
  };

  const start = useCallback(async () => {
    console.log(`[useVoiceInput] start called, isRunning=${isRunningRef.current}`);
    if (!isLoggedIn) {
      onError?.(new Error(i18n.t('auth.errors.notLoggedIn')));
      return;
    }

    if (isRunningRef.current) {
      console.log('[useVoiceInput] already running, stopping first');
      await stop();
    }

    if (vadConfirmTimerRef.current) {
      clearTimeout(vadConfirmTimerRef.current);
      vadConfirmTimerRef.current = null;
    }
    speechConfirmedRef.current = false;
    isRunningRef.current = true;
    sessionTextRef.current = '';
    pendingPeriodRef.current = false;
    clearFinalText();
    setPartialText('');
    setError(null);

    try {
      voiceEngine.start(callbacksRef.current);
      await voiceEngine.setMode('asr');
      await voiceEngine.beginSession();

      // stop() 可能在 await 期间被调用，检查是否仍然有效
      if (!isRunningRef.current) {
        console.log('[useVoiceInput] start cancelled by stop');
        return;
      }

      console.log('[useVoiceInput] session started');
      setState('listening');
    } catch (err) {
      console.error('[useVoiceInput] start session failed:', err);
      isRunningRef.current = false;
      setError(err instanceof Error ? err.message : String(err));
      setState('error');
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }, [isLoggedIn, onError, setState, clearFinalText, setPartialText, setError, stop]);

  const stop = useCallback(async () => {
    if (!isRunningRef.current) {return;}
    // 清理噪音抑制状态
    if (vadConfirmTimerRef.current) {
      clearTimeout(vadConfirmTimerRef.current);
      vadConfirmTimerRef.current = null;
    }
    speechConfirmedRef.current = false;
    isRunningRef.current = false;

    try {
      // 5s timeout: native endSession 可能因音频回调未触发而挂起
      await Promise.race([
        voiceEngine.endSession(),
        new Promise<void>((resolve) => setTimeout(resolve, 5000)),
      ]);
    } catch (err) {
      console.error('[useVoiceInput] endSession error:', err);
    }
    // Wait a short time to let any trailing ASR events cross the React Native bridge and process in JS
    await new Promise((resolve) => setTimeout(resolve, 150));
    flushFinal();
    setPartialText('');
    setState('idle');
    setPressed(false);
  }, [flushFinal, setState, setPressed, setPartialText]);

  const pressIn = useCallback(async () => {
    console.log('[useVoiceInput] pressIn called');
    setPressed(true);
    try {
      await start();
      console.log('[useVoiceInput] pressIn start completed');
    } catch (err) {
      console.error('[useVoiceInput] pressIn start failed:', err);
      setPressed(false);
    }
  }, [start, setPressed]);

  const pressOut = useCallback(async () => {
    console.log('[useVoiceInput] pressOut called');
    setPressed(false);
    try {
      await stop();
    } catch (err) {
      console.error('[useVoiceInput] pressOut stop failed:', err);
    }
  }, [stop, setPressed]);

  // 点击说话：点一下开始，再点一下结束
  const toggle = useCallback(async () => {
    if (isRunningRef.current) {
      await stop();
    } else {
      await start();
    }
  }, [start, stop]);

  return {
    start,
    stop,
    pressIn,
    pressOut,
    toggle,
    setContinuous,
    flushFinal,
  };
}
