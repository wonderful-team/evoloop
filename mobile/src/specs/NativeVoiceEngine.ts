import type { TurboModule } from 'react-native';
import { TurboModuleRegistry, NativeModules, Platform } from 'react-native';

export type VoiceEngineMode = 'idle' | 'asr';

export interface Spec extends TurboModule {
  // === ASR ===
  initialize(config: {
    modelDir: string;
    sampleRate?: number;
    numThreads?: number;
    vadThreshold?: number;
    silenceTimeoutMs?: number;
  }): Promise<void>;

  setMode(mode: VoiceEngineMode): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  release(): Promise<void>;

  // === TTS / Audio ===
  /** 原生层播放 PCM/MP3 流，支持鸿蒙 */
  playAudioStream(config: {
    sampleRate?: number;
    channels?: number;
    format: 'pcm' | 'mp3' | 'wav';
  }): Promise<void>;

  /** 向播放流写入音频数据 */
  writeAudioChunk(base64Data: string): Promise<void>;

  /** 停止播放 */
  stopAudio(): Promise<void>;

  /** 动态更新 VAD 检测门限 */
  setVadThreshold(value: number): Promise<void>;

  /** 本地 Kokoro TTS 合成 */
  synthesizeTTS(params: { text: string; speakerId: number; speed: number }): Promise<string>;

  // 事件：
  // voiceEngine:vadStart
  // voiceEngine:vadEnd
  // voiceEngine:partial { text }
  // voiceEngine:final { text }
  // voiceEngine:error { message }
  // voiceEngine:volume { value }
  // audio:ended
  // audio:error { message }
}

const isTurboModule = !!(global as any).__turboModuleProxy;

export default (Platform.OS !== 'harmony' && isTurboModule
  ? TurboModuleRegistry.getEnforcing<Spec>('RNVoiceEngine')
  : NativeModules.RNVoiceEngine) as Spec;
