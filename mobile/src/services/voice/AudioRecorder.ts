import { Platform, PermissionsAndroid } from 'react-native';
import AudioRecorderPlayer, {
  AudioEncoderAndroidType,
  AudioSourceAndroidType,
  AVEncoderAudioQualityIOSType,
  AVEncodingOption,
} from 'react-native-audio-recorder-player';
import { check, request, PERMISSIONS, RESULTS } from 'react-native-permissions';
import RNFS from 'react-native-fs';
import { AUDIO_CONFIG } from '@/constants/config';

export type RecordingStatus = 'idle' | 'recording' | 'paused' | 'stopping';

export interface RecordingConfig {
  sampleRate?: number;
  channels?: number;
  bitDepth?: number;
  maxDuration?: number;
}

const audioRecorderPlayer = new AudioRecorderPlayer();

export class AudioRecorder {
  private status: RecordingStatus = 'idle';
  private recordingUri: string | null = null;
  private onDataAvailable?: (base64Data: string) => void;

  // 获取当前状态
  getStatus(): RecordingStatus {
    return this.status;
  }

  // 请求录音权限
  static async requestPermissions(): Promise<boolean> {
    if (Platform.OS === 'android') {
      try {
        const grants = await PermissionsAndroid.requestMultiple([
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          PermissionsAndroid.PERMISSIONS.WRITE_EXTERNAL_STORAGE,
          PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE,
        ]);

        if (
          grants['android.permission.RECORD_AUDIO'] === PermissionsAndroid.RESULTS.GRANTED
        ) {
          return true;
        }
        return false;
      } catch (err) {
        console.warn(err);
        return false;
      }
    } else if (Platform.OS === 'harmony') {
      const harmonyPermissions = (PERMISSIONS as any).HARMONY;
      if (harmonyPermissions && harmonyPermissions.MICROPHONE) {
        const res = await request(harmonyPermissions.MICROPHONE);
        return res === RESULTS.GRANTED;
      }
      return false;
    } else {
      const res = await request(PERMISSIONS.IOS.MICROPHONE);
      return res === RESULTS.GRANTED;
    }
  }

  // 检查权限
  static async checkPermissions(): Promise<boolean> {
    if (Platform.OS === 'android') {
      const hasPermission = await PermissionsAndroid.check(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      );
      return hasPermission;
    } else if (Platform.OS === 'harmony') {
      const harmonyPermissions = (PERMISSIONS as any).HARMONY;
      if (harmonyPermissions && harmonyPermissions.MICROPHONE) {
        const res = await check(harmonyPermissions.MICROPHONE);
        return res === RESULTS.GRANTED;
      }
      return false;
    } else {
      const res = await check(PERMISSIONS.IOS.MICROPHONE);
      return res === RESULTS.GRANTED;
    }
  }

  // 初始化录音 (原生库通常根据开始录音时的参数自动初始化)
  async initialize(config?: RecordingConfig): Promise<void> {
    this.status = 'idle';
  }

  // 开始录音
  async start(onDataAvailable?: (base64Data: string) => void): Promise<void> {
    try {
      this.onDataAvailable = onDataAvailable;
      
      const path = Platform.select({
        ios: 'hello.m4a',
        android: `${RNFS.CachesDirectoryPath}/hello.mp4`, // Android 建议使用 mp4 包装 aac
        harmony: `${RNFS.CachesDirectoryPath}/hello.mp4`,
      });

      const audioSet = {
        AudioEncoderAndroid: AudioEncoderAndroidType.AAC,
        AudioSourceAndroid: AudioSourceAndroidType.MIC,
        AVEncoderAudioQualityKeyIOS: AVEncoderAudioQualityIOSType.high,
        AVNumberOfChannelsKeyIOS: 2,
        AVFormatIDKeyIOS: AVEncodingOption.aac,
      };

      const uri = await audioRecorderPlayer.startRecorder(path, audioSet);
      this.recordingUri = uri;
      this.status = 'recording';

      audioRecorderPlayer.addRecorderBackListener((e) => {
        // 这里可以处理进度更新，音量测量等
        // e.currentPosition, e.isRecording, etc.
      });

      console.log(`开始录制: ${uri}`);
    } catch (error) {
      console.error('开始录音失败:', error);
      throw error;
    }
  }

  // 停止录音
  async stop(): Promise<string | null> {
    try {
      this.status = 'stopping';
      const result = await audioRecorderPlayer.stopRecorder();
      audioRecorderPlayer.removeRecorderBackListener();
      
      this.status = 'idle';
      const uri = this.recordingUri;
      console.log(`停止录制: ${result}`);
      return uri;
    } catch (error) {
      console.error('停止录音失败:', error);
      throw error;
    }
  }

  // 暂停录音
  async pause(): Promise<void> {
    try {
      await audioRecorderPlayer.pauseRecorder();
      this.status = 'paused';
    } catch (error) {
      console.error('暂停录音失败:', error);
      throw error;
    }
  }

  // 恢复录音
  async resume(): Promise<void> {
    try {
      await audioRecorderPlayer.resumeRecorder();
      this.status = 'recording';
    } catch (error) {
      console.error('恢复录音失败:', error);
      throw error;
    }
  }

  // 获取录音时长 (通常从监听器或停止结果中获取)
  async getDuration(): Promise<number> {
    // 简化实现
    return 0;
  }

  // 获取录音音量 (0-1)
  async getVolume(): Promise<number> {
    // react-native-audio-recorder-player 的音量测量可能需要特定逻辑
    return 0.5; // 占位
  }

  // 释放资源
  async cleanup(): Promise<void> {
    try {
      await audioRecorderPlayer.stopRecorder();
      audioRecorderPlayer.removeRecorderBackListener();
    } catch (e) {}
    this.status = 'idle';
  }

  // 读取录音文件为 base64
  async readAudioFile(uri: string): Promise<string> {
    try {
      // 去掉 file:// 前缀
      const filePath = uri.replace('file://', '');
      const base64 = await RNFS.readFile(filePath, 'base64');
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
      const filePath = fileUri.replace('file://', '');
      const exists = await RNFS.exists(filePath);
      if (exists) {
        await RNFS.unlink(filePath);
      }
    } catch (error) {
      console.error('删除音频文件失败:', error);
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
