/**
 * MessageAdapter — Agent 消息到 Mobile UI 的适配器。
 *
 * 将原来内嵌在 conversationStore.ts 和 ChatScreen.tsx 中的
 * 消息转换、去重、HITL 解析逻辑提取为纯函数，便于复用和测试。
 */

import { ChatMessage } from '@/types/conversation';
import { HumanRequest } from '@/types/hitl';
import { AgentSyncMessage } from '@/services/gateway/agentMessage';

/**
 * 将 Agent 推送的单条消息转换为 Mobile ChatMessage
 */
export function adaptAgentMessage(raw: AgentSyncMessage): ChatMessage {
  return {
    id: String(raw.id || raw.sequence_number || Date.now()),
    role:
      raw.role === 'human'
        ? 'user'
        : raw.role === 'ai'
          ? 'assistant'
          : 'system',
    content: raw.content || '',
    timestamp: (raw.created_at || 0) * 1000, // Agent 秒级 → Mobile 毫秒级
    isComplete: raw.status === 'completed' || raw.status === 'done',
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
 * 从 Agent 消息中解析 HITL 请求。
 *
 * 当前实现：HITL 信息 JSON.stringify 后放在 content 字段中（协议 v1）。
 * 未来协议 v2 将改为直接从 msg.hitl 字段读取。
 */
export function parseHITLRequest(msg: AgentSyncMessage): HumanRequest | null {
  if (msg.action_type !== 'human_request' && msg.status !== 'waiting_human') {
    return null;
  }

  try {
    const content = JSON.parse(msg.content || '{}');
    return {
      id: content.id || msg.id || `hitl-${Date.now()}`,
      type: content.type || 'text',
      prompt: content.prompt || '需要您的输入',
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
  return rawMessages
    .filter((m) => m.is_visible !== 0)
    .map(adaptAgentMessage);
}
