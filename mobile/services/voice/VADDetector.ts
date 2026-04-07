// VAD (Voice Activity Detection) 检测器

import { Audio } from 'expo-av';

export interface VADConfig {
  // 音量阈值 (0-1)，超过此值认为是语音
  threshold?: number;
  // 静音持续时间（毫秒），超过此值认为语音结束
  silenceTimeout?: number;
  // 最小语音持续时间（毫秒），少于此值认为是噪音
  minSpeechDuration?: number;
  // 最大语音持续时间（毫秒），超过此值强制停止
  maxSpeechDuration?: number;
}

export type VADState = 'idle' | 'speaking' | 'silence';

export interface VADCallbacks {
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
  onVolumeChange?: (volume: number) => void;
}

export class VADDetector {
  private config: Required<VADConfig>;
  private callbacks: VADCallbacks;
  private state: VADState = 'idle';
  private recording: Audio.Recording | null = null;
  private checkInterval: NodeJS.Timeout | null = null;
  private speechStartTime: number = 0;
  private lastSpeechTime: number = 0;
  private silenceTimer: NodeJS.Timeout | null = null;

  constructor(config: VADConfig = {}, callbacks: VADCallbacks = {}) {
    this.config = {
      threshold: 0.15,
      silenceTimeout: 1500,
      minSpeechDuration: 500,
      maxSpeechDuration: 60000,
      ...config,
    };
    this.callbacks = callbacks;
  }

  // 获取当前状态
  getState(): VADState {
    return this.state;
  }

  // 开始检测
  async start(): Promise<void> {
    if (this.state !== 'idle') {
      return;
    }

    try {
      // 设置音频模式
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: true,
      });

      // 创建录音实例（用于获取音量）
      const { recording } = await Audio.Recording.createAsync({
        android: {
          extension: '.m4a',
          outputFormat: Audio.AndroidOutputFormat.MPEG_4,
          audioEncoder: Audio.AndroidAudioEncoder.AAC,
          sampleRate: 16000,
          numberOfChannels: 1,
        },
        ios: {
          extension: '.m4a',
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
        },
      });

      this.recording = recording;
      this.state = 'idle';

      // 启动音量检测
      this.startVolumeCheck();
    } catch (error) {
      console.error('VAD 启动失败:', error);
      throw error;
    }
  }

  // 停止检测
  async stop(): Promise<void> {
    this.stopVolumeCheck();
    this.clearSilenceTimer();

    if (this.recording) {
      try {
        await this.recording.stopAndUnloadAsync();
      } catch (error) {
        // 忽略停止错误
      }
      this.recording = null;
    }

    this.state = 'idle';
    this.speechStartTime = 0;
    this.lastSpeechTime = 0;
  }

  // 启动音量检测
  private startVolumeCheck() {
    this.checkInterval = setInterval(async () => {
      if (!this.recording) return;

      try {
        const status = await this.recording.getStatusAsync();
        // @ts-ignore
        const metering = status.metering || -160;
        const volume = Math.max(0, Math.min(1, (metering + 160) / 160));

        // 回调音量变化
        this.callbacks.onVolumeChange?.(volume);

        // 检测语音活动
        this.processVolume(volume);
      } catch (error) {
        // 忽略检测错误
      }
    }, 100); // 每 100ms 检测一次
  }

  // 停止音量检测
  private stopVolumeCheck() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  // 处理音量
  private processVolume(volume: number) {
    const now = Date.now();

    if (volume > this.config.threshold) {
      // 检测到声音
      this.lastSpeechTime = now;

      if (this.state === 'idle') {
        // 开始语音
        this.state = 'speaking';
        this.speechStartTime = now;
        this.clearSilenceTimer();
        this.callbacks.onSpeechStart?.();
      }
    } else if (this.state === 'speaking') {
      // 语音中检测到静音
      this.state = 'silence';
      this.startSilenceTimer();
    }

    // 检查最大语音时长
    if (this.speechStartTime > 0) {
      const speechDuration = now - this.speechStartTime;
      if (speechDuration >= this.config.maxSpeechDuration) {
        this.stopSpeech();
      }
    }
  }

  // 启动静音定时器
  private startSilenceTimer() {
    this.clearSilenceTimer();
    this.silenceTimer = setTimeout(() => {
      const silenceDuration = Date.now() - this.lastSpeechTime;
      if (silenceDuration >= this.config.silenceTimeout) {
        // 静音超时，结束语音
        this.stopSpeech();
      }
    }, this.config.silenceTimeout);
  }

  // 清除静音定时器
  private clearSilenceTimer() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
  }

  // 停止语音
  private stopSpeech() {
    const speechDuration = Date.now() - this.speechStartTime;

    if (speechDuration >= this.config.minSpeechDuration) {
      // 语音时长满足要求，触发结束回调
      this.callbacks.onSpeechEnd?.();
    }

    this.state = 'idle';
    this.speechStartTime = 0;
    this.clearSilenceTimer();
  }

  // 手动触发语音结束（用于打断）
  forceEnd(): void {
    if (this.state === 'speaking' || this.state === 'silence') {
      this.stopSpeech();
    }
  }
}

// 简化的 VAD Hook 版本
export function useSimpleVAD(
  onSpeechStart: () => void,
  onSpeechEnd: () => void,
  threshold: number = 0.15
) {
  let isSpeaking = false;
  let silenceTimer: NodeJS.Timeout | null = null;
  const SILENCE_TIMEOUT = 1500;

  const processVolume = (volume: number) => {
    if (volume > threshold) {
      // 检测到声音
      if (!isSpeaking) {
        isSpeaking = true;
        onSpeechStart();
      }

      // 清除静音定时器
      if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
      }
    } else if (isSpeaking) {
      // 语音中静音，启动静音检测
      if (!silenceTimer) {
        silenceTimer = setTimeout(() => {
          isSpeaking = false;
          onSpeechEnd();
        }, SILENCE_TIMEOUT);
      }
    }
  };

  const reset = () => {
    isSpeaking = false;
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
  };

  return {
    processVolume,
    reset,
    get isSpeaking() {
      return isSpeaking;
    },
  };
}
