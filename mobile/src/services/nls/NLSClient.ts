// 阿里云 NLS 实时语音识别客户端

import { EventEmitter } from 'eventemitter3';
import { 
  NLSConfig, 
  NLSCallbacks, 
  NLSState, 
  NLSMessageType,
  NLSTranscriptionResult 
} from './types';
import { generateUUID } from '@/utils/uuid';
import i18n from '@/locales';

const NLS_DEFAULT_URL = 'wss://nls-gateway.aliyuncs.com/ws/v1';

export class NLSClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private config: NLSConfig;
  private callbacks: NLSCallbacks;
  private state: NLSState = 'idle';
  private taskId: string = '';
  
  constructor(config: NLSConfig, callbacks: NLSCallbacks = {}) {
    super();
    this.config = {
      url: NLS_DEFAULT_URL,
      sampleRate: 16000,
      format: 'opus',
      ...config,
    };
    this.callbacks = callbacks;
  }

  // 获取当前状态
  getState(): NLSState {
    return this.state;
  }

  // 连接并启动识别
  async connect(): Promise<void> {
    if (this.state !== 'idle') {
      throw new Error(i18n.t('nls.errors.clientRunning'));
    }

    this.setState('connecting');
    this.taskId = generateUUID().replace(/-/g, '');

    return new Promise((resolve, reject) => {
      try {
        // 构建 WebSocket URL（带 Token）
        const url = `${this.config.url}?token=${encodeURIComponent(this.config.token)}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('NLS WebSocket 已连接');
          this.setState('connected');
          this.callbacks.onConnected?.();
          
          // 发送开始识别指令
          this.startTranscription();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error('NLS WebSocket 错误:', error);
          this.setState('error');
          this.callbacks.onError?.(new Error(i18n.t('nls.errors.wsError')));
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('NLS WebSocket 已关闭');
          this.setState('idle');
          this.callbacks.onDisconnected?.();
        };
      } catch (error) {
        this.setState('error');
        reject(error);
      }
    });
  }

  // 断开连接（不再自动发送停止指令，由调用方控制）
  disconnect(): void {
    if (this.ws) {
      // 关闭连接
      this.ws.close();
      this.ws = null;
    }
    this.setState('idle');
  }

  // 发送音频数据
  sendAudio(audioData: ArrayBuffer | Uint8Array): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.warn('NLS WebSocket 未连接，无法发送音频');
      return;
    }

    // 音频数据以 Binary Frame 发送
    this.ws.send(audioData);
  }

  // 发送开始识别指令
  private startTranscription(): void {
    const message = {
      header: {
        message_id: generateUUID().replace(/-/g, ''),
        task_id: this.taskId,
        namespace: 'SpeechTranscriber',
        name: NLSMessageType.START_TRANSCRIPTION,
        appkey: this.config.appKey,
      },
      payload: {
        sample_rate: this.config.sampleRate,
        format: this.config.format,
        enable_intermediate_result: true,      // 返回中间结果
        enable_punctuation_prediction: true,   // 添加标点
        enable_inverse_text_normalization: true, // 数字转换
        max_sentence_silence: 800,             // 800ms 静音断句
        enable_words: false,
        disfluency: true,                      // 过滤语气词
      },
    };

    this.sendJSON(message);
    console.log('发送开始识别指令');
  }

  // 发送停止识别指令（public，供外部调用）
  stopRecognition(): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    const message = {
      header: {
        message_id: generateUUID().replace(/-/g, ''),
        task_id: this.taskId,
        namespace: 'SpeechTranscriber',
        name: NLSMessageType.STOP_TRANSCRIPTION,
        appkey: this.config.appKey,
      },
    };

    this.sendJSON(message);
    console.log('发送停止识别指令');
  }

  // 发送 JSON 消息
  private sendJSON(data: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  // 处理收到的消息
  private handleMessage(data: any): void {
    try {
      if (!data) return;
      const result: NLSTranscriptionResult = typeof data === 'string' ? JSON.parse(data) : data;
      if (!result || !result.header) return;
      const { name, status } = result.header;

      // 检查状态码
      if (status !== 20000000) {
        const statusText = String(result.header.status_text || '');
        // IDLE_TIMEOUT 是正常行为（StopTranscription 后服务端空闲断开）
        if (statusText.includes('IDLE_TIMEOUT')) {
          console.log('NLS 空闲超时断开，属于正常行为');
          return;
        }
        console.error('NLS 错误:', statusText);
        if (typeof this.callbacks.onError === 'function') {
          this.callbacks.onError(new Error(statusText || i18n.t('nls.errors.recognitionError')));
        }
        return;
      }

      switch (name) {
        case NLSMessageType.TRANSCRIPTION_STARTED:
          console.log('识别已开始');
          this.setState('recognizing');
          if (typeof this.callbacks.onRecognitionStarted === 'function') {
            this.callbacks.onRecognitionStarted();
          }
          break;

        case NLSMessageType.TRANSCRIPTION_RESULT_CHANGED:
          // 中间结果
          if (result.payload?.result && typeof this.callbacks.onResultChanged === 'function') {
            this.callbacks.onResultChanged(result.payload.result);
          }
          break;

        case NLSMessageType.SENTENCE_END:
          // 一句话结束
          if (result.payload?.result && typeof this.callbacks.onSentenceEnd === 'function') {
            this.callbacks.onSentenceEnd(result.payload.result);
          }
          break;

        case NLSMessageType.TRANSCRIPTION_COMPLETED:
          console.log('识别已完成');
          if (typeof this.callbacks.onRecognitionCompleted === 'function') {
            this.callbacks.onRecognitionCompleted();
          }
          break;

        case NLSMessageType.TASK_FAILED:
          const taskFailedText = String(result.header.status_text || '');
          // IDLE_TIMEOUT 是正常行为，忽略
          if (taskFailedText.includes('IDLE_TIMEOUT')) {
            console.log('NLS 任务空闲超时断开');
            return;
          }
          console.error('识别任务失败:', taskFailedText);
          if (typeof this.callbacks.onError === 'function') {
            this.callbacks.onError(new Error(taskFailedText || i18n.t('nls.errors.recognitionFailed')));
          }
          break;
      }
    } catch (error) {
      console.error('解析 NLS 消息失败:', error);
    }
  }

  // 设置状态
  private setState(state: NLSState): void {
    this.state = state;
    this.emit('stateChange', state);
  }
}
