// 流式 TTS Hook（双轨版）
// 网络良好  → qwen3-tts-flash（云端，高音质 + 情感）
// 弱网/离线 → Sherpa-ONNX Kokoro-multi-lang-v1_1（本地，< 100ms 首字）
// 路由切换对调用方完全透明，统一通过 enqueue / speak 接口使用

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import RNFS from 'react-native-fs';
import i18n from '@/locales';
import { voiceEngine } from '@/services/voice/VoiceEngine';
import { ttsRouter } from '@/services/voice/TTSRouter';
import { DASHSCOPE_CONFIG } from '@/constants/config';

const DASHSCOPE_TTS_ENDPOINT = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation';
const QWEN_TTS_MAX_TEXT_LENGTH = 800;

export interface TTSOptions {
  voiceId?: string;
  speed?: number;
  emotion?: 'neutral' | 'happy' | 'sad' | 'excited' | 'calm';
  instructions?: string;
}

export interface TTSVoice {
  id: string;
  name: string;
  gender: string;
  description: string;
}

export function getDefaultVoices(t: (key: string) => string): TTSVoice[] {
  return [
    { id: 'Cherry', name: 'Cherry', gender: 'female', description: t('chat.tts.cherryDesc') },
    { id: 'Serena', name: 'Serena', gender: 'female', description: t('chat.tts.serenaDesc') },
  ];
}

export interface UseStreamingTTSOptions {
  onComplete?: () => void;
}

export function useStreamingTTS(options: UseStreamingTTSOptions = {}) {
  const { onComplete } = options;
  const { t } = useTranslation();
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentVoice, setCurrentVoiceState] = useState('Cherry');

  const abortControllerRef = useRef<AbortController | null>(null);
  const queueRef = useRef<Array<{ text: string; options: TTSOptions }>>([]);
  const isProcessingRef = useRef(false);
  const externallyStoppedRef = useRef(false);

  // 持久化音色选择
  useEffect(() => {
    const load = async () => {
      try {
        const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
        const saved = await AsyncStorage.getItem('evoloop_tts_voice');
        if (saved) { setCurrentVoiceState(saved); }
      } catch {}
    };
    load();
  }, []);

  // TTS 播放状态变化时，动态调节 VAD 门限防自激打断
  useEffect(() => {
    // 播放期间调高门限（0.5 → 0.8，等效 +15dB 抑制），结束后恢复
    const threshold = isSpeaking ? 0.8 : 0.5;
    (voiceEngine as any).setVadThreshold?.(threshold).catch(() => {});
  }, [isSpeaking]);

  const setCurrentVoice = useCallback(async (voice: string) => {
    setCurrentVoiceState(voice);
    try {
      const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
      await AsyncStorage.setItem('evoloop_tts_voice', voice);
    } catch {}
  }, []);

  const stop = useCallback(() => {
    externallyStoppedRef.current = true;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    voiceEngine.stopAudio().catch(() => {});
    queueRef.current = [];
    isProcessingRef.current = false;
    setIsSpeaking(false);
    setIsLoading(false);
  }, []);

  // ── 本地文件播放（下载完成后调用，或 Kokoro 合成后调用）──────
  const playLocalFile = useCallback(async (localPath: string): Promise<void> => {
    const base64 = await RNFS.readFile(localPath, 'base64');
    const decodedLength = Math.ceil((base64.length * 3) / 4);
    const durationMs = (decodedLength / (24000 * 2)) * 1000;

    await voiceEngine.startAudioStream('wav', 24000);
    await voiceEngine.writeAudioChunk(base64);

    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => resolve(), Math.max(500, Math.ceil(durationMs)));
      return () => clearTimeout(timer);
    });
  }, []);

  // ── 云端 qwen3-tts-flash 合成并播放（N+1 并发预取） ──────────
  const synthesizeCloud = useCallback(async (text: string, opts: TTSOptions): Promise<void> => {
    if (!text.trim()) { return; }

    const truncated = truncateAtSentenceBoundary(text, QWEN_TTS_MAX_TEXT_LENGTH);
    setIsLoading(true);
    setError(null);

    try {
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const response = await fetch(DASHSCOPE_TTS_ENDPOINT, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${DASHSCOPE_CONFIG.apiKey}`,
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          model: 'qwen3-tts-flash',
          input: {
            text: truncated,
            voice: opts.voiceId || currentVoice,
            language_type: /^(zh|ja|ko)/.test(i18n.language ?? 'zh') ? 'Chinese' : 'English',
          },
          parameters: {
            emotion: opts.emotion || 'neutral',
            speed_ratio: opts.speed ?? 1.0,
          },
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`TTS HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const audioUrls: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) { break; }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) { continue; }
          const data = trimmed.slice(5).trim();
          if (data === '[DONE]') { continue; }

          try {
            const parsed = JSON.parse(data);
            const audioUrl = parsed?.output?.audio?.url;
            if (audioUrl) { audioUrls.push(audioUrl); }
          } catch { /* ignore malformed SSE lines */ }
        }
      }

      if (audioUrls.length === 0) {
        throw new Error(t('chat.tts.apiNoAudioUrl'));
      }

      setIsLoading(false);
      setIsSpeaking(true);

      // ── N+1 并发预取：当前分片播放时，下一分片在后台下载 ──────
      const prefetch = (url: string): Promise<string> => {
        const path = `${RNFS.DocumentDirectoryPath}/tts_${Date.now()}_${Math.random().toString(36).slice(2)}.wav`;
        return RNFS.downloadFile({ fromUrl: url, toFile: path })
          .promise.then(r => {
            if (r.statusCode !== 200) { throw new Error(`dl ${r.statusCode}`); }
            return path;
          });
      };

      let nextDownload: Promise<string> | null = null;

      for (let i = 0; i < audioUrls.length; i++) {
        if (abortControllerRef.current !== controller) { return; }

        // 当前分片：若上一轮已并发预取则直接 await，否则现在下载
        const currentPath = nextDownload
          ? await nextDownload
          : await prefetch(audioUrls[i]);

        // 立即并发启动下一分片的下载
        nextDownload = i + 1 < audioUrls.length ? prefetch(audioUrls[i + 1]) : null;

        // 播放当前分片
        await playLocalFile(currentPath);
        RNFS.unlink(currentPath).catch(() => {});
      }

      setIsSpeaking(false);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') { return; }
      const msg = err instanceof Error ? err.message : t('chat.tts.error');
      setError(msg);
      setIsSpeaking(false);
      setIsLoading(false);
    }
  }, [currentVoice, t, playLocalFile]);

  // ── 本地 Kokoro 合成并播放（弱网/离线路径） ──────────────────
  const synthesizeLocal = useCallback(async (text: string, opts: TTSOptions): Promise<void> => {
    if (!text.trim()) { return; }
    setIsLoading(true);
    try {
      setIsSpeaking(true);
      await ttsRouter.synthesizeLocal(text, opts);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('chat.tts.error');
      setError(msg);
    } finally {
      setIsSpeaking(false);
      setIsLoading(false);
    }
  }, [t]);

  // ── 统一 synthesize 入口：由 TTSRouter 决定走云端还是本地 ────
  const synthesize = useCallback(async (text: string, opts: TTSOptions): Promise<void> => {
    if (ttsRouter.getMode() === 'local') {
      await synthesizeLocal(text, opts);
    } else {
      await synthesizeCloud(text, opts);
    }
  }, [synthesizeCloud, synthesizeLocal]);

  // ── 队列处理器 ────────────────────────────────────────────────
  const processQueue = useCallback(async () => {
    if (isProcessingRef.current || queueRef.current.length === 0) { return; }
    isProcessingRef.current = true;

    const item = queueRef.current.shift();
    try {
      if (item) { await synthesize(item.text, item.options); }
    } catch (e) {
      console.error('[useStreamingTTS] synthesize error:', e);
    } finally {
      isProcessingRef.current = false;
      // 被外部 stop()（如 AutoSpeakHandler.speak）中止时，不清空队列的 onComplete
      // 由 speak() 自己负责在播放完毕后 fire，避免误触发 auto-start
      if (externallyStoppedRef.current) {
        externallyStoppedRef.current = false;
        return;
      }
      if (queueRef.current.length === 0) {
        onComplete?.();
      } else {
        processQueue();
      }
    }
  }, [synthesize, onComplete]);

  const enqueue = useCallback((text: string, opts: TTSOptions = {}) => {
    queueRef.current.push({ text, options: opts });
    processQueue();
  }, [processQueue]);

  const speak = useCallback(async (text: string, opts: TTSOptions = {}) => {
    stop();
    await synthesize(text, opts);
    onComplete?.();
  }, [stop, synthesize, onComplete]);

  /** 预热云端 TTS 的 TCP 连接（在 VAD onVadEnd 时调用，省去首包 TLS 握手延迟）*/
  const prewarm = useCallback(() => {
    if (ttsRouter.getMode() === 'cloud') {
      fetch(DASHSCOPE_TTS_ENDPOINT, {
        method: 'HEAD',
        headers: { Authorization: `Bearer ${DASHSCOPE_CONFIG.apiKey}` },
        keepalive: true,
      }).catch(() => {});
    }
  }, []);

  const clearQueue = useCallback(() => { stop(); }, [stop]);

  return {
    isSpeaking,
    isLoading,
    error,
    currentVoice,
    setCurrentVoice,
    speak,
    enqueue,
    clearQueue,
    stop,
    prewarm,
    ttsMode: ttsRouter.getMode(),
    voices: getDefaultVoices(t),
  };
}

