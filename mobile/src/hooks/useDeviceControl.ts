// 设备控制 Hook - 通过 HTTP API 与 Gateway 通信
// 支持双链路：链路一（Desktop）和链路二（直连 LLM）

import { useCallback, useRef, useState } from 'react';
import i18n from '@/locales';
import { useAuthStore } from '@/stores/authStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useConversationStore } from '@/stores/conversationStore';

import { api } from '@/services/api/client';
import { HumanRequest } from '@/types/hitl';
import { useHITLStore } from '@/stores/hitlStore';
import { generateUUID } from '@/utils/uuid';

// 生成用户友好的 HTTP 错误消息
function getFriendlyErrorMessage(status: number, rawMessage: string): string {
  if (/quota|额度|配额/i.test(rawMessage)) return i18n.t('deviceControl.httpErrors.quotaInsufficient');
  switch (status) {
    case 400: return i18n.t('deviceControl.httpErrors.400');
    case 401: return i18n.t('deviceControl.httpErrors.401');
    case 403: return i18n.t('deviceControl.httpErrors.403');
    case 404: return i18n.t('deviceControl.httpErrors.404');
    case 408: return i18n.t('deviceControl.httpErrors.408');
    case 429: return i18n.t('deviceControl.httpErrors.429');
    case 500: return i18n.t('deviceControl.httpErrors.500');
    case 502: return i18n.t('deviceControl.httpErrors.502');
    case 503: return i18n.t('deviceControl.httpErrors.503');
    case 504: return i18n.t('deviceControl.httpErrors.504');
    default: return rawMessage || i18n.t('deviceControl.httpErrors.default', { status });
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

export interface SendMessageOptions {
  conversationId?: string;
  deviceKey?: string;
  references?: any[];
  // 流式回调（仅链路二 / 直连 LLM 生效）
  onStreamStart?: () => void;
  onStreamChunk?: (chunk: string, fullText: string) => void;
  onStreamDone?: (fullText: string) => void;
}

export interface UseDeviceControlReturn {
  // 连接状态
  state: DeviceControlState;
  isSending: boolean;

  // HITL 状态
  hitlRequest: HumanRequest | null;
  isWaitingForHuman: boolean;
  setHitlRequest: (request: HumanRequest | null) => void;

  // 待确认指令
  pendingCommand: PendingCommand | null;

  // 配额耗尽状态
  quotaExhaustedInfo: QuotaExhaustedInfo | null;
  isQuotaExhausted: boolean;

  // 方法
  sendMessage: (content: MessageContent, options?: SendMessageOptions) => Promise<void>;
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

  const [state, setState] = useState<DeviceControlState>('idle');
  const hitlRequest = useHITLStore((state) => state.currentRequest);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);
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
      throw new Error(i18n.t('deviceControl.notSelectedDevice'));
    }


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

    // 如果有引用（消息引用/文件引用等），塞进 content 透传给 Agent
    if (options?.references && options.references.length > 0) {
      messageContent.references = options.references;
    }

    const data = await api.post('/gateway/api/v1/command/send', {
      device_key: options.deviceKey,
      command_type: 'chat',
      thread_id: options.conversationId,
      content: messageContent,
    }, { signal: abortControllerRef.current?.signal });


    if (data.code !== 0) {
      const rawMsg = data.message || i18n.t('deviceControl.httpErrors.sendFailed');

      // 检测配额耗尽错误
      if (data.code === 429 || /quota/i.test(rawMsg)) {
        setQuotaExhaustedInfo({
          title: i18n.t('deviceControl.quotaExhaustedTitle'),
          message: rawMsg,
          hint: i18n.t('deviceControl.quotaExhaustedHint'),
        });
        const quotaError = new Error(rawMsg);
        (quotaError as any).__quota_exhausted = true;
        throw quotaError;
      }

      // 其他错误翻译为友好提示
      const friendlyMsg = getFriendlyErrorMessage(data.code || 500, rawMsg);
      throw new Error(friendlyMsg);
    }

    // 链路一：消息由 Desktop Agent 通过 WebSocket 即时推送到 Mobile
    // Agent 产生消息时直接调用 _push_to_mobile()，不再依赖 MC 轮询
    onMessageSent?.({
      commandId: data.command_id || 0,
      threadId: data.data?.thread_id || options?.conversationId || '',
      mode: 'desktop',
    });
  }, [token, onMessageSent]);

  /**
   * 链路二：直连 LLM（通过 Gateway /v1/chat/completions）
   * 支持 SSE 流式输出
   */
  const sendDirectLLM = useCallback(async (
    content: MessageContent,
    options?: SendMessageOptions
  ) => {
    if (!token) {
      throw new Error(i18n.t('deviceControl.notLoggedIn'));
    }

    // 构建用户消息内容
    let userContent = '';
    switch (content.type) {
      case 'text':
        userContent = content.text || '';
        break;
      case 'image':
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

    // 构建多轮对话消息上下文
    const contextMessages = useConversationStore.getState().messages
      .filter(m => m.role === 'human' || m.role === 'ai')
      .map(m => ({ role: m.role, content: m.content }));
    contextMessages.push({ role: 'human', content: userContent });

    // SSE 流式请求
    let fullText = '';
    options?.onStreamStart?.();

    await api.fetchSSE('/gateway/v1/chat/completions', {
      model: '',
      messages: contextMessages,
      stream: true,
      temperature: 0.7,
    }, {
      onChunk: (chunk) => {
        fullText += chunk;
        console.log('[useDeviceControl] onChunk:', chunk, 'fullText length:', fullText.length);
        options?.onStreamChunk?.(chunk, fullText);
      },
      onDone: () => {
        options?.onStreamDone?.(fullText);
        // SSE 流式：消息已在流式过程中实时更新，不再重复添加
        // 只传递 threadId（用于新会话时设置 currentConversationId）
        onMessageSent?.({
          commandId: 0,
          threadId: options?.conversationId || '',
          mode: 'direct_llm',
        });
      },
      onError: (error) => {
        // 配额耗尽检测
        const rawMsg = error.message || '';
        if (/quota_exhausted|配额/i.test(rawMsg)) {
          setQuotaExhaustedInfo({
            title: i18n.t('deviceControl.quotaExhaustedTitle'),
            message: rawMsg || i18n.t('deviceControl.quotaExhaustedMessage'),
            hint: i18n.t('deviceControl.quotaExhaustedHint'),
          });
          const quotaError = new Error(rawMsg);
          (quotaError as any).__quota_exhausted = true;
          throw quotaError;
        }
        throw error;
      },
      signal: abortControllerRef.current?.signal,
      headers: {
        'X-Thread-ID': options?.conversationId || '',
        'X-Device-Key': options?.deviceKey || '0',
      },
    });
  }, [token, onMessageSent]);

  /**
   * 发送消息 - 自动根据 deviceKey 选择链路
   */
  const sendMessage = useCallback(async (
    content: MessageContent,
    options?: SendMessageOptions
  ) => {

    if (!token) {
      onError?.(new Error(i18n.t('deviceControl.notLoggedIn')));
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
      // - 无 deviceKey 或为空：链路二（直连 LLM，支持 SSE 流式）
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
        return;
      }
      setState('error');
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
      onError?.(error);
    }
  }, [pendingCommand, token, onError]);

  // 响应 HITL 请求 - 通过 HTTP
  // 响应 HITL 请求 - 通过 HTTP
  const respondToHITL = useCallback(async (value: string) => {
    if (!hitlRequest || !token) return;

    const deviceKey = useDeviceStore.getState().currentDevice?.deviceKey;
    if (!deviceKey) {
      onError?.(new Error(i18n.t('deviceControl.notSelectedDevice')));
      return;
    }

    try {
      // 根据不同的请求类型调用不同的后端接口
      if (hitlRequest.type === 'choice') {
        await api.post('/gateway/api/v1/hitl/choice', {
          device_key: deviceKey,
          request_id: hitlRequest.id,
          choice_id: value,
        });
      } else if (hitlRequest.type === 'approval' || hitlRequest.type === 'confirmation') {
        await api.post('/gateway/api/v1/hitl/confirm', {
          device_key: deviceKey,
          request_id: hitlRequest.id,
          response: value === 'APPROVED' || value === 'yes' ? 'confirm' : 'cancel',
        });
      } else {
        // 默认为 text 类型
        await api.post('/gateway/api/v1/hitl/text', {
          device_key: deviceKey,
          request_id: hitlRequest.id,
          text: value,
        });
      }

      setHitlRequest(null);
    } catch (error: any) {
      onError?.(error);
    }
  }, [hitlRequest, token, onError]);



  // 取消 HITL 请求 - 通过 HTTP
  const cancelHITL = useCallback(async (reason?: string) => {
    if (!hitlRequest || !token) return;

    const deviceKey = useDeviceStore.getState().currentDevice?.deviceKey;

    try {
      await api.post('/gateway/api/v1/hitl/confirm', {
        device_key: deviceKey,
        request_id: hitlRequest.id,
        response: 'cancel',
        reason: reason || i18n.t('deviceControl.hitlCancelReason'),
      });

      setHitlRequest(null);
    } catch (error: any) {
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
    setHitlRequest,
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
