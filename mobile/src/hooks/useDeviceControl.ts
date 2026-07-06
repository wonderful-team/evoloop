// 设备控制 Hook - 通过 HTTP API 与 Gateway 通信
// 支持双链路：链路一（Desktop）和链路二（直连 LLM）

import { useCallback, useRef, useState } from 'react';
import i18n from '@/locales';
import { useAuthStore } from '@/stores/authStore';
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
  threadId?: string;
  deviceKey: string;
  deviceName: string;
  action: string;
  parameters?: Record<string, any>;
  description?: string;
}

export interface UseDeviceControlOptions {
  onError?: (error: Error) => void;
  onMessageSent?: (result: {
    commandId: number;
    threadId: string;
    messageId?: string;
    aiMessage?: string;
    mode: 'desktop' | 'direct_llm';
  }) => void;
}

export interface SendMessageOptions {
  conversationId?: string;
  deviceKey?: string;
  references?: any[];
  projectId?: number;
  messageId?: string;
  stream?: boolean;
  // 流式回调（仅链路二 / 直连 LLM 生效）
  onStreamStart?: () => void;
  onStreamChunk?: (chunk: string, fullText: string) => void;
  onStreamDone?: (fullText: string) => void;
  // Gateway 扩展元数据回调（链路二 SSE 末尾返回 message_id / thread_id）
  onGatewayMetadata?: (meta: { message_id: string; thread_id: string }) => void;
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
  const { onError, onMessageSent } = options;
  const { token } = useAuthStore();