// ── 情感与语速检测（i18n 多语言版） ─────────────────────────────
export function detectEmotionAndSpeed(text: string): TTSOptions {
  const t = text.trim().toLowerCase();
  const isDoubleExclaim = /!!|！！/.test(t);

  const speedMap: Record<string, number> = {
    excited: 1.15,
    happy: 1.05,
    sad: 0.88,
    calm: 0.92,
  };

  for (const emotion of ['excited', 'happy', 'sad', 'calm'] as const) {
    const raw = i18n.t(`voiceNLU.emotionKeywords.${emotion}`) as string;
    if (!raw) { continue; }
    const re = new RegExp(raw, 'i');
    if (re.test(t) || (emotion === 'excited' && isDoubleExclaim)) {
      return { emotion, speed: speedMap[emotion] };
    }
  }

  // 标点辅助：单感叹号 → happy，省略号 → sad
  if (/[!！]/.test(t)) { return { emotion: 'happy', speed: 1.05 }; }
  if (/\.\.\.|。。。/.test(t)) { return { emotion: 'sad', speed: 0.88 }; }

  return { emotion: 'neutral', speed: 1.0 };
}

// ── 内部工具：在句子边界截断超长文本 ─────────────────────────────
function truncateAtSentenceBoundary(text: string, maxLength: number): string {
  if (text.length <= maxLength) { return text; }
  const punctuationRegex = /[。！？.!?；;\n]/;
  let truncateIndex = maxLength;
  for (let i = maxLength; i >= Math.floor(maxLength * 0.7); i--) {
    if (punctuationRegex.test(text[i])) {
      truncateIndex = i + 1;
      break;
    }
  }
  return text.slice(0, truncateIndex).trimEnd() + '...';
}
