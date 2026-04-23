// 语音会话管理器 - 整合音频录制、VAD 和 Gateway 通信

import { GatewayClient } from '../gateway/GatewayClient';
import { GatewayMessageType, HumanRequestMessage } from '../gateway/types';
import { HumanRequest } from '@/types/hitl';
import { useHITLStore } from '@/stores/hitlStore';
import { AudioRecorder } from './AudioRecorder';
import { VADDetector, VADConfig } from './VADDetector';
import { useVoiceStore } from '@/stores/voiceStore';
import { ChatMessage, TaskCommand } from '@/types/voice';
import { generateUUID } from '@/utils/uuid';

export type VoiceSessionState = 'idle' | 'connecting' | 'listening' | 'recognizing' | 'thinking' | 'speaking';

export interface VoiceSessionCallbacks {
  onStateChange?: (state: VoiceSessionState) => void;
  onMessage?: (message: ChatMessage) => void;
  onCommandReady?: (command: TaskCommand) => void;
  onError?: (error: Error) => void;
  onVolumeChange?: (volume: number) => void;
}

export class VoiceSessionManager {
  private gateway: GatewayClient;
  private audioRecorder: AudioRecorder;
  private vadDetector: VADDetector;
  private callbacks: VoiceSessionCallbacks;
  private sessionId: string = '';
  private state: VoiceSessionState = 'idle';
  private store = useVoiceStore.getState();
  private hitlStore = useHITLStore.getState();

  constructor(callbacks: VoiceSessionCallbacks = {}, vadConfig?: VADConfig) {
    this.gateway = GatewayClient.getInstance();
    this.audioRecorder = new AudioRecorder();
    this.callbacks = callbacks;

    // 初始化 VAD 检测器
    this.vadDetector = new VADDetector(vadConfig, {
      onSpeechStart: () => this.handleSpeechStart(),
      onSpeechEnd: () => this.handleSpeechEnd(),
      onVolumeChange: (volume) => this.callbacks.onVolumeChange?.(volume),
    });

    // 监听 Gateway 事件
    this.setupGatewayListeners();
  }

  // 获取当前状态
  getState(): VoiceSessionState {
    return this.state;
  }

  // 开始语音会话
  async start(): Promise<void> {
    if (this.state !== 'idle') {
      return;
    }

    try {
      this.setState('connecting');

      // 生成会话 ID
      this.sessionId = generateUUID();

      // 确保 Gateway 连接
      await this.gateway.connect();

      // 开始 VAD 检测
      await this.vadDetector.start();

      // 初始化音频录制
      await this.audioRecorder.initialize();

      // 更新 store
      this.store.startSession(this.sessionId);

      // 设置为监听状态
      this.setState('listening');

      // 通知 Gateway 开始 ASR
      this.gateway.startASR(this.sessionId);
    } catch (error) {
      this.setState('idle');
      this.callbacks.onError?.(error as Error);
      throw error;
    }
  }

  // 停止语音会话
  async stop(): Promise<void> {
    if (this.state === 'idle') {
      return;
    }

    try {
      // 停止 VAD 检测
      await this.vadDetector.stop();

      // 停止音频录制
      await this.audioRecorder.cleanup();

      // 通知 Gateway 停止 ASR
      this.gateway.stopASR(this.sessionId);

      // 更新 store
      this.store.endSession();

      // 重置状态
      this.setState('idle');
      this.sessionId = '';
    } catch (error) {
      console.error('停止会话失败:', error);
    }
  }

  // 打断当前会话（用于用户主动打断 AI 讲话）
  async interrupt(): Promise<void> {
    if (this.state === 'speaking') {
      // 发送打断消息到 Gateway
      this.gateway.send({
        type: GatewayMessageType.CHAT_INTERRUPT,
        payload: {
          sessionId: this.sessionId,
        },
        timestamp: Date.now(),
      });

      // 停止当前播放（如果有 TTS 播放）
      // TODO: 实现 TTS 播放停止

      // 返回监听状态
      this.setState('listening');
    }
  }

