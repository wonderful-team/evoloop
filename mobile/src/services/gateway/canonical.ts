/**
 * EvoLoop Canonical Message — Mobile 端规范消息类型
 *
 * 配合 Gateway Phase 1 schema 包使用。
 * 所有 WS 接收的消息优先检测是否为规范格式（存在 message_id 字段），
 * 若不是则回退到旧格式解析。
 */

import { generateUUID } from '@/utils/uuid';

// ============ Constants ============

export const CANONICAL_VERSION = '2.0';

/** 规范消息类型枚举 */
export enum CanonicalMessageType {
  Connect = 'connect',
  CommandRelay = 'command.relay',
  CommandAck = 'command.ack',
  CommandStop = 'command.stop',
  CommandRetry = 'command.retry',
  CommandRewind = 'command.rewind',
  HITLRequest = 'hitl.request',
  HITLResponse = 'hitl.response',
  HITLCancel = 'hitl.cancel',
  MessageSync = 'message.sync',
  MessageDeleted = 'message.deleted',
  MessageAck = 'message.ack',
  MemorySync = 'memory.sync',
  DeviceStatus = 'device.status',
  DeviceHeartbeat = 'device.heartbeat',
  AgentStatus = 'agent.status',
  SystemInit = 'system.init',
  SystemError = 'system.error',
}

/** 端点类型枚举 */
export enum EndpointKind {
  Mobile = 'mobile',
  Agent = 'agent',
  Gateway = 'gateway',
  Backend = 'backend',
  MC = 'mc',
}

// ============ Envelope ============

export interface CanonicalEndpoint {
  kind: EndpointKind | string;
  device_key?: string;
}

export interface CanonicalEnvelope {
  version: string;
  type: CanonicalMessageType | string;
  message_id: string;
  seq?: number;
  timestamp: number;
  source?: CanonicalEndpoint;
  target?: CanonicalEndpoint;
  body: Record<string, unknown>;
}

/**
 * 检测原始消息是否为规范 Envelope 格式。
 * 判断依据：有 version 字段且值为 "2.0"，有 message_id 字段。
 */
export function isCanonicalEnvelope(msg: unknown): msg is CanonicalEnvelope {
  if (!msg || typeof msg !== 'object') return false;
  const obj = msg as Record<string, unknown>;
  return obj.version === '2.0' && typeof obj.message_id === 'string' && !!obj.message_id;
}

// ============ Body Type Guards ============

export function isBodyType<T extends Record<string, unknown>>(
  envelope: CanonicalEnvelope,
  type: CanonicalMessageType,
): envelope is CanonicalEnvelope & { body: T } {
  return envelope.type === type;
}

// ============ Helper: 从 body 中提取 typed 字段 ============

export function getBodyAs<T>(envelope: CanonicalEnvelope): T {
  return envelope.body as unknown as T;
}

// ============ Helper: 创建出站规范 Envelope ============

function generateMessageId(): string {
  return generateUUID();
}

export function createEnvelope(
  type: string,
  body: Record<string, unknown> = {},
  target?: CanonicalEndpoint,
): CanonicalEnvelope {
  return {
    version: '2.0',
    type,
    message_id: generateMessageId(),
    timestamp: Math.floor(Date.now() / 1000),
    source: { kind: EndpointKind.Mobile },
    target,
    body,
  };
}

// 判断收到的消息是否需要回复 message.ack（排除握手、心跳、ack 自身）
export function messageTypeRequiresAck(type: string): boolean {
  switch (type) {
    case CanonicalMessageType.SystemInit:
    case CanonicalMessageType.DeviceHeartbeat:
    case CanonicalMessageType.MessageAck:
    case 'ping':
      return false;
    default:
      return true;
  }
}


