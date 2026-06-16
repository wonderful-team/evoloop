// 实时音频流录制器 - 使用 react-native-live-audio-stream 实现原生流式录制
import { Buffer } from 'buffer';
import { Platform, PermissionsAndroid, TurboModuleRegistry, DeviceEventEmitter } from 'react-native';
import i18n from '@/locales';

const LiveAudioStream = Platform.OS !== 'harmony' ? require('react-native-live-audio-stream').default : null;

const HarmonyAudioStream = Platform.OS === 'harmony' ? TurboModuleRegistry.get('RNLiveAudioStream') : null;

export interface AudioStreamConfig {
  sampleRate?: number;    // 16000 或 8000
  channelConfig?: number;   // 1 = mono
  audioFormat?: 'pcm' | 'opus';
  chunkSize?: number;      // 每次回调的音频大小
}

export interface AudioStreamCallbacks {
  onAudioChunk?: (chunk: Uint8Array) => void;
  onError?: (error: Error) => void;
  onVolumeChange?: (volume: number) => void;
}

export class AudioStreamRecorder {
  private isRecording: boolean = false;
  private config: AudioStreamConfig;
  private callbacks: AudioStreamCallbacks;

  constructor(config: AudioStreamConfig = {}, callbacks: AudioStreamCallbacks = {}) {
    this.config = {
      sampleRate: 16000,
      channelConfig: 1,
      audioFormat: 'pcm', // 原生库通常直接输出 PCM
      bufferSize: 4096,
      ...config,
    };
    this.callbacks = callbacks;

    // 初始化流
    const options = {
      sampleRate: this.config.sampleRate ?? 16000,
      channels: this.config.channelConfig ?? 1,
      bitsPerSample: 16,
      audioSource: 6, // 语音助手/录音源
      bufferSize: 4096,
    };

    const handleData = (data: string) => {
      // data 是 base64 字符串
      const chunk = Buffer.from(data, 'base64');
      const uint8Array = new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
      
      this.callbacks.onAudioChunk?.(uint8Array);
      
      // 简易音量估算
      if (this.callbacks.onVolumeChange) {
        const volume = this.calculateRMS(uint8Array);
        this.callbacks.onVolumeChange(volume);
      }
    };

    if (Platform.OS === 'harmony') {
      if (HarmonyAudioStream) {
        HarmonyAudioStream.init(options);
        DeviceEventEmitter.addListener('data', handleData);
      }
    } else {
      LiveAudioStream.init(options);
      LiveAudioStream.on('data', handleData);
    }
  }

  // 计算音量 (RMS 模型，带子采样优化以降低 JS CPU 开销)
  private calculateRMS(data: Uint8Array): number {
    let sum = 0;
    let count = 0;
    // 子采样：每 4 个样本采 1 个（步长 8 字节），精度对音量表示足够，速度提升 4 倍
    for (let i = 0; i < data.length; i += 8) {
      const sample = (data[i + 1] << 8) | data[i];
      // 转换为有符号 16bit
      const signedSample = sample >= 0x8000 ? sample - 0x10000 : sample;
      sum += signedSample * signedSample;
      count++;
    }
    const rms = Math.sqrt(sum / (count || 1));
    return Math.min(1, rms / 10000); // 归一化到 0-1
  }

  // 请求权限
  static async requestPermissions(): Promise<boolean> {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO
        );
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn('请求录音权限失败:', err);
        return false;
      }
    }
    return true; // iOS 和 HarmonyOS 在原生层或配置文件中处理
  }

  // 开始录制
  async start(): Promise<void> {
    if (this.isRecording) return;

    try {
      const hasPermission = await AudioStreamRecorder.requestPermissions();
      if (!hasPermission) {
        throw new Error(i18n.t('audio.errors.noPermission'));
      }

      if (Platform.OS === 'harmony') {
        HarmonyAudioStream?.start();
      } else {
        LiveAudioStream.start();
      }
      this.isRecording = true;
      console.log('✅ 原生音频流录制已开始');
    } catch (error) {
      console.error('开始录制失败:', error);
      this.callbacks.onError?.(error as Error);
      throw error;
    }
  }

  // 停止录制
  async stop(): Promise<void> {
    if (!this.isRecording) return;

    try {
      if (Platform.OS === 'harmony') {
        HarmonyAudioStream?.stop();
      } else {
        LiveAudioStream.stop();
      }
      this.isRecording = false;
      console.log('✅ 原生音频流录制已停止');
    } catch (error) {
      console.error('停止录制失败:', error);
      throw error;
    }
  }

  getIsRecording(): boolean {
    return this.isRecording;
  }
}