  // 发送 HITL 响应
  sendHITLResponse(requestId: string, value: string): void {
    if (!this.sessionId) {
      this.callbacks.onError?.(new Error('会话未启动'));
      return;
    }

    // 更新 HITL store
    this.hitlStore.respondToCurrent(value);

    // 发送到 Gateway
    this.gateway.send({
      type: GatewayMessageType.HUMAN_RESPONSE,
      payload: {
        sessionId: this.sessionId,
        requestId,
        value,
      },
      timestamp: Date.now(),
    });

    // 添加用户消息到对话
    const displayValue = value.length > 50 ? `${value.slice(0, 50)}...` : value;
    this.store.addMessage({
      id: generateUUID(),
      role: 'user',
      content: `[响应] ${displayValue}`,
      timestamp: Date.now(),
    });

    // 恢复思考状态
    this.setState('thinking');
  }

  // 取消当前 HITL 请求
  cancelHITLRequest(reason?: string): void {
    if (!this.sessionId) return;

    const currentRequest = this.hitlStore.currentRequest;
    if (!currentRequest) return;

    this.hitlStore.cancelCurrent(reason);

    // 发送到 Gateway
    this.gateway.send({
      type: GatewayMessageType.HUMAN_CANCEL,
      payload: {
        sessionId: this.sessionId,
        requestId: currentRequest.id,
        reason: reason || '用户取消',
      },
      timestamp: Date.now(),
    });

    // 添加系统消息
    this.store.addMessage({
      id: generateUUID(),
      role: 'system',
      content: `输入已取消: ${reason || '用户取消'}`,
      timestamp: Date.now(),
    });

    // 恢复监听状态
    this.setState('listening');
  }

  // 确认执行指令
  confirmCommand(confirmed: boolean): void {
    const command = this.store.currentCommand;
    if (!command) return;

    // 更新 store
    this.store.confirmCurrentCommand(confirmed);

    // 通知 Gateway
    this.gateway.confirmCommand(this.sessionId, confirmed);

    if (confirmed) {
      // 添加系统消息
      this.store.addMessage({
        id: generateUUID(),
        role: 'system',
        content: '指令已确认执行',
        timestamp: Date.now(),
      });
    } else {
      // 添加系统消息
      this.store.addMessage({
        id: generateUUID(),
        role: 'system',
        content: '指令已取消',
        timestamp: Date.now(),
      });
    }
  }

  // 发送文本消息
  sendTextMessage(text: string): void {
    if (!this.sessionId) {
      this.callbacks.onError?.(new Error('会话未启动'));
      return;
    }

    // 添加用户消息到 store
    const userMessage: ChatMessage = {
      id: generateUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    this.store.addMessage(userMessage);
    this.callbacks.onMessage?.(userMessage);

    // 发送到 Gateway
    this.gateway.send({
      type: GatewayMessageType.CHAT_MESSAGE,
      payload: {
        sessionId: this.sessionId,
        message: text,
      },
      timestamp: Date.now(),
    });

    // 进入思考状态
    this.setState('thinking');
  }

  // 设置 Gateway 事件监听
  private setupGatewayListeners(): void {
    // 监听 ASR 结果
    this.gateway.on(GatewayMessageType.ASR_RESULT, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      if (data.payload?.text) {
        // 添加用户消息
        const message: ChatMessage = {
          id: generateUUID(),
          role: 'user',
          content: data.payload.text,
          timestamp: Date.now(),
          isFinal: data.payload.isFinal,
        };
        this.store.addMessage(message);
        this.callbacks.onMessage?.(message);

        if (data.payload.isFinal) {
          // ASR 完成，进入思考状态
          this.setState('thinking');
        }
      }
    });

    // 监听聊天流
    this.gateway.on(GatewayMessageType.CHAT_STREAM, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      const { payload } = data;

      // 流式消息块
      this.handleChatChunk(payload);
    });

