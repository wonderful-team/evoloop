// 实时音频流录制器 - 使用 expo-audio-stream 实现真实流式录制

import { AudioModule, RecordingConfig } from 'expo-audio-stream';
import * as FileSystem from 'expo-file-system';

export interface AudioStreamConfig {
  sampleRate?: number;  // 16000 或 8000
  channelConfig?: number; // 1 = mono
  audioFormat?: 'pcm' | 'opus';
  chunkSize?: number;   // 每次回调的音频大小
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
      audioFormat: 'opus', // NLS 推荐 opus，省流量
      chunkSize: 3200,
      ...config,
    };
    this.callbacks = callbacks;
  }

  // 请求权限
  static async requestPermissions(): Promise<boolean> {
    try {
      const { status } = await AudioModule.requestPermissionsAsync();
      console.log('录音权限状态:', status);
      return status === 'granted';
    } catch (error) {
      console.error('请求录音权限失败:', error);
      return false;
    }
  }

  // 开始录制
  async start(): Promise<void> {
    if (this.isRecording) {
      throw new Error('已经在录制中');
    }

    try {
      // 检查权限
      const hasPermission = await AudioStreamRecorder.requestPermissions();
      if (!hasPermission) {
        throw new Error('没有录音权限，请在设置中开启');
      }

      // 配置录音选项
      const recordingConfig: RecordingConfig = {
        sampleRate: this.config.sampleRate!,
        channels: this.config.channelConfig!,
        encoding: this.config.audioFormat === 'opus' ? 'opus' : 'pcm',
        // 关键：启用流式回调
        keepAudioInMemory: false,
        // 每 100ms 回调一次音频数据
        interval: 100,
      };

      console.log('开始录音，配置:', recordingConfig);

      // 开始录音
      await AudioModule.startRecording(recordingConfig);
      this.isRecording = true;

      // 设置音频数据回调
      this.setupAudioCallback();

      console.log('✅ 音频流录制已开始');
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
      const result = await AudioModule.stopRecording();
      this.isRecording = false;
      
      console.log('✅ 音频流录制已停止');
      console.log('录音文件:', result?.fileUri);
      console.log('录音时长:', result?.duration, 'ms');
    } catch (error) {
      console.error('停止录制失败:', error);
      throw error;
    }
  }

  // 设置音频数据回调
  private setupAudioCallback(): void {
    // 监听音频数据 - 这是实时流式的关键
    AudioModule.addListener('onAudioData', (event: { data: string; position: number; }) => {
      // event.data 是 base64 编码的音频数据
      const base64Data = event.data;
      
      // base64 转 Uint8Array
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // 发送给回调（直接发送到 NLS）
      this.callbacks.onAudioChunk?.(bytes);
    });

    // 监听音量变化
    AudioModule.addListener('onVolumeChange', (event: { volume: number }) => {
      // volume 是 0-1 的值
      this.callbacks.onVolumeChange?.(event.volume);
    });
  }

  // 获取录制状态
  getIsRecording(): boolean {
    return this.isRecording;
  }

  // 读取录音文件（如果需要）
  async readRecordingFile(uri: string): Promise<Uint8Array> {
    try {
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      
      // base64 转 Uint8Array
      const binaryString = atob(base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      return bytes;
    } catch (error) {
      console.error('读取录音文件失败:', error);
      throw error;
    }
  }
}

// Mock 实现保留用于测试
export class MockAudioStreamRecorder {
  private isRecording: boolean = false;
  private intervalId: NodeJS.Timeout | null = null;
  private callbacks: AudioStreamCallbacks;

  constructor(config: AudioStreamConfig = {}, callbacks: AudioStreamCallbacks = {}) {
    this.callbacks = callbacks;
  }

  static async requestPermissions(): Promise<boolean> {
    return true;
  }

  async start(): Promise<void> {
    if (this.isRecording) {
      throw new Error('已经在录制中');
    }

    this.isRecording = true;
    
    // 模拟每 200ms 发送一次音频数据
    this.intervalId = setInterval(() => {
      const mockChunk = new Uint8Array(3200);
      for (let i = 0; i < mockChunk.length; i++) {
        mockChunk[i] = Math.floor(Math.random() * 256);
      }
      this.callbacks.onAudioChunk?.(mockChunk);
      
      const mockVolume = Math.sin(Date.now() / 500) * 0.3 + 0.4;
      this.callbacks.onVolumeChange?.(Math.max(0, Math.min(1, mockVolume)));
    }, 200);

    console.log('[Mock] 音频流录制已开始');
  }

  async stop(): Promise<void> {
    if (!this.isRecording) return;

    this.isRecording = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    console.log('[Mock] 音频流录制已停止');
  }

  getIsRecording(): boolean {
    return this.isRecording;
  }
}
