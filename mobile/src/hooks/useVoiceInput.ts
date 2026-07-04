// 新版语音输入 Hook
// 支持：按住说话、点击说话、唤醒词、连续对话、语音打断、本地意图拦截

import { useCallback, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { voiceEngine, type VoiceEngineEventCallbacks } from '@/services/voice/VoiceEngine';
import { useVoiceSessionStore } from '@/stores/voiceSessionStore';
import { useAuthStore } from '@/stores/authStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { parseLocalIntent, type LocalIntent } from '@/services/voice/localNLU';

export interface UseVoiceInputOptions {
  onFinalResult?: (text: string) => void;
  onError?: (error: Error) => void;
  onWake?: (text: string) => void;
  onInterrupt?: () => void;
  /** 本地意图拦截回调：ASR 识别出控制指令时触发，不转发给 LLM */
  onLocalIntent?: (intent: LocalIntent) => void;
  /** VAD 静音检测结束时回调：用于提前预热 TTS TCP 连接 */
  onVadEndPrewarm?: () => void;
  /** 当前 UI 状态（用于指代消解） */
  uiState?: { isHistoryOpen: boolean };
}

export function useVoiceInput(options: UseVoiceInputOptions = {}) {
  const { onFinalResult, onError, onWake, onInterrupt, onLocalIntent, onVadEndPrewarm, uiState } = options;
  // 使用 ref 保持最新的 uiState 引用，避免 stale closure
  const uiStateRef = useRef(uiState ?? { isHistoryOpen: false });
  useEffect(() => { uiStateRef.current = uiState ?? { isHistoryOpen: false }; }, [uiState]);

  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
  const settings = useSettingsStore((state) => state.settings);
  const wakeWordEnabled = settings.wakeWordEnabled;
  const wakeWord = settings.wakeWord;

  const {
    setState,
    setPartialText,
    appendFinalText,
    clearFinalText,
    setVolume,
    setError,
    setWakeWordMode,
    setContinuousMode,
    setPressed,
  } = useVoiceSessionStore.getState();

  const sessionTextRef = useRef('');
  const isRunningRef = useRef(false);
  const pendingFinalRef = useRef(false);
  const isContinuousRef = useRef(false);

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
      wakeWord,
      sampleRate: 16000,
      numThreads: 2,
      vadThreshold: 0.5,
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
  }, [isLoggedIn, wakeWord, setContinuous]);

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
      setState('speaking');
      setPressed(true);
      // VAD 检测到人声，触发打断 (Barge-in)
      onInterrupt?.();
    },
    onVadEnd: () => {
      setState('recognizing');
      pendingFinalRef.current = true;
      // 用户停止说话瞬间，提前预热云端 TTS 的 TCP/SSL 连接（省去 ~200ms 握手延迟）
      onVadEndPrewarm?.();
    },
    onPartial: (text) => {
      setPartialText(text);
    },
    onFinal: (text) => {
      // ① 本地意图拦截：识别到控制指令则直接执行，不发给云端 LLM
      const intent = parseLocalIntent(text, uiStateRef.current);
      if (intent) {
        onLocalIntent?.(intent);
        // 清空本次录音缓冲，不累积到 sessionText
        clearFinalText();
        sessionTextRef.current = '';
        pendingFinalRef.current = false;
        return;
      }

      // ② 非本地指令：正常累积并发送给云端 LLM
      sessionTextRef.current += (sessionTextRef.current ? ' ' : '') + text;
      appendFinalText(text);
      pendingFinalRef.current = false;

      // VAD 断句后自动发送
      if (!isContinuousRef.current) {
        flushFinal();
      }
    },
    onWake: (text) => {
      onWake?.(text);
      onInterrupt?.();
      voiceEngine.setMode('asr').catch(() => {});
      setState('listening');
      clearFinalText();
      sessionTextRef.current = '';
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

  const start = useCallback(async (mode: 'wake' | 'asr' = 'asr') => {
    console.log(`[useVoiceInput] start called, mode=${mode}, isRunning=${isRunningRef.current}`);
    if (!isLoggedIn) {
      onError?.(new Error('未登录'));
      return;
    }

    if (isRunningRef.current) {
      console.log('[useVoiceInput] already running, stopping first');
      await stop();
    }

    isRunningRef.current = true;
    sessionTextRef.current = '';
    clearFinalText();
    setPartialText('');
    setError(null);

    try {
      voiceEngine.start(callbacksRef.current);
      await voiceEngine.setMode(mode);
      await voiceEngine.beginSession();
      console.log('[useVoiceInput] session started');

      setWakeWordMode(mode === 'wake');
      setState('listening');
    } catch (err) {
      console.error('[useVoiceInput] start session failed:', err);
      isRunningRef.current = false;
      setError(err instanceof Error ? err.message : String(err));
      setState('error');
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }, [isLoggedIn, onError, setState, setWakeWordMode, clearFinalText, setPartialText, setError, stop]);

  const stop = useCallback(async () => {
    if (!isRunningRef.current) {return;}
    isRunningRef.current = false;

    await voiceEngine.endSession();
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
      await start('asr');
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
      await start('asr');
    }
  }, [start, stop]);

  // 启动唤醒词监听
  const startWakeWord = useCallback(async () => {
    if (!wakeWordEnabled) {return;}
    await start('wake');
  }, [start, wakeWordEnabled]);

  return {
    start,
    stop,
    pressIn,
    pressOut,
    toggle,
    setContinuous,
    startWakeWord,
    flushFinal,
    isWakeWordEnabled: wakeWordEnabled,
  };
}
