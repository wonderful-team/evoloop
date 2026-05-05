import {
  NativeModules,
  NativeEventEmitter,
  type EmitterSubscription,
} from 'react-native';

interface SherpaOnnxASRNativeModule {
  init(config: Record<string, unknown>): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  release(): Promise<void>;
}

const { SherpaOnnxASR } = NativeModules as { SherpaOnnxASR?: SherpaOnnxASRNativeModule };

if (!SherpaOnnxASR) {
  console.warn('[SherpaOnnxASR] Native module not found. Is the native code linked?');
}

const asrEmitter = SherpaOnnxASR ? new NativeEventEmitter(SherpaOnnxASR as any) : null;

export interface SherpaAsrConfig {
  modelDir: string;
  numThreads?: number;
}

export interface AsrResultEvent {
  text: string;
}

class SherpaOnnxASRManager {
  private subscription: EmitterSubscription | null = null;

  async initialize(config: SherpaAsrConfig): Promise<void> {
    if (!SherpaOnnxASR) {
      throw new Error('SherpaOnnxASR native module not available');
    }
    return SherpaOnnxASR.init({
      modelDir: config.modelDir,
      numThreads: config.numThreads ?? 2,
    });
  }

  async start(): Promise<void> {
    if (!SherpaOnnxASR) {
      throw new Error('SherpaOnnxASR native module not available');
    }
    return SherpaOnnxASR.start();
  }

  async stop(): Promise<void> {
    if (!SherpaOnnxASR) {
      return;
    }
    return SherpaOnnxASR.stop();
  }

  async release(): Promise<void> {
    if (!SherpaOnnxASR) {
      return;
    }
    this.removeListener();
    return SherpaOnnxASR.release();
  }

  onAsrResult(callback: (event: AsrResultEvent) => void): void {
    this.removeListener();
    if (!asrEmitter) {
      console.warn('[SherpaOnnxASR] Cannot listen: emitter not available');
      return;
    }
    this.subscription = asrEmitter.addListener(
      'onAsrResult',
      (event: AsrResultEvent) => {
        callback(event);
      }
    );
  }

  onError(callback: (error: { message: string }) => void): void {
    if (!asrEmitter) {
      console.warn('[SherpaOnnxASR] Cannot listen: emitter not available');
      return;
    }
    asrEmitter.addListener('onError', (event: { message: string }) => {
      callback(event);
    });
  }

  removeListener(): void {
    if (this.subscription) {
      this.subscription.remove();
      this.subscription = null;
    }
  }
}

export const sherpaOnnxASR = new SherpaOnnxASRManager();
