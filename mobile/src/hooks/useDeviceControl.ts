// 设备控制 Hook - 通过 HTTP API 与 Gateway 通信
// 支持双链路：链路一（Desktop）和链路二（直连 LLM）

import { useCallback, useRef, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { useConversationStore } from '@/stores/conversationStore';
import { api } from '@/services/api/client';
import { HumanRequest } from '@/types/hitl';
import { generateUUID } from '@/utils/uuid';

// 生成用户友好的 HTTP 错误消息
function getFriendlyErrorMessage(status: number, rawMessage: string): string {
  if (/quota|额度|配额/i.test(rawMessage)) return '配额不足，请联系管理员或升级套餐';
  switch (status) {
    case 400: return '请求参数错误，请检查后重试';
    case 401: return '登录已过期，请重新登录';
    case 403: return '没有权限执行此操作';
    case 404: return '请求的资源不存在';
    case 408: return '请求超时，请检查网络后重试';
    case 429: return '请求过于频繁，请稍后再试';
    case 500: return '服务器内部错误，请稍后再试';
    case 502: return '网关错误，请稍后再试';
    case 503: return '服务暂时不可用，请稍后再试';
    case 504: return '网关超时，请稍后再试';
    default: return rawMessage || `请求失败 (${status})`;
  }
}

// 消息类型
export type MessageType = 'text' | 'image' | 'audio' | 'file';

// 消息内容
export interface MessageContent {
  type: MessageType;
  text?: string;           // 文本内容
  imageUrl?: string;       // 图片 URL
  audioUrl?: string;       // 音频 URL
  fileUrl?: string;        // 文件 URL
  fileName?: string;       // 文件名
  mimeType?: string;       // MIME 类型
  duration?: number;       // 音频时长（秒）
}

export type DeviceControlState = 'idle' | 'sending' | 'sent' | 'error';

export interface QuotaExhaustedInfo {
  title: string;
  message: string;
  hint?: string;
  actionText?: string;
}

export interface PendingCommand {
  id: string;
  deviceKey: string;
  deviceName: string;
  action: string;
  parameters?: Record<string, any>;
  description?: string;
}

export interface UseDeviceControlOptions {
  onError?: (error: Error) => void;
  onCommandReady?: (command: PendingCommand) => void;
  onHITLRequest?: (request: HumanRequest) => void;
  onMessageSent?: (result: {
    commandId: number;
    threadId: string;
    aiMessage?: string;
    mode: 'desktop' | 'direct_llm';
  }) => void;
}

export interface UseDeviceControlReturn {
  // 连接状态
  state: DeviceControlState;
  isSending: boolean;

  // HITL 状态
  hitlRequest: HumanRequest | null;
  isWaitingForHuman: boolean;

  // 待确认指令
  pendingCommand: PendingCommand | null;

  // 配额耗尽状态
  quotaExhaustedInfo: QuotaExhaustedInfo | null;
  isQuotaExhausted: boolean;

  // 方法
  sendMessage: (content: MessageContent, options?: {
    conversationId?: string;
    deviceKey?: string;
    references?: any[];
  }) => Promise<void>;
  confirmCommand: (confirmed: boolean) => void;
  respondToHITL: (value: string) => void;
  cancelHITL: (reason?: string) => void;
  clearQuotaExhausted: () => void;
}

/**
 * 设备控制 Hook (HTTP 版本)
 * 支持双链路：
 * - 链路一（Desktop）: Mobile → Gateway → Desktop → LLM → MC
 * - 链路二（直连 LLM）: Mobile → Gateway → LLM → MC
 */
export function useDeviceControl(options: UseDeviceControlOptions = {}): UseDeviceControlReturn {
  const { onError, onCommandReady, onHITLRequest, onMessageSent } = options;
  const { token } = useAuthStore();
  const { messages } = useConversationStore();

  const [state, setState] = useState<DeviceControlState>('idle');
  const [hitlRequest, setHitlRequest] = useState<HumanRequest | null>(null);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand | null>(null);
  const [quotaExhaustedInfo, setQuotaExhaustedInfo] = useState<QuotaExhaustedInfo | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * 链路一：发送消息到 Desktop（通过 Gateway 转发）
   */
  const sendToDesktop = useCallback(async (
    content: MessageContent,
    options?: { conversationId?: string; deviceKey?: string; references?: any[] }
  ) => {
    if (!token || !options?.deviceKey) {
      throw new Error('未登录或未选择设备');
    }

    console.log('[DeviceControl] 链路一（Desktop）POST to: /gateway/api/v1/command/send, deviceKey:', options.deviceKey);

    // 构建消息内容
    const messageContent: Record<string, any> = {
      type: content.type,
    };

    switch (content.type) {
      case 'text':
        messageContent.message = content.text;
        break;
      case 'image':
        messageContent.image_url = content.imageUrl;
        messageContent.mime_type = content.mimeType;
        break;
      case 'audio':
        messageContent.audio_url = content.audioUrl;
        messageContent.duration = content.duration;
        messageContent.mime_type = content.mimeType;
        break;
      case 'file':
        messageContent.file_url = content.fileUrl;
        messageContent.file_name = content.fileName;
        messageContent.mime_type = content.mimeType;
        break;
    }

    const data = await api.post('/gateway/api/v1/command/send', {
      device_key: options.deviceKey,
      command_type: 'chat',
      thread_id: options.conversationId,
      content: messageContent,
    }, { signal: abortControllerRef.current?.signal });

    console.log('[DeviceControl] 链路一响应:', data);

    if (data.code !== 0) {
      const rawMsg = data.message || '发送失败';

      // 检测配额耗尽错误
      if (data.code === 429 || /quota/i.test(rawMsg)) {
        setQuotaExhaustedInfo({
          title: '配额已耗尽',
          message: rawMsg,
          hint: '请联系管理员添加配额，或升级您的订阅计划。',
        });
        const quotaError = new Error(rawMsg);
        (quotaError as any).__quota_exhausted = true;
        throw quotaError;
      }

      // 其他错误翻译为友好提示
      const friendlyMsg = getFriendlyErrorMessage(data.code || 500, rawMsg);
      throw new Error(friendlyMsg);
    }

    // 链路一不立即返回 AI 消息，由 Desktop 处理后上报到 MC
    // Mobile 通过后台轮询从 MC 获取结果
    onMessageSent?.({
      commandId: data.command_id || 0,
      threadId: data.data?.thread_id || options?.conversationId || '',
      mode: 'desktop',
    });
  }, [token, onMessageSent]);

  /**
   * 链路二：直连 LLM（通过 Gateway /v1/chat/completions）
   */
  const sendDirectLLM = useCallback(async (
    content: MessageContent,
    options?: { conversationId?: string; deviceKey?: string; references?: any[] }
  ) => {
    if (!token) {
      throw new Error('未登录');
    }

    console.log('[DeviceControl] 链路二（直连 LLM）POST to: /gateway/v1/chat/completions');

    // 构建用户消息内容
    let userContent = '';
    switch (content.type) {
      case 'text':
        userContent = content.text || '';
        break;
      case 'image':
        // OpenAI 视觉格式
        userContent = JSON.stringify([
          { type: 'text', text: '请分析这张图片' },
          { type: 'image_url', image_url: { url: content.imageUrl } },
        ]);
        break;
      case 'audio':
        userContent = `[语音消息] ${content.audioUrl || ''}`;
        break;
      case 'file':
        userContent = `[文件] ${content.fileName || content.fileUrl}`;
        break;
    }

    // 构建多轮对话消息上下文（仅包含 user 和 assistant 消息）
    const contextMessages = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }));
    contextMessages.push({ role: 'user', content: userContent });

    const data = await api.post('/gateway/v1/chat/completions', {
      model: '', // 空字符串，让 Gateway 使用配置的默认模型
      messages: contextMessages,
      stream: false,
      temperature: 0.7,
    }, {
      signal: abortControllerRef.current?.signal,
      headers: {
        'X-Thread-ID': options?.conversationId || '',
        'X-Device-Key': options?.deviceKey || '0',
      },
    });

    console.log('[DeviceControl] 链路二响应:', data);

    if (data.error) {
      const errorCode = data.error?.code || '';
      const rawMsg = data.error?.message || data.message || '发送失败';

      // 检测配额耗尽错误 (429 + quota_exhausted)
      if (errorCode === 'quota_exhausted') {
        setQuotaExhaustedInfo({
          title: '配额已耗尽',
          message: rawMsg || '您的 LLM 配额已耗尽。',
          hint: '请联系管理员添加配额，或升级您的订阅计划。',
        });
        const quotaError = new Error(rawMsg);
        (quotaError as any).__quota_exhausted = true;
        throw quotaError;
      }

      // 限流 / 引擎过载
      if (data.error?.status === 429 || data.error?.status === 503) {
        const isRateLimit =
          /rate_limit|too many requests|overloaded|引擎繁忙/i.test(rawMsg);
        const friendlyMsg = isRateLimit ? '服务繁忙，请稍后再试' : rawMsg;
        throw new Error(friendlyMsg);
      }

      // 其他 HTTP 错误生成友好提示
      const friendlyMsg = getFriendlyErrorMessage(data.error?.status || 500, rawMsg);
      throw new Error(friendlyMsg);
    }

    // 提取 AI 回复
    const aiMessage = data.choices?.[0]?.message?.content;

    onMessageSent?.({
      commandId: 0,
      threadId: options?.conversationId || '',
      aiMessage: aiMessage,
      mode: 'direct_llm',
    });
  }, [token, messages, onMessageSent]);

  /**
   * 发送消息 - 自动根据 deviceKey 选择链路
   */
  const sendMessage = useCallback(async (
    content: MessageContent,
    options?: { conversationId?: string; deviceKey?: string; references?: any[] }
  ) => {
    console.log('[DeviceControl] sendMessage called:', content.type, 'deviceKey:', options?.deviceKey || 'none');

    if (!token) {
      console.error('[DeviceControl] No auth token');
      onError?.(new Error('未登录'));
      return;
    }

    // 取消之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setState('sending');

    try {
      // 根据 deviceKey 选择链路
      // - 有 deviceKey 且不为空：链路一（Desktop）
      // - 无 deviceKey 或为空：链路二（直连 LLM）
      if (options?.deviceKey && options.deviceKey.trim() !== '') {
        await sendToDesktop(content, options);
      } else {
        await sendDirectLLM(content, options);
      }

      setState('sent');

      // 3秒后重置状态为 idle
      setTimeout(() => {
        setState('idle');
      }, 3000);

    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('[DeviceControl] Request aborted');
        return;
      }
      // 错误已由 UI 提示，控制台统一降级为 log
      console.log('[DeviceControl] Send failed:', error.message);
      setState('error');

      // 将错误抛给上层（ChatScreen handleSendMessage），由上层统一展示 UI
      throw error;
    }
  }, [token, sendToDesktop, sendDirectLLM]);

  // 确认执行指令 - 通过 HTTP
  const confirmCommand = useCallback(async (confirmed: boolean) => {
    if (!pendingCommand || !token) return;

    try {
      await api.post('/gateway/api/v1/hitl/confirm', {
        device_key: pendingCommand.deviceKey,
        request_id: pendingCommand.id,
        response: confirmed ? 'confirm' : 'cancel',
      });

      setPendingCommand(null);
    } catch (error: any) {
      console.error('[DeviceControl] Confirm failed:', error);
      onError?.(error);
    }
  }, [pendingCommand, token, onError]);

  // 响应 HITL 请求 - 通过 HTTP
  const respondToHITL = useCallback(async (value: string) => {
    if (!hitlRequest || !token) return;

    try {
      await api.post('/gateway/api/v1/hitl/text', {
        request_id: hitlRequest.id,
        text: value,
      });

      setHitlRequest(null);
    } catch (error: any) {
      console.error('[DeviceControl] HITL response failed:', error);
      onError?.(error);
    }
  }, [hitlRequest, token, onError]);

  // 取消 HITL 请求 - 通过 HTTP
  const cancelHITL = useCallback(async (reason?: string) => {
    if (!hitlRequest || !token) return;

    try {
      await api.post('/gateway/api/v1/hitl/confirm', {
        request_id: hitlRequest.id,
        response: 'cancel',
        reason: reason || '用户取消',
      });

      setHitlRequest(null);
    } catch (error: any) {
      console.error('[DeviceControl] HITL cancel failed:', error);
      onError?.(error);
    }
  }, [hitlRequest, token, onError]);

  // 清除配额耗尽状态
  const clearQuotaExhausted = useCallback(() => {
    setQuotaExhaustedInfo(null);
  }, []);

  return {
    state,
    isSending: state === 'sending',
    hitlRequest,
    isWaitingForHuman: !!hitlRequest,
    pendingCommand,
    quotaExhaustedInfo,
    isQuotaExhausted: !!quotaExhaustedInfo,
    sendMessage,
    confirmCommand,
    respondToHITL,
    cancelHITL,
    clearQuotaExhausted,
  };
}
