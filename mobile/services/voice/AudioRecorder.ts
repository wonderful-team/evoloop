// 音频录制服务

import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';
import { AUDIO_CONFIG } from '@/constants/config';

export type RecordingStatus = 'idle' | 'recording' | 'paused' | 'stopping';

export interface RecordingConfig {
  sampleRate?: number;
  channels?: number;
  bitDepth?: number;
  maxDuration?: number;
}

export class AudioRecorder {
  private recording: Audio.Recording | null = null;
  private status: RecordingStatus = 'idle';
  private recordingUri: string | null = null;
  private onDataAvailable?: (base64Data: string) => void;
  private recordingTimer: NodeJS.Timeout | null = null;
  private chunkInterval = 200; // 每 200ms 发送一次数据

  // 获取当前状态
  getStatus(): RecordingStatus {
    return this.status;
  }

  // 请求录音权限
  static async requestPermissions(): Promise<boolean> {
    const { status } = await Audio.requestPermissionsAsync();
    return status === 'granted';
  }

  // 检查权限
  static async checkPermissions(): Promise<boolean> {
    const { status } = await Audio.getPermissionsAsync();
    return status === 'granted';
  }

  // 初始化录音
  async initialize(config?: RecordingConfig): Promise<void> {
    try {
      // 设置音频模式
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: true,
        shouldDuckAndroid: true,
      });

      // 创建录音实例
      const { recording } = await Audio.Recording.createAsync(
        {
          android: {
            extension: '.m4a',
            outputFormat: Audio.AndroidOutputFormat.MPEG_4,
            audioEncoder: Audio.AndroidAudioEncoder.AAC,
            sampleRate: config?.sampleRate || AUDIO_CONFIG.sampleRate,
            numberOfChannels: config?.channels || AUDIO_CONFIG.channels,
            bitRate: 128000,
          },
          ios: {
            extension: '.m4a',
            audioQuality: Audio.IOSAudioQuality.HIGH,
            sampleRate: config?.sampleRate || AUDIO_CONFIG.sampleRate,
            numberOfChannels: config?.channels || AUDIO_CONFIG.channels,
            bitRate: 128000,
            linearPCMBitDepth: config?.bitDepth || AUDIO_CONFIG.bitDepth,
            linearPCMIsBigEndian: false,
            linearPCMIsFloat: false,
          },
        },
        (status) => this.onRecordingStatusUpdate(status),
        this.chunkInterval
      );

      this.recording = recording;
      this.status = 'idle';
    } catch (error) {
      console.error('初始化录音失败:', error);
      throw error;
    }
  }

  // 开始录音
  async start(onDataAvailable?: (base64Data: string) => void): Promise<void> {
    if (!this.recording) {
      await this.initialize();
    }

    if (!this.recording) {
      throw new Error('录音实例未创建');
    }

    try {
      this.onDataAvailable = onDataAvailable;
      await this.recording.startAsync();
      this.status = 'recording';
      
      // 启动定时器发送音频数据
      if (onDataAvailable) {
        this.startChunkTimer();
      }
    } catch (error) {
      console.error('开始录音失败:', error);
      throw error;
    }
  }

  // 停止录音
  async stop(): Promise<string | null> {
    if (!this.recording) {
      return null;
    }

    try {
      this.status = 'stopping';
      this.stopChunkTimer();

      await this.recording.stopAndUnloadAsync();
      const uri = this.recording.getURI();
      this.recordingUri = uri;
      this.status = 'idle';

      // 清理
      this.recording = null;

      return uri;
    } catch (error) {
      console.error('停止录音失败:', error);
      throw error;
    }
  }

  // 暂停录音
  async pause(): Promise<void> {
    if (!this.recording || this.status !== 'recording') {
      return;
    }

    try {
      await this.recording.pauseAsync();
      this.status = 'paused';
      this.stopChunkTimer();
    } catch (error) {
      console.error('暂停录音失败:', error);
      throw error;
    }
  }

  // 恢复录音
  async resume(): Promise<void> {
    if (!this.recording || this.status !== 'paused') {
      return;
    }

    try {
      await this.recording.startAsync(); // expo-av 使用 startAsync 恢复
      this.status = 'recording';
      
      if (this.onDataAvailable) {
        this.startChunkTimer();
      }
    } catch (error) {
      console.error('恢复录音失败:', error);
      throw error;
    }
  }

  // 获取录音时长（毫秒）
  async getDuration(): Promise<number> {
    if (!this.recording) {
      return 0;
    }

    const status = await this.recording.getStatusAsync();
    return status.durationMillis || 0;
  }

  // 获取录音音量（0-1）
  async getVolume(): Promise<number> {
    if (!this.recording || this.status !== 'recording') {
      return 0;
    }

    const status = await this.recording.getStatusAsync();
    // @ts-ignore - metering 属性可能存在
    const metering = status.metering || -160;
    // 将分贝转换为 0-1 的范围
    const volume = Math.max(0, Math.min(1, (metering + 160) / 160));
    return volume;
  }

  // 释放资源
  async cleanup(): Promise<void> {
    this.stopChunkTimer();

    if (this.recording) {
      try {
        await this.recording.stopAndUnloadAsync();
      } catch (error) {
        // 忽略停止错误
      }
      this.recording = null;
    }

    this.status = 'idle';
    this.recordingUri = null;
  }

  // 读取录音文件为 base64
  async readAudioFile(uri: string): Promise<string> {
    try {
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      return base64;
    } catch (error) {
      console.error('读取音频文件失败:', error);
      throw error;
    }
  }

  // 删除录音文件
  async deleteAudioFile(uri?: string): Promise<void> {
    const fileUri = uri || this.recordingUri;
    if (!fileUri) return;

    try {
      const info = await FileSystem.getInfoAsync(fileUri);
      if (info.exists) {
        await FileSystem.deleteAsync(fileUri);
      }
    } catch (error) {
      console.error('删除音频文件失败:', error);
    }
  }

  // 录音状态更新回调
  private onRecordingStatusUpdate(status: Audio.RecordingStatus) {
    // 可以在这里处理录音状态更新
    // console.log('录音状态:', status);
  }

  // 启动分块定时器
  private startChunkTimer() {
    // 注意：expo-av 目前不支持实时获取录音数据块
    // 这里是一个预留的接口，实际实现可能需要使用原生模块
    // 或者通过其他方式（如 WebSocket 发送整段音频）
  }

  // 停止分块定时器
  private stopChunkTimer() {
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
      this.recordingTimer = null;
    }
  }
}

// 单例实例
let instance: AudioRecorder | null = null;

export function getAudioRecorder(): AudioRecorder {
  if (!instance) {
    instance = new AudioRecorder();
  }
  return instance;
}