  const [state, setState] = useState<DeviceControlState>('idle');
  const hitlRequest = useHITLStore((state) => state.currentRequest);
  const setHitlRequest = useHITLStore((state) => state.setCurrentRequest);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand | null>(null);
  const [quotaExhaustedInfo, setQuotaExhaustedInfo] = useState<QuotaExhaustedInfo | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * 链路一：发送消息到指定设备（通过 Gateway 转发）
   */
  const sendToDevice = useCallback(async (
    content: MessageContent,
    options?: { conversationId?: string; deviceKey?: string; references?: any[]; projectId?: number }
  ) => {
    if (!token || !options?.deviceKey) {
      throw new Error(i18n.t('deviceControl.notSelectedDevice'));
    }


    // 构建 Canonical Envelope（遵循 @schemas/message.json）
    // content 对象格式遵循 @schemas/types/command.relay.json
    const messageContent: Record<string, any> = {};

    switch (content.type) {
      case 'text':
        messageContent.text = content.text;
        break;
      case 'image':
        messageContent.image_url = content.imageUrl;
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

    if (options?.references && options.references.length > 0) {
      messageContent.references = options.references;
    }

    const bodyPayload: Record<string, any> = {
      action: 'chat',
      thread_id: options?.conversationId,
      content: messageContent,
    };
    if (options?.projectId) {
      bodyPayload.project_id = options.projectId;
    }

    const envelope = {
      version: '2.0',
      type: 'command.relay',
      timestamp: Math.floor(Date.now() / 1000),
      source: { kind: 'mobile' },
      target: { kind: 'agent', device_key: options?.deviceKey },
      body: bodyPayload,
    };

    const data = await api.post('/gateway/api/v1/message/send', {
      target_device_key: options?.deviceKey,
      envelope,
    }, { signal: abortControllerRef.current?.signal });

    if (data.code !== 0) {
      const rawMsg = data.message || i18n.t('deviceControl.httpErrors.sendFailed');

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

      const friendlyMsg = getFriendlyErrorMessage(data.code || 500, rawMsg);
      throw new Error(friendlyMsg);
    }

    onMessageSent?.({
      commandId: 0,
      threadId: options?.conversationId || '',
      messageId: bodyPayload.message_id,
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
          { type: 'text', text: i18n.t('chat.imageAnalyzePrompt') },
          { type: 'image_url', image_url: { url: content.imageUrl } },
        ]);
        break;
      case 'audio':
        userContent = `${i18n.t('chat.voiceMessagePlaceholder')} ${content.audioUrl || ''}`;
        break;
      case 'file':
        userContent = `${i18n.t('chat.fileMessagePlaceholder')} ${content.fileName || content.fileUrl}`;
        break;
    }

    // 构建多轮对话消息上下文（内部角色为 human/ai；OpenAI API 需要 user/assistant）
    const contextMessages = useConversationStore.getState().messages
      .filter(m => m.role === 'human' || m.role === 'ai')
      .map(m => ({
        role: m.role === 'human' ? 'user' : 'assistant',
        content: m.content
      }));
    contextMessages.push({ role: 'user', content: userContent });

    // 非流式 Direct-LLM 路径：直接走 api.post 读取 metadata.message_id
    if (!options?.stream) {
      const threadId = options?.conversationId || generateUUID();
      const data = await api.post('/gateway/v1/chat/completions', {
        model: '',
        messages: contextMessages,
        stream: false,
        temperature: 1,
      }, {
        headers: {
          'X-Thread-ID': threadId,
          'X-Device-Key': options?.deviceKey || '0',
        },
      });

      const aiMessage = data?.choices?.[0]?.message?.content || '';
      const messageId = data?.metadata?.message_id;
      const responseThreadId = data?.metadata?.thread_id || threadId;

      onMessageSent?.({
        commandId: 0,
        threadId: responseThreadId,
        messageId,
        aiMessage,
        mode: 'direct_llm',
      });
      return;
    }

    // SSE 流式请求
    let fullText = '';
    options?.onStreamStart?.();

    // device-less 直连 LLM：本地生成 thread_id，Gateway 会原样返回
    const threadId = options?.conversationId || generateUUID();

    await api.fetchSSE('/gateway/v1/chat/completions', {
      model: '',
      messages: contextMessages,
      stream: true,
      temperature: 1,
    }, {
      onChunk: (chunk) => {
        fullText += chunk;
        console.log('[useDeviceControl] onChunk:', chunk, 'fullText length:', fullText.length);
        options?.onStreamChunk?.(chunk, fullText);
      },
      onMetadata: (meta) => {
        options?.onGatewayMetadata?.(meta);
      },
      onDone: () => {
        options?.onStreamDone?.(fullText);
        // SSE 流式：消息已在流式过程中实时更新，不再重复添加
        // 只传递 threadId（用于新会话时设置 currentConversationId）
        onMessageSent?.({
          commandId: 0,
          threadId: options?.conversationId || threadId,
          messageId: options?.messageId,
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
        'X-Thread-ID': threadId,
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
      // - 有 deviceKey 且不为空：链路一（指定设备，Gateway 转发）
      // - 无 deviceKey 或为空：链路二（直连 LLM，支持 SSE 流式）
      if (options?.deviceKey && options.deviceKey.trim() !== '') {
        await sendToDevice(content, options);
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
  }, [token, sendToDevice, sendDirectLLM, onError]);

  // 确认执行指令 - 通过 HTTP
  const confirmCommand = useCallback(async (confirmed: boolean) => {
    if (!pendingCommand || !token) return;

    const activeDeviceKey = useConversationStore.getState().activeDeviceKey;
    if (!activeDeviceKey) {
      onError?.(new Error(i18n.t('deviceControl.notSelectedDevice')));
      return;
    }

    try {
      const envelope = {
        version: '2.0',
        type: 'hitl.response',
        timestamp: Math.floor(Date.now() / 1000),
        source: { kind: 'mobile' },
        target: { kind: 'agent', device_key: activeDeviceKey },
        body: {
          request_id: pendingCommand.id,
          thread_id: pendingCommand.threadId,
          action: 'confirm',
          value: confirmed ? 'APPROVED' : 'REJECTED',
        },
      };
      await api.post('/gateway/api/v1/message/send', {
        target_device_key: activeDeviceKey,
        envelope,
      });

      setPendingCommand(null);
    } catch (error: any) {
      onError?.(error);
    }
  }, [pendingCommand, token, onError]);

  // 响应 HITL 请求 - 通过 HTTP
  const respondToHITL = useCallback(async (value: string) => {
    if (!hitlRequest || !token) return;

    const activeDeviceKey = useConversationStore.getState().activeDeviceKey;
    if (!activeDeviceKey) {
      onError?.(new Error(i18n.t('deviceControl.notSelectedDevice')));
      return;
    }

    const action: 'confirm' | 'choice' | 'text' =
      hitlRequest.type === 'choice' ? 'choice'
      : hitlRequest.type === 'approval' || hitlRequest.type === 'confirmation' ? 'confirm'
      : 'text';

    try {
      const envelope = {
        version: '2.0',
        type: 'hitl.response',
        timestamp: Math.floor(Date.now() / 1000),
        source: { kind: 'mobile' },
        target: { kind: 'agent', device_key: activeDeviceKey },
        body: {
          request_id: hitlRequest.id,
          thread_id: hitlRequest.threadId,
          action,
          value,
        },
      };
      await api.post('/gateway/api/v1/message/send', {
        target_device_key: activeDeviceKey,
        envelope,
      });

      setHitlRequest(null);
    } catch (error: any) {
      onError?.(error);
    }
  }, [hitlRequest, token, onError, setHitlRequest]);

  // 取消 HITL 请求 - 通过 HTTP
  const cancelHITL = useCallback(async (reason?: string) => {
    if (!hitlRequest || !token) return;

    const activeDeviceKey = useConversationStore.getState().activeDeviceKey;
    if (!activeDeviceKey) {
      console.warn('[DeviceControl] cancelHITL: no active device key, skipping');
      setHitlRequest(null);
      return;
    }

    try {
      const envelope = {
        version: '2.0',
        type: 'hitl.cancel',
        timestamp: Math.floor(Date.now() / 1000),
        source: { kind: 'mobile' },
        target: { kind: 'agent', device_key: activeDeviceKey },
        body: {
          request_id: hitlRequest.id,
          thread_id: hitlRequest.threadId,
        },
      };
      await api.post('/gateway/api/v1/message/send', {
        target_device_key: activeDeviceKey,
        envelope,
      });

      setHitlRequest(null);
    } catch (error: any) {
      onError?.(error);
    }
  }, [hitlRequest, token, onError, setHitlRequest]);


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
