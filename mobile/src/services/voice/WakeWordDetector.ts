// 唤醒词检测引擎 - 使用 Sherpa-ONNX 流式 ASR + 关键词匹配
// 纯本地运行，无需网络。ASR 输出文字后，在 JS 层匹配唤醒词。

import { sherpaOnnxASR, type SherpaAsrConfig } from '@/native-modules/SherpaOnnxASR';

/** 固定模型目录（打包在 App 资源中） */
const DEFAULT_MODEL_DIR = 'sherpa-asr/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23';

export interface WakeWordDetectorConfig {
  wakeWord: string;
  modelDir?: string;
}

export interface WakeWordDetectorCallbacks {
  onWake?: (detectedWord: string) => void;
  /** 检测到非唤醒词的语音活动（用于 TTS 播放时直接说话打断） */
  onSpeechDetected?: (text: string) => void;
  onError?: (error: Error) => void;
}

/**
 * 唤醒词检测引擎 - Sherpa-ONNX 流式 ASR
 *
 * 原理：
 * 1. Native 层启动流式 ASR（中文），持续识别用户语音
 * 2. 每次有新的识别结果，通过事件发送到 JS
 * 3. JS 层检查文字中是否包含唤醒词
 * 4. 匹配成功则触发 onWake
 */
export class WakeWordDetector {
  private config: { wakeWord: string; modelDir: string };
  private callbacks: WakeWordDetectorCallbacks;
  private isRunning = false;
  private isInitialized = false;
  private listenerRegistered = false;

  constructor(config: WakeWordDetectorConfig, callbacks: WakeWordDetectorCallbacks = {}) {
    this.config = {
      wakeWord: config.wakeWord,
      modelDir: config.modelDir || DEFAULT_MODEL_DIR,
    };
    this.callbacks = callbacks;
  }

  /**
   * 初始化 ASR 引擎（加载模型）
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    try {
      await sherpaOnnxASR.initialize({
        modelDir: this.config.modelDir,
        numThreads: 2,
      });

      if (!this.listenerRegistered) {
        sherpaOnnxASR.onAsrResult((event) => {
          if (!this.isRunning) return;
          const text = event.text.replace(/\s+/g, '').trim();
          const wakeWord = this.config.wakeWord.replace(/\s+/g, '').trim();

          if (text.includes(wakeWord)) {
            console.log('[WakeWord] 检测到唤醒词:', this.config.wakeWord);
            this.callbacks.onWake?.(this.config.wakeWord);
          } else if (text.length >= 2) {
            // TTS 播放时检测到非唤醒词的人声文本，触发语音打断
            this.callbacks.onSpeechDetected?.(text);
          }
        });

        sherpaOnnxASR.onError((error) => {
          console.error('[WakeWord] ASR 错误:', error.message);
          this.callbacks.onError?.(new Error(error.message));
        });

        this.listenerRegistered = true;
      }

      this.isInitialized = true;
      console.log('[WakeWord] ASR 引擎初始化完成');
    } catch (error) {
      console.error('[WakeWord] ASR 初始化失败:', error);
      this.callbacks.onError?.(error as Error);
      throw error;
    }
  }

  /**
   * 开始监听
   */
  async start(): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }
    if (this.isRunning) return;

    this.isRunning = true;
    await sherpaOnnxASR.start();
    console.log('[WakeWord] 监听已启动');
  }

  /**
   * 停止监听
   */
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    this.isRunning = false;
    await sherpaOnnxASR.stop();
    console.log('[WakeWord] 监听已停止');
  }

  /**
   * 释放所有资源
   */
  async destroy(): Promise<void> {
    this.isRunning = false;
    await sherpaOnnxASR.release();
    this.isInitialized = false;
    this.listenerRegistered = false;
    console.log('[WakeWord] ASR 资源已释放');
  }

  getIsRunning(): boolean {
    return this.isRunning;
  }
}
