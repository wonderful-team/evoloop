// Native 语音引擎 JS 封装
// 统一封装麦克风采集、VAD、ASR、唤醒词、TTS 音频播放

import {
  NativeModules,
  NativeEventEmitter,
  type EmitterSubscription,
  Platform,
} from 'react-native';
import NativeVoiceEngine from '@/specs/NativeVoiceEngine';
import { voiceEngineHarmony } from './VoiceEngineHarmony';

export type VoiceEngineMode = 'idle' | 'wake' | 'asr';

export interface VoiceEngineConfig {
  modelDir: string;
  wakeWord?: string;
  sampleRate?: number;
  numThreads?: number;
  vadThreshold?: number;
  silenceTimeoutMs?: number;
}

export interface VoiceEngineEventCallbacks {
  onVadStart?: () => void;
  onVadEnd?: () => void;
  onPartial?: (text: string) => void;
  onFinal?: (text: string) => void;
  onWake?: (text: string) => void;
  onVolume?: (value: number) => void;
  onError?: (error: Error) => void;
}

export interface AudioEventCallbacks {
  onEnded?: () => void;
  onError?: (error: Error) => void;
}

class VoiceEngineManager {
  private engine = Platform.OS === 'harmony' ? voiceEngineHarmony : new NativeVoiceEngineWrapper();

  async initialize(config: VoiceEngineConfig): Promise<void> {
    return this.engine.initialize(config);
  }

  start(callbacks: VoiceEngineEventCallbacks): void {
    return this.engine.start(callbacks);
  }

  subscribeAudio(callbacks: AudioEventCallbacks): void {
    return this.engine.subscribeAudio(callbacks);
  }

  async setMode(mode: VoiceEngineMode): Promise<void> {
    return this.engine.setMode(mode);
  }

  async beginSession(): Promise<void> {
    return this.engine.beginSession();
  }

  async endSession(): Promise<void> {
    return this.engine.endSession();
  }

  async release(): Promise<void> {
    return this.engine.release();
  }

  async startAudioStream(format: 'pcm' | 'mp3' | 'wav' = 'mp3', sampleRate = 24000): Promise<void> {
    return this.engine.startAudioStream(format, sampleRate);
  }

  async writeAudioChunk(base64Data: string): Promise<void> {
    return this.engine.writeAudioChunk(base64Data);
  }

  async stopAudio(): Promise<void> {
    return this.engine.stopAudio();
  }

  /**
   * 动态调节 VAD 门限（TTS 播放期间调高防自激剓断）
   * @param value 0.0~1.0，平时 0.5，TTS 播放中 0.8
   */
  async setVadThreshold(value: number): Promise<void> {
    return this.engine.setVadThreshold?.(value);
  }

  /**
   * 本地 Kokoro TTS 合成（Sherpa-ONNX OfflineTts）
   * @param text 要合成的文本
   * @param speakerId Kokoro 音色 ID（kokoro-multi-lang-v1_1）
   * @param speed 语速比例（默认 1.0）
   * @returns 本地 WAV 文件路径
   */
  async synthesizeTTS(text: string, speakerId: number, speed: number): Promise<string> {
    return this.engine.synthesizeTTS?.(text, speakerId, speed) ?? '';
  }
}

class NativeVoiceEngineWrapper {
  private subscriptions: EmitterSubscription[] = [];
  private audioSubscriptions: EmitterSubscription[] = [];
  private isInitialized = false;
  private currentMode: VoiceEngineMode = 'idle';

  async initialize(config: VoiceEngineConfig): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    await NativeVoiceEngine.initialize({
      modelDir: config.modelDir,
      wakeWord: config.wakeWord,
      sampleRate: config.sampleRate ?? 16000,
      numThreads: config.numThreads ?? 2,
      vadThreshold: config.vadThreshold ?? 0.5,
      silenceTimeoutMs: config.silenceTimeoutMs ?? 800,
    });

    this.isInitialized = true;
  }

  start(callbacks: VoiceEngineEventCallbacks): void {
    this.removeListeners();

    const emitter = new NativeEventEmitter(NativeVoiceEngine as any);
    this.subscriptions = [
      emitter.addListener('voiceEngine:vadStart', () => callbacks.onVadStart?.()),
      emitter.addListener('voiceEngine:vadEnd', () => callbacks.onVadEnd?.()),
      emitter.addListener('voiceEngine:partial', (event: { text: string }) =>
        callbacks.onPartial?.(event.text)
      ),
      emitter.addListener('voiceEngine:final', (event: { text: string }) =>
        callbacks.onFinal?.(event.text)
      ),
      emitter.addListener('voiceEngine:wake', (event: { text: string }) =>
        callbacks.onWake?.(event.text)
      ),
      emitter.addListener('voiceEngine:volume', (event: { value: number }) =>
        callbacks.onVolume?.(event.value)
      ),
      emitter.addListener('voiceEngine:error', (event: { message: string }) =>
        callbacks.onError?.(new Error(event.message))
      ),
    ];
  }

  subscribeAudio(callbacks: AudioEventCallbacks): void {
    this.removeAudioListeners();
    const emitter = new NativeEventEmitter(NativeVoiceEngine as any);
    this.audioSubscriptions = [
      emitter.addListener('audio:ended', () => callbacks.onEnded?.()),
      emitter.addListener('audio:error', (event: { message: string }) =>
        callbacks.onError?.(new Error(event.message))
      ),
    ];
  }

  async setMode(mode: VoiceEngineMode): Promise<void> {
    this.currentMode = mode;
    await NativeVoiceEngine.setMode(mode);
  }

  async beginSession(): Promise<void> {
    await NativeVoiceEngine.start();
  }

  async endSession(): Promise<void> {
    await NativeVoiceEngine.stop();
    this.currentMode = 'idle';
  }

  async release(): Promise<void> {
    this.removeListeners();
    this.removeAudioListeners();
    await NativeVoiceEngine.release();
    this.isInitialized = false;
    this.currentMode = 'idle';
  }

  async startAudioStream(format: 'pcm' | 'mp3' | 'wav' = 'mp3', sampleRate = 24000): Promise<void> {
    await NativeVoiceEngine.playAudioStream({
      format,
      sampleRate,
      channels: 1,
    });
  }

  async writeAudioChunk(base64Data: string): Promise<void> {
    await NativeVoiceEngine.writeAudioChunk(base64Data);
  }

  async stopAudio(): Promise<void> {
    await NativeVoiceEngine.stopAudio();
  }

  async setVadThreshold(value: number): Promise<void> {
    // 部分平台可能尚未实现此接口，安全地忓略错误
    try {
      await (NativeVoiceEngine as any).setVadThreshold(value);
    } catch {
      // no-op: 该接口尚未实现时静默失败
    }
  }

  async synthesizeTTS(text: string, speakerId: number, speed: number): Promise<string> {
    try {
      return await (NativeVoiceEngine as any).synthesizeTTS({ text, speakerId, speed });
    } catch (e) {
      console.error('[NativeVoiceEngine] synthesizeTTS failed:', e);
      return '';
    }
  }

  private removeListeners(): void {
    this.subscriptions.forEach((sub) => sub.remove());
    this.subscriptions = [];
  }

  private removeAudioListeners(): void {
    this.audioSubscriptions.forEach((sub) => sub.remove());
    this.audioSubscriptions = [];
  }
}

export const voiceEngine = new VoiceEngineManager();
