// 鸿蒙语音引擎适配器
// 现在使用本地 Sherpa-ONNX ASR，不再走 NLS 云端识别

import {
  NativeEventEmitter,
  type EmitterSubscription,
} from 'react-native';
import NativeVoiceEngine from '@/specs/NativeVoiceEngine';
import type { VoiceEngineEventCallbacks, AudioEventCallbacks, VoiceEngineConfig } from './VoiceEngine';

export type VoiceEngineMode = 'idle' | 'asr';

class VoiceEngineHarmonyAdapter {
  private subscriptions: EmitterSubscription[] = [];
  private audioSubscriptions: EmitterSubscription[] = [];
  private isRunning = false;
  private currentMode: VoiceEngineMode = 'idle';
  private callbacks: VoiceEngineEventCallbacks | null = null;

  async initialize(config: VoiceEngineConfig): Promise<void> {
    console.log('[VoiceEngineHarmony] initialize called with modelDir:', config.modelDir);
    await NativeVoiceEngine.initialize({
      modelDir: config.modelDir,
      sampleRate: config.sampleRate ?? 16000,
      numThreads: config.numThreads ?? 2,
      vadThreshold: config.vadThreshold ?? 0.5,
      silenceTimeoutMs: config.silenceTimeoutMs ?? 800,
    });
    console.log('[VoiceEngineHarmony] initialize done');
  }

  start(callbacks: VoiceEngineEventCallbacks): void {
    console.log('[VoiceEngineHarmony] start called, setting up listeners');
    this.callbacks = callbacks;
    this.removeListeners();
    const emitter = new NativeEventEmitter();
    this.subscriptions = [
      emitter.addListener('voiceEngine:vadStart', () => {
        callbacks.onVadStart?.();
      }),
      emitter.addListener('voiceEngine:vadEnd', () => {
        callbacks.onVadEnd?.();
      }),
      emitter.addListener('voiceEngine:partial', (event: { text: string }) => {
        console.log('[VoiceEngineHarmony] partial event:', event?.text);
        callbacks.onPartial?.(event.text);
      }),
      emitter.addListener('voiceEngine:final', (event: { text: string }) => {
        console.log('[VoiceEngineHarmony] final event:', event?.text);
        callbacks.onFinal?.(event.text);
      }),
      emitter.addListener('voiceEngine:volume', (event: { value: number }) => {
        callbacks.onVolume?.(event.value);
      }),
      emitter.addListener('voiceEngine:error', (event: { message: string }) => {
        callbacks.onError?.(new Error(event.message));
      }),
    ];
  }

  subscribeAudio(callbacks: AudioEventCallbacks): void {
    this.removeAudioListeners();
    const emitter = new NativeEventEmitter();
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
    if (this.currentMode === 'idle') {return;}
    this.isRunning = true;
    console.log('[VoiceEngineHarmony] beginSession calling NativeVoiceEngine.start()');
    await NativeVoiceEngine.start();
    console.log('[VoiceEngineHarmony] beginSession done');
  }

  async endSession(): Promise<void> {
    this.isRunning = false;
    console.log('[VoiceEngineHarmony] endSession calling NativeVoiceEngine.stop()');
    await NativeVoiceEngine.stop();
    console.log('[VoiceEngineHarmony] endSession done');
  }

  async release(): Promise<void> {
    this.removeListeners();
    this.removeAudioListeners();
    await this.endSession();
    await NativeVoiceEngine.release();
  }

  async startAudioStream(format: 'pcm' | 'mp3' | 'wav' = 'mp3', sampleRate = 24000): Promise<void> {
    await NativeVoiceEngine.playAudioStream({ format, sampleRate, channels: 1 });
  }

  async writeAudioChunk(base64Data: string): Promise<void> {
    await NativeVoiceEngine.writeAudioChunk(base64Data);
  }

  async stopAudio(): Promise<void> {
    await NativeVoiceEngine.stopAudio();
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

export const voiceEngineHarmony = new VoiceEngineHarmonyAdapter();
