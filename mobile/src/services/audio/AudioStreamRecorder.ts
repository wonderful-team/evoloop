// 实时音频流录制器 - 使用 react-native-live-audio-stream 实现原生流式录制
import LiveAudioStream from 'react-native-live-audio-stream';
import { Buffer } from 'buffer';
import { Platform, PermissionsAndroid } from 'react-native';

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
      sampleRate: this.config.sampleRate,
      channels: this.config.channelConfig,
      bitsPerSample: 16,
      audioSource: 6, // 语音助手/录音源
      bufferSize: 4096,
    };

    LiveAudioStream.init(options);

    // 设置回调
    LiveAudioStream.on('data', (data: string) => {
      // data 是 base64 字符串
      const chunk = Buffer.from(data, 'base64');
      const uint8Array = new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
      
      this.callbacks.onAudioChunk?.(uint8Array);
      
      // 简易音量估算
      if (this.callbacks.onVolumeChange) {
        const volume = this.calculateRMS(uint8Array);
        this.callbacks.onVolumeChange(volume);
      }
    });
  }

  // 计算音量 (RMS 模型)
  private calculateRMS(data: Uint8Array): number {
    let sum = 0;
    // 假设是 16bit PCM，每两个字节一个样本
    for (let i = 0; i < data.length; i += 2) {
      const sample = (data[i + 1] << 8) | data[i];
      // 转换为有符号 16bit
      const signedSample = sample >= 0x8000 ? sample - 0x10000 : sample;
      sum += signedSample * signedSample;
    }
    const rms = Math.sqrt(sum / (data.length / 2));
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
    return true; // iOS 通过 Info.plist 处理
  }

  // 开始录制
  async start(): Promise<void> {
    if (this.isRecording) return;

    try {
      const hasPermission = await AudioStreamRecorder.requestPermissions();
      if (!hasPermission) {
        throw new Error('没有录音权限');
      }

      LiveAudioStream.start();
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
      LiveAudioStream.stop();
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
