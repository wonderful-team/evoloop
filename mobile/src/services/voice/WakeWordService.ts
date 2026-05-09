// 唤醒词后台生命周期管理服务
// 管理 WakeWordDetector 的启动/停止 + AppState 变化 + Android 前台服务通知

import { AppState, AppStateStatus, Platform } from 'react-native';
import notifee, { AndroidImportance } from '@notifee/react-native';
import i18n from '@/locales';
import { WakeWordDetector, type WakeWordDetectorConfig } from './WakeWordDetector';

export interface WakeWordServiceOptions extends WakeWordDetectorConfig {
  onWake?: (detectedWord: string) => void;
  onSpeechDetected?: (text: string) => void;
  onError?: (error: Error) => void;
}

/**
 * 唤醒词后台服务
 * 封装 WakeWordDetector + AppState 监听 + Android 前台服务
 */
export class WakeWordService {
  private detector: WakeWordDetector | null = null;
  private options: WakeWordServiceOptions;
  private appStateSubscription: { remove: () => void } | null = null;
  private isStarted = false;
  private channelCreated = false;

  constructor(options: WakeWordServiceOptions) {
    this.options = options;
  }

  /**
   * 启动唤醒词监听（前台/后台均支持）
   */
  async start(): Promise<void> {
    if (this.isStarted) {
      return;
    }

    try {
      // 创建通知渠道（Android）
      if (Platform.OS === 'android' && !this.channelCreated) {
        await notifee.createChannel({
          id: 'wake-word',
          name: i18n.t('notifications.wakeWordTitle'),
          importance: AndroidImportance.LOW,
          vibration: false,
        });
        this.channelCreated = true;
      }

      // 初始化检测器
      this.detector = new WakeWordDetector(
        {
          wakeWord: this.options.wakeWord,
          modelDir: this.options.modelDir,
        },
        {
          onWake: (text) => {
            this.options.onWake?.(text);
          },
          onSpeechDetected: (text) => {
            this.options.onSpeechDetected?.(text);
          },
          onError: (error) => {
            this.options.onError?.(error);
          },
        }
      );

      await this.detector.start();
      this.isStarted = true;

      // 监听 AppState 变化
      this.appStateSubscription = AppState.addEventListener(
        'change',
        this.handleAppStateChange
      );

      // 根据当前状态处理后台通知
      const currentState = AppState.currentState;
      if (currentState === 'background') {
        await this.startBackgroundNotification();
      }

      console.log('[WakeWordService] 服务已启动');
    } catch (error) {
      this.isStarted = false;
      throw error;
    }
  }

  /**
   * 停止唤醒词监听
   */
  async stop(): Promise<void> {
    if (!this.isStarted) {
      return;
    }

    this.isStarted = false;

    // 移除 AppState 监听
    this.appStateSubscription?.remove();
    this.appStateSubscription = null;

    // 停止后台通知
    await this.stopBackgroundNotification();

    // 停止检测器
    try {
      await this.detector?.destroy();
    } catch (e) {
      // 忽略
    }
    this.detector = null;

    console.log('[WakeWordService] 服务已停止');
  }

  /**
   * 获取当前状态
   */
  getIsStarted(): boolean {
    return this.isStarted;
  }

  /**
   * 处理 AppState 变化
   */
  private handleAppStateChange = async (nextAppState: AppStateStatus): Promise<void> => {
    if (!this.isStarted) {
      return;
    }

    if (nextAppState === 'background') {
      await this.startBackgroundNotification();
    } else if (nextAppState === 'active') {
      await this.stopBackgroundNotification();
    }
  };

  /**
   * 启动 Android 前台服务通知
   */
  private async startBackgroundNotification(): Promise<void> {
    if (Platform.OS !== 'android') {
      return;
    }

    try {
      await notifee.displayNotification({
        title: i18n.t('notifications.wakeWordTitle'),
        body: i18n.t('notifications.wakeWordBody', { wakeWord: this.options.wakeWord }),
        android: {
          channelId: 'wake-word',
          asForegroundService: true,
          ongoing: true,
          pressAction: {
            id: 'default',
          },
          importance: AndroidImportance.LOW,
        },
      });
      console.log('[WakeWordService] Android 前台服务已启动');
    } catch (error) {
      console.error('[WakeWordService] 启动前台服务失败:', error);
    }
  }

  /**
   * 停止 Android 前台服务通知
   */
  private async stopBackgroundNotification(): Promise<void> {
    if (Platform.OS !== 'android') {
      return;
    }

    try {
      await notifee.stopForegroundService();
      console.log('[WakeWordService] Android 前台服务已停止');
    } catch (error) {
      // 可能服务未启动，忽略错误
    }
  }
}
