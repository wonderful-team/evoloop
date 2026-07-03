/**
 * MessageAdapter — Agent 消息到 Mobile UI 的适配器。
 *
 * 将原来内嵌在 conversationStore.ts 和 ChatScreen.tsx 中的
 * 消息转换、去重、HITL 解析逻辑提取为纯函数，便于复用和测试。
 *
 * 时间戳规范化策略（统一以 Python Backend 为准）：
 * - WS 推送 (AgentSyncMessage)：created_at 为 ISO 8601 字符串 → 解析为毫秒
 * - HTTP 拉取 (PHP API)：create_time 为 Unix 秒级整数 → 乘以 1000 转为毫秒
 */

import i18n from '@/locales';
import { ChatMessage } from '@/types/conversation';
import { HumanRequest } from '@/types/hitl';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';

/**
 * 标准化后端发送的 references 数组。
 * 将后端 ReferenceBlock 的 target_id / target_name 映射为移动端 MessageReference 的 id / name / detail。
 */
export function adaptReferences(refs: Array<Record<string, any>> | null | undefined): Array<Record<string, any>> | undefined {
  if (!refs || !Array.isArray(refs) || refs.length === 0) return undefined;
  return refs.map(ref => ({
    ...ref,
    id: String(ref.id || ref.target_id || `ref-${Date.now()}`),
    name: String(ref.name || ref.target_name || ref.title || 'Reference'),
    detail: String(ref.detail || (ref.meta_data ? typeof ref.meta_data === 'string' ? ref.meta_data : JSON.stringify(ref.meta_data) : '')),
  }));
}



/**
 * 统一时间戳规范化。
 * 兼容三种来源：
 *   1. ISO 8601 字符串 (Python WS 推送)："2024-01-15T10:30:00+08:00"
 *   2. Unix 秒级整数 (PHP HTTP 拉取)：1705284600
 *   3. 毫秒级整数（已规范化，直接使用）
 */
export function normalizeTimestamp(value: string | number | null | undefined): number {
  if (!value) return Date.now();

  if (typeof value === 'string') {
    // ISO 8601 → parse → milliseconds
    const ms = Date.parse(value);
    return isNaN(ms) ? Date.now() : ms;
  }

  // Number: 秒级 (10位) → 乘以1000; 毫秒级 (13位) → 直接使用
  if (value < 1e12) {
    return value * 1000;
  }
  return value;
}

/**
 * 将 Agent 推送的单条消息转换为 Mobile ChatMessage
 * 对齐 Python MessageBlock 的完整字段。
 */
export function adaptAgentMessage(raw: AgentSyncMessage): ChatMessage {
  return {
    id: String(raw.id || raw.sequence_number || Date.now()),
    role: raw.role === 'human' || raw.role === 'ai' || raw.role === 'tool' || raw.role === 'system' ? raw.role : 'system',
    content: raw.content || '',
    thinking: raw.thinking ?? undefined,
    timestamp: normalizeTimestamp(raw.created_at),  // ISO 8601 → ms
    isComplete:
      raw.status === 'completed' ||
      raw.status === 'failed' ||
      raw.status === 'waiting_human',
    status: raw.status ?? 'completed',
    // 工具消息专属字段
    tool_name: raw.tool_name ?? undefined,
    tool_call_id: raw.tool_call_id ?? undefined,
    tool_meta: raw.tool_meta ?? raw.meta_data?.tool_meta ?? undefined,
    tool_calls: raw.tool_calls ?? undefined,
    // 元数据透传
    category: raw.category ?? undefined,
    sequence_number: raw.sequence_number,
    references: adaptReferences(raw.references),
  };
}

/**
 * 规范化 PHP API 返回的历史消息（HTTP 拉取路径）
 * 处理 create_time（秒级 Unix）→ timestamp（毫秒级）
 */
export function adaptHistoryMessage(raw: Record<string, any>): ChatMessage {
  return {
    id: String(raw.id || raw.sequence_number || Date.now()),
    role: raw.role === 'human' || raw.role === 'ai' || raw.role === 'tool' || raw.role === 'system' ? raw.role : 'system',
    content: raw.content || '',
    thinking: raw.thinking ?? undefined,
    // PHP 返回 create_time (Unix 秒) 或 created_at (ISO 8601 字符串)，统一处理
    timestamp: normalizeTimestamp(raw.created_at || raw.create_time),
    isComplete: raw.status === 'completed' || !raw.status,
    status: raw.status ?? 'completed',
    tool_name: raw.tool_name ?? undefined,
    tool_calls: Array.isArray(raw.tool_calls)
      ? raw.tool_calls
      : (raw.tool_calls ? JSON.parse(raw.tool_calls) : undefined),
    tool_meta: (() => {
      if (raw.tool_meta) return typeof raw.tool_meta === 'string' ? JSON.parse(raw.tool_meta) : raw.tool_meta;
      if (raw.meta_data) {
        try {
          const meta = typeof raw.meta_data === 'string' ? JSON.parse(raw.meta_data) : raw.meta_data;
          return meta.tool_meta;
        } catch (e) {
          console.warn('[MessageAdapter] Failed to parse meta_data:', e);
        }
      }
      return undefined;
    })(),
    has_file_operations: raw.has_file_operations ?? false,
    references: adaptReferences(raw.references),
    category: raw.category ?? undefined,
    sequence_number: raw.sequence_number ?? undefined,
  };
}