    // 监听聊天完成
    this.gateway.on(GatewayMessageType.CHAT_DONE, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      this.handleChatComplete(data.payload);
    });

    // 监听指令确认
    this.gateway.on(GatewayMessageType.COMMAND_READY, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      const cmd = data.payload?.command;
      if (!cmd) return;

      const command: TaskCommand = {
        id: generateUUID(),
        deviceKey: cmd.target || 'unknown',
        deviceName: cmd.target || '未知设备',
        deviceType: cmd.type,
        action: cmd.type,
        parameters: cmd.parameters,
        status: 'pending',
        description: cmd.description,
      };

      // 更新 store
      this.store.setCurrentCommand(command);
      this.callbacks.onCommandReady?.(command);
    });

    // 监听错误
    this.gateway.on(GatewayMessageType.ASR_ERROR, (data) => {
      this.callbacks.onError?.(new Error(data.payload?.error || '语音识别错误'));
    });

    // 监听 HITL 请求
    this.gateway.on(GatewayMessageType.HUMAN_REQUEST, (data: HumanRequestMessage) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      const requestData = data.payload.request;
      const request: HumanRequest = {
        id: requestData.id,
        type: requestData.type,
        prompt: requestData.prompt,
        options: requestData.options,
        default_value: requestData.default_value,
        context: requestData.context,
        timestamp: Date.now(),
        timeout: requestData.timeout,
      };

      // 添加到 HITL store
      this.hitlStore.addRequest(request);

      // 添加系统消息提示
      this.store.addMessage({
        id: generateUUID(),
        role: 'system',
        content: `Agent 需要您的输入: ${requestData.prompt}`,
        timestamp: Date.now(),
      });
    });

    // 监听 HITL 超时
    this.gateway.on(GatewayMessageType.HUMAN_TIMEOUT, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      this.hitlStore.timeoutCurrent();

      // 添加系统消息
      this.store.addMessage({
        id: generateUUID(),
        role: 'system',
        content: '输入等待已超时',
        timestamp: Date.now(),
      });
    });

    // 监听 HITL 取消
    this.gateway.on(GatewayMessageType.HUMAN_CANCEL, (data) => {
      if (data.payload?.sessionId !== this.sessionId) return;

      this.hitlStore.cancelCurrent(data.payload?.reason);
    });
  }

  // 处理语音识别开始
  private handleSpeechStart(): void {
    if (this.state === 'listening') {
      // 可以在这里触发 UI 反馈，如显示波形动画
    }
  }

  // 处理语音识别结束
  private async handleSpeechEnd(): Promise<void> {
    if (this.state === 'listening') {
      this.setState('recognizing');

      // 停止录音并获取音频
      const audioUri = await this.audioRecorder.stop();

      if (audioUri) {
        try {
          // 读取音频文件为 base64
          const base64Audio = await this.audioRecorder.readAudioFile(audioUri);

          // 发送音频数据到 Gateway
          this.gateway.sendAudioChunk(this.sessionId, base64Audio);

          // 清理音频文件
          await this.audioRecorder.deleteAudioFile(audioUri);
        } catch (error) {
          console.error('发送音频数据失败:', error);
        }
      }

      // 重新启动录音以继续监听
      await this.audioRecorder.initialize();
      this.setState('listening');
    }
  }

  // 处理聊天流消息块
  private handleChatChunk(payload: any): void {
    this.setState('speaking');

    // 更新或添加助手消息
    const messages = this.store.messages;
    const lastMessage = messages[messages.length - 1];

    if (lastMessage && lastMessage.role === 'assistant' && !lastMessage.isComplete) {
      // 更新现有消息
      this.store.updateLastMessage({
        content: lastMessage.content + payload.content,
      });
    } else {
      // 添加新消息
      const message: ChatMessage = {
        id: payload.messageId || generateUUID(),
        role: 'assistant',
        content: payload.content,
        timestamp: Date.now(),
        isComplete: false,
      };
      this.store.addMessage(message);
    }
  }

  // 处理聊天消息完成
  private handleChatComplete(payload: any): void {
    this.store.updateLastMessage({
      isComplete: true,
    });

    // 返回到监听状态
    this.setState('listening');
  }

  // 设置状态
  private setState(state: VoiceSessionState): void {
    this.state = state;
    this.store.setSessionState(state);
    this.callbacks.onStateChange?.(state);
  }
}

// 单例实例
let instance: VoiceSessionManager | null = null;

export function getVoiceSessionManager(callbacks?: VoiceSessionCallbacks): VoiceSessionManager {
  if (!instance) {
    instance = new VoiceSessionManager(callbacks);
  } else if (callbacks) {
    // 更新回调
    (instance as any).callbacks = callbacks;
  }
  return instance;
}
