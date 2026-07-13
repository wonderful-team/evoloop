import type { TurboModule } from 'react-native';
import { TurboModuleRegistry, NativeModules, Platform } from 'react-native';

export interface Spec extends TurboModule {
  init(options: {
    sampleRate: number;
    channels: number;
    bitsPerSample: number;
    audioSource: number;
    bufferSize: number;
  }): void;
  start(): void;
  stop(): void;
}

const isTurboModule = !!(global as any).__turboModuleProxy;

export default (Platform.OS !== 'harmony' && isTurboModule
  ? TurboModuleRegistry.getEnforcing<Spec>('RNLiveAudioStream')
  : NativeModules.RNLiveAudioStream) as Spec;