/**
 * 过滤掉已存在的消息（基于 id 去重）
 */
export function deduplicateMessages(
  existing: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const existingIds = new Set(existing.map((m) => m.id));
  return incoming.filter((m) => !existingIds.has(m.id));
}

/**
 * 将后端同步的 human 消息与本地乐观更新的临时 human 消息合并，避免重复显示。
 *
 * 匹配规则：
 * - role 为 human
 * - content 完全一致（引用内容已参与 finalText 构造）
 * - 本地消息没有 sequence_number（临时消息）
 * - 本地消息状态为 running/sent
 *
 * 命中后，用后端真实消息替换本地临时消息，状态修正为 completed。
 */
export function mergeSyncedHumanMessages(
  existing: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const result = [...existing];
  const consumedTempIndexes = new Set<number>();

  for (const msg of incoming) {
    if (msg.role !== 'human') {
      const idx = result.findIndex((m) => m.id === msg.id);
      if (idx !== -1) {
        result[idx] = {
          ...result[idx],
          ...msg,
          thinking: msg.thinking !== undefined ? msg.thinking : result[idx].thinking,
          tool_name: msg.tool_name !== undefined ? msg.tool_name : result[idx].tool_name,
          tool_call_id: msg.tool_call_id !== undefined ? msg.tool_call_id : result[idx].tool_call_id,
          tool_meta: msg.tool_meta !== undefined ? msg.tool_meta : result[idx].tool_meta,
          tool_calls: msg.tool_calls !== undefined ? msg.tool_calls : result[idx].tool_calls,
          category: msg.category !== undefined ? msg.category : result[idx].category,
          sequence_number: msg.sequence_number !== undefined ? msg.sequence_number : result[idx].sequence_number,
          references: msg.references !== undefined ? msg.references : result[idx].references,
        };
      } else {
        result.push(msg);
      }
      continue;
    }

    // 1. 优先通过 Gateway 返回的 message_id（id）匹配
    let tempIndex = result.findIndex(
      (m, idx) => {
        return (
          !consumedTempIndexes.has(idx) &&
          m.role === 'human' &&
          m.id === msg.id &&
          !m.sequence_number
        );
      },
    );

    // 3. 最终兜底：基于内容模糊匹配（兼容旧版本或第三方发送场景）
    if (tempIndex === -1) {
      tempIndex = result.findIndex(
        (m, idx) => {
          const status = m.status as string | undefined;
          return (
            !consumedTempIndexes.has(idx) &&
            m.role === 'human' &&
            m.content === msg.content &&
            (status === 'running' || status === 'sent' || status === 'sending' || status === 'awaiting_delivered') &&
            !m.sequence_number
          );
        },
      );
    }

    if (tempIndex >= 0) {
      result[tempIndex] = { ...msg, status: 'completed' };
      consumedTempIndexes.add(tempIndex);
    } else if (!result.some((m) => m.id === msg.id)) {
      result.push({ ...msg, status: 'completed' });
    }
  }

  return result;
}

/**
 * 从 Agent 消息或规范 hitl.request body 中解析 HITL 请求。
 *
 * 支持两种格式：
 * 1. 旧版：HITL 信息 JSON.stringify 后放在 AgentSyncMessage.content 中。
 * 2. 规范：直接传入 hitl.request envelope body（含 request_id/request_type）。
 */
export function parseHITLRequest(msg: AgentSyncMessage | Record<string, any>): HumanRequest | null {
  // 规范格式（hitl.request envelope body）
  if ('request_id' in msg && 'request_type' in msg) {
    const body = msg as Record<string, any>;
    return {
      id: body.request_id || `hitl-${Date.now()}`,
      threadId: body.thread_id || '',
      type: body.request_type || 'text',
      prompt: body.prompt || i18n.t('hitl.defaultPrompt'),
      options: body.options,
      default_value: body.default_value,
      context: body.context,
      risk_level: body.metadata?.risk_level,
      timestamp: Date.now(),
      timeout: body.metadata?.timeout,
    };
  }

  // 旧版 AgentSyncMessage 格式
  const legacy = msg as AgentSyncMessage;
  if (legacy.action_type !== 'human_request' && legacy.status !== 'waiting_human') {
    return null;
  }

  try {
    const content = JSON.parse(legacy.content || '{}');
    return {
      id: content.id || legacy.id || `hitl-${Date.now()}`,
      threadId: legacy.thread_id || '',
      type: content.type || 'text',
      prompt: content.prompt || i18n.t('hitl.defaultPrompt'),
      options: content.options,
      default_value: content.default_value,
      context: content.context,
      risk_level: content.risk_level,
      timestamp: Date.now(),
      timeout: content.timeout,
    };
  } catch (e) {
    console.warn('[MessageAdapter] Failed to parse HITL content:', e);
    return null;
  }
}

/**
 * 批量适配 Agent 消息为 ChatMessage，并过滤不可见消息。
 */
export function adaptAgentMessages(
  rawMessages: AgentSyncMessage[],
): ChatMessage[] {
  return rawMessages.map(adaptAgentMessage);
}

