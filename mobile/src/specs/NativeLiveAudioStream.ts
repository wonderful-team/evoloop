import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

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

export default TurboModuleRegistry.getEnforcing<Spec>('RNLiveAudioStream');
