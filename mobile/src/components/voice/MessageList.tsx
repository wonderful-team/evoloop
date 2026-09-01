// 语音对话消息列表 - 文档列表样式

import React, { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Text, Menu, Divider } from 'react-native-paper';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { ChatMessage } from '@/types/conversation';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { MessageContent, ChangesetSnapshot, ResourceChip, MessageReferences } from '@/components/chat';
import { HumanRequestCard } from '@/components/hitl';
import { useConversationStore } from '@/stores/conversationStore';

import { shareChatMessage } from '@/utils/share';
import Clipboard from '@react-native-clipboard/clipboard';

interface MessageListProps {
  onRewind?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  onQuote?: (message: ChatMessage) => void;
  onForward?: (message: ChatMessage) => void;
  onAddToMemory?: (text: string, messageId?: string) => void;
  onRemoveFromMemory?: (text: string, messageId?: string) => void;
  onResend?: (message: ChatMessage) => void;
  /** 是否显示 AI 思考中指示器 */
  isTyping?: boolean;
}

// 获取角色图标名
function getRoleIcon(role: string): string {
  switch (role) {
    case 'human': return 'account';
    case 'ai': return 'robot';
    case 'system': return 'information';
    case 'tool': return 'wrench';
    default: return 'help-circle';
  }
}

// 获取角色颜色
function getRoleColor(role: string, colors: any): string {
  switch (role) {
    case 'human': return colors.primary;
    case 'ai': return colors.secondary;
    case 'system': return colors.onSurfaceVariant;
    case 'tool': return colors.info;
    default: return colors.onSurfaceVariant;
  }
}


// 单条消息组件 - 用 React.memo 包装
const MessageItem = React.memo(function MessageItem({
  message,
  isUser,
  colors,
  inStepsGroup = false,
  onRewind,
  onRetry,
  onQuote,
  onForward,
  onAddToMemory,
  onRemoveFromMemory,
  onResend,
}: {
  message: ChatMessage;
  isUser: boolean;
  colors: any;
  inStepsGroup?: boolean;
  onRewind?: (id: string) => void;
  onRetry?: (id: string) => void;
  onQuote?: (msg: ChatMessage) => void;
  onForward?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string, messageId?: string) => void;
  onRemoveFromMemory?: (text: string, messageId?: string) => void;
  onResend?: (msg: ChatMessage) => void;
}) {
  const isStreaming = message.status === 'streaming' || message.status === 'running';
  const [menuVisible, setMenuVisible] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(isStreaming);
  const { t } = useTranslation();

  useEffect(() => {
    if (isStreaming) {
      setThinkingExpanded(true);
    }
  }, [isStreaming]);

  const isHITL = message.category === 'human_request';
  const parsedHITL = useMemo(() => {
    if (isHITL && message.content) {
      try {
        const parsed = JSON.parse(message.content);
        return {
          id: parsed.id || message.id,
          type: parsed.type || 'text',
          prompt: parsed.prompt || '',
          options: parsed.options,
          default_value: parsed.default_value,
          context: parsed.context,
          risk_level: parsed.risk_level,
          timestamp: Date.now(),
          timeout: parsed.timeout,
        };
      } catch (e) {
        return null;
      }
    }
    return null;
  }, [isHITL, message.content, message.id]);


  const handleCopy = useCallback(() => {
    Clipboard.setString(message.content);
    setMenuVisible(false);
  }, [message.content]);

  const handleRewind = useCallback(() => {
    onRewind?.(message.id);
    setMenuVisible(false);
  }, [message.id, onRewind]);

  const handleRetry = useCallback(() => {
    onRetry?.(message.id);
    setMenuVisible(false);
  }, [message.id, onRetry]);

  const handleQuote = useCallback(() => {
    onQuote?.(message);
    setMenuVisible(false);
  }, [message, onQuote]);

  const handleAddToMemory = useCallback(() => {
    onAddToMemory?.(message.content, message.id);
    setMenuVisible(false);
  }, [message.content, message.id, onAddToMemory]);

  const handleRemoveFromMemory = useCallback(() => {
    onRemoveFromMemory?.(message.content, message.id);
    setMenuVisible(false);
  }, [message.content, message.id, onRemoveFromMemory]);

  const isRemembered = message.is_remembered;

  const handleMemoryAction = useCallback(() => {
    if (isRemembered) {
      handleRemoveFromMemory();
    } else {
      handleAddToMemory();
    }
  }, [isRemembered, handleAddToMemory, handleRemoveFromMemory]);

  const handleForward = useCallback(() => {
    onForward?.(message);
    setMenuVisible(false);
  }, [message, onForward]);

  const handleShare = useCallback(async () => {
    const sender = isUser ? t('chat.messageList.me') : t('chat.messageList.ai');
    await shareChatMessage(message.content, sender);
    setMenuVisible(false);
  }, [message.content, isUser, t]);

  const roleIcon = getRoleIcon(message.role);
  const roleColor = getRoleColor(message.role, colors);

  // ── 工具消息：紧凑单行（对齐桌面端设计）
  if (message.role === 'tool') {
    const toolLabel = message.tool_meta?.display_name || message.tool_name || 'TOOL';
    const isRunning = message.status === 'running';
    return (
      <View style={[styles.toolRow, inStepsGroup && styles.inStepsGroupToolRow]}>
        {!inStepsGroup ? (
          <>
            <View style={[styles.toolSpine, { backgroundColor: colors.outline }]} />
            <View style={styles.toolContent}>
              <View style={[styles.toolDot, { backgroundColor: colors.outline }]} />
              <Text
                numberOfLines={1}
                style={[styles.toolLabel, { color: colors.onSurfaceVariant }]}
              >
                {toolLabel}
              </Text>
              {isRunning && (
                <ActivityIndicator size={10} color={colors.primary} style={{ marginLeft: 4, opacity: 0.6 }} />
              )}
            </View>
          </>
        ) : (
          <>
            <View style={[
              styles.inStepsGroupTimelineDot,
              { backgroundColor: isRunning ? colors.primary : colors.onSurfaceVariant }
            ]} />
            <View style={styles.toolContent}>
              <Text
                numberOfLines={1}
                style={[styles.toolLabel, { color: colors.onSurfaceVariant }, isRunning && { color: colors.primary, fontWeight: '500' }]}
              >
                {toolLabel}
              </Text>
              {isRunning && (
                <ActivityIndicator size={10} color={colors.primary} style={{ marginLeft: 4, opacity: 0.8 }} />
              )}
            </View>
          </>
        )}
      </View>
    );
  }

  return (
    <Menu
      visible={menuVisible}
      onDismiss={() => setMenuVisible(false)}
      anchor={
        <TouchableOpacity
          activeOpacity={0.8}
          onLongPress={() => setMenuVisible(true)}
        >
          <View style={[
            styles.messageItem,
            isUser && { backgroundColor: colors.primaryContainer },
            inStepsGroup && styles.inStepsGroupMessageItem,
          ]}>
            {/* 角色图标水印 - 融入背景右下角 */}
            <View style={styles.watermark}>
              <MaterialCommunityIcons
                name={roleIcon}
                size={48}
                color={roleColor}
                style={{ opacity: 0.1 }}
              />
            </View>

            {/* 消息内容 */}
            <View style={styles.messageBody}>
              {/* Thinking 折叠区域（对齐桌面端 Collapsible Brain 设计） */}
              {!isUser && !!(message as any).thinking && (
                <TouchableOpacity
                  onPress={() => setThinkingExpanded(v => !v)}
                  style={styles.thinkingHeader}
                  activeOpacity={0.7}
                >
                  <MaterialIcons name="psychology" size={13} color={colors.onSurfaceVariant} style={{ opacity: 0.7 }} />
                  <Text style={[styles.thinkingHeaderText, { color: colors.onSurfaceVariant }]}>
                    {t('chat.messageList.thinkingProcess')}
                  </Text>
                  <MaterialIcons
                    name={thinkingExpanded ? 'expand-less' : 'expand-more'}
                    size={14}
                    color={colors.onSurfaceVariant}
                    style={{ opacity: 0.7 }}
                  />
                </TouchableOpacity>
              )}
              {!isUser && thinkingExpanded && !!(message as any).thinking && (
                <View style={[
                  styles.thinkingBody,
                  { borderLeftColor: colors.outline },
                  inStepsGroup && styles.inStepsGroupThinkingBody,
                ]}>
                  <MessageContent
                    content={(message as any).thinking}
                    isUser={false}
                  />
                </View>
              )}

              {/* 引用消息 (排除文件、图片、音频) */}
              {message.references && message.references.length > 0 && (
                <View style={styles.referencesContainer}>
                  {message.references
                    .filter((ref: any) => !['file', 'image', 'audio'].includes(ref.type))
                    .map((ref: any, idx: number) => (
                      <ResourceChip key={idx} reference={ref} isUser={isUser} />
                    ))}
                </View>
              )}

              {/* 附件/文件 (用户消息：挪到上方) */}
              {isUser && message.references && message.references.some((ref: any) => ['file', 'image', 'audio'].includes(ref.type)) && (
                <MessageReferences
                  references={message.references.filter((ref: any) => ['file', 'image', 'audio'].includes(ref.type))}
                  isUser={isUser}
                />
              )}

              {isHITL && parsedHITL ? (
                <HumanRequestCard
                  request={parsedHITL}
                  onRespond={() => {}}
                  disabled={true}
                />
              ) : (
                <MessageContent content={message.content} isUser={isUser} isStreaming={isStreaming} />
              )}

              {/* 附件/文件 (AI 消息：保持在下方) */}
              {!isUser && message.references && message.references.some((ref: any) => ['file', 'image', 'audio'].includes(ref.type)) && (
                <MessageReferences
                  references={message.references.filter((ref: any) => ['file', 'image', 'audio'].includes(ref.type))}
                  isUser={isUser}
                />
              )}

              {/* 文件变更快照 (Changeset Snapshot) */}
              {!isUser && (message.changeset_count ?? 0) > 0 && (
                <ChangesetSnapshot
                  files={message.changeset_files || []}
                  totalCount={message.changeset_count || 0}
                  onViewDetails={(path) => {
                    // 后续可对接查看 Diff 的逻辑
                    console.log('View changeset:', path);
                  }}
                />
              )}

              {/* 执行用时 */}
              {!isUser && (message as any).isLastInTurn && !!(message as any).turnDuration && (
                <View style={styles.aiFooter}>
                  <Text variant="labelSmall" style={[styles.aiFooterText, { color: colors.onSurfaceVariant }]}>
                    {t('chat.messageList.duration')}: {(message as any).turnDuration}
                  </Text>
                </View>
              )}

            </View>

            {/* 发送状态指示器 */}
            {isUser && message.status && message.status !== 'sent' && (
              <View style={styles.statusRow}>
                {(message.status === 'running' || message.status === 'streaming' || message.status === 'pending') && (
                  <>
                    <ActivityIndicator size={12} color={colors.onSurfaceVariant} />
                    <Text variant="bodySmall" style={{ marginLeft: 4, color: colors.onSurfaceVariant }}>
                      {t('chat.messageList.sending')}
                    </Text>
                  </>
                )}
                {message.status === 'failed' && (
                  <TouchableOpacity
                    onPress={() => onResend?.(message)}
                    style={styles.resendBtn}
                  >
                    <MaterialIcons name="error-outline" size={14} color={colors.error} />
                    <Text variant="bodySmall" style={{ marginLeft: 4, color: colors.error }}>
                      {t('chat.messageList.sendFailedRetry')}
                    </Text>
                  </TouchableOpacity>
                )}
                {message.status === 'timeout' && (
                  <TouchableOpacity
                    onPress={() => onResend?.(message)}
                    style={styles.resendBtn}
                  >
                    <MaterialIcons name="timer-off" size={14} color={colors.error} />
                    <Text variant="bodySmall" style={{ marginLeft: 4, color: colors.error }}>
                      {t('chat.messageList.sendTimeoutRetry')}
                    </Text>
                  </TouchableOpacity>
                )}
                {message.status === 'awaiting_delivered' && (
                  <MaterialIcons name="access-time" size={12} color={colors.onSurfaceVariant} />
                )}
              </View>
            )}
          </View>
        </TouchableOpacity>
      }
    >
      <Menu.Item
        onPress={handleCopy}
        title={t('chat.messageActions.copy')}
        leadingIcon={props => <MaterialIcons {...props} name="content-copy" />}
      />
      {isUser && onRewind && (
        <Menu.Item
          onPress={handleRewind}
          title={t('chat.messageActions.rewind')}
          leadingIcon={props => <MaterialIcons {...props} name="undo" />}
        />
      )}
      {isUser && onRetry && (
        <Menu.Item
          onPress={handleRetry}
          title={t('chat.messageActions.retry')}
          leadingIcon={props => <MaterialIcons {...props} name="refresh" />}
        />
      )}
      {onQuote && (
        <Menu.Item
          onPress={handleQuote}
          title={t('chat.messageActions.quote')}
          leadingIcon={props => <MaterialIcons {...props} name="format-quote" />}
        />
      )}
      {onForward && (
        <Menu.Item
          onPress={handleForward}
          title={t('chat.messageActions.forward')}
          leadingIcon={props => <MaterialIcons {...props} name="share" />}
        />
      )}
      <Menu.Item
        onPress={handleShare}
        title={t('chat.messageActions.share')}
        leadingIcon={props => <MaterialIcons {...props} name="ios-share" />}
      />
      {onAddToMemory && onRemoveFromMemory && (
        <Menu.Item
          onPress={handleMemoryAction}
          title={isRemembered ? t('chat.messageActions.removeFromMemory') : t('chat.messageActions.addToMemory')}
          leadingIcon={props => <MaterialIcons {...props} name={isRemembered ? 'psychology' : 'psychology-alt'} />}
        />
      )}
    </Menu>


  );
}, (prev, next) => {
  // 只比较影响渲染的 props
  return prev.message === next.message &&
    prev.isUser === next.isUser &&
    prev.colors === next.colors;
});

export type RenderItem =
  | { type: 'message'; data: ChatMessage }
  | { type: 'steps_group'; id: string; steps: ChatMessage[]; isTurnActive: boolean };

function mergeAiMessages(msgs: ChatMessage[]): ChatMessage | null {
  if (msgs.length === 0) return null;
  const first = msgs[0];
  const last = msgs[msgs.length - 1];

  const paragraphs = msgs.map((m) => m.content?.trim()).filter(Boolean);

  return {
    ...first,
    content: paragraphs.join('\n\n'),
    thinking:
      msgs
        .map((m) => m.thinking)
        .filter(Boolean)
        .join('\n\n') || undefined,
    status: msgs.some((m) => m.status === 'streaming')
      ? 'streaming'
      : last.status || 'completed',
    changeset_count: msgs.reduce((sum, m) => sum + (m.changeset_count || 0), 0),
    changeset_files: msgs.reduce(
      (all, m) => [...all, ...(m.changeset_files || [])],
      [] as any[],
    ),
    has_file_operations: msgs.some((m) => m.has_file_operations),
    timestamp: last.timestamp || first.timestamp,
    references: msgs.reduce(
      (all, m) => [...all, ...(m.references || [])],
      [] as any[],
    ),
  };
}

function groupMessages(messages: ChatMessage[], t: TFunction): RenderItem[] {
  // Filter out system messages
  const filtered = messages.filter(m => m.role !== 'system');

  const items: {
    type: 'message';
    data: ChatMessage & {
      isFirstInTurn?: boolean;
      isLastInTurn?: boolean;
    };
  }[] = [];

  let turnMsgs: ChatMessage[] = [];

  const flushTurn = () => {
    if (turnMsgs.length === 0) return;

    let isFirstAiInTurn = true;
    let pendingAiGroup: ChatMessage[] = [];

    const flushPendingAi = (isFinalInTurn: boolean) => {
      if (pendingAiGroup.length === 0) return;
      const merged = mergeAiMessages(pendingAiGroup);
      if (merged) {
        items.push({
          type: 'message',
          data: {
            ...merged,
            isFirstInTurn: isFirstAiInTurn,
            ...(isFinalInTurn ? { isLastInTurn: true } : {}),
          } as any,
        });
        isFirstAiInTurn = false;
      }
      pendingAiGroup = [];
    };

    for (let j = 0; j < turnMsgs.length; j++) {
      const m = turnMsgs[j];
      if (m.role === 'ai') {
        pendingAiGroup.push(m);
        const nextM = turnMsgs[j + 1];
        if (!nextM || nextM.role !== 'ai') {
          const isFinalInTurn = j === turnMsgs.length - 1;
          flushPendingAi(isFinalInTurn);
        }
      } else if (m.role === 'tool') {
        items.push({
          type: 'message',
          data: { ...m, isFirstInTurn: false } as any,
        });
      }
    }
    turnMsgs = [];
  };

  let isNewAiTurn = true;

  for (let i = 0; i < filtered.length; i++) {
    const msg = filtered[i];

    if (msg.role === 'human') {
      flushTurn();
      items.push({ type: 'message', data: msg });
      isNewAiTurn = true;
    } else if (msg.role === 'ai' || msg.role === 'tool') {
      if (isNewAiTurn && msg.role === 'ai') {
        turnMsgs.push({ ...msg, isFirstInTurn: true } as any);
        isNewAiTurn = false;
      } else {
        turnMsgs.push(msg);
      }
    }
  }
  flushTurn();

  // ─── 第二步：计算每个 turn 的 duration 并标记 ─────────────────────────────
  const getItemTimestamp = (itm: any): string | undefined => {
    if (!itm) return undefined;
    if (itm.data?.timestamp) return itm.data.timestamp;
    return undefined;
  };

  let turnStartIndex = 0;
  let turnFirstAiIndex = -1;
  let turnLastAiIndex = -1;
  let lastAiContentInTurn = '';

  const closeTurn = () => {
    if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
      (items[turnFirstAiIndex].data as any).effective_content =
        lastAiContentInTurn;
    }
    if (turnLastAiIndex !== -1) {
      const lastAiItem = items[turnLastAiIndex];
      const firstItem = items[turnStartIndex];
      const firstTs = getItemTimestamp(firstItem);
      const lastTs = getItemTimestamp(lastAiItem);
      if (firstTs && lastTs) {
        const startMs = new Date(firstTs).getTime();
        const endMs = new Date(lastTs).getTime();
        if (
          !Number.isNaN(startMs) &&
          !Number.isNaN(endMs) &&
          endMs >= startMs
        ) {
          const diffSec = (endMs - startMs) / 1000;
          (lastAiItem.data as any).turnDuration =
            diffSec >= 1
              ? t('common.durationSeconds', { value: diffSec.toFixed(1) })
              : t('common.durationMilliseconds', { value: Math.round(endMs - startMs) });
        }
      }
    }
  };

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.data.role === 'human') {
      closeTurn();
      turnStartIndex = i;
      turnFirstAiIndex = -1;
      turnLastAiIndex = -1;
      lastAiContentInTurn = '';
    } else if (item.data.role === 'ai') {
      if ((item.data as any).isFirstInTurn) {
        closeTurn();
        turnStartIndex = i;
        turnFirstAiIndex = i;
        turnLastAiIndex = i;
        lastAiContentInTurn = item.data.content || '';
      } else if ((item.data as any).isLastInTurn) {
        turnLastAiIndex = i;
        if (item.data.content && item.data.content.trim() !== '') {
          lastAiContentInTurn = item.data.content;
        }
      }
    }
  }
  closeTurn();

  // ─── 第三步：把中间步骤归入 steps_group ─────────────────────────────
  const groupedItems: RenderItem[] = [];
  let currentTurnSteps: ChatMessage[] = [];

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.data.role === 'human') {
      if (currentTurnSteps.length > 0) {
        groupedItems.push({
          type: 'steps_group',
          id: `steps_group_before_${item.data.id}`,
          steps: [...currentTurnSteps],
          isTurnActive: false,
        });
        currentTurnSteps = [];
      }
      groupedItems.push(item);
    } else if ((item.data as any).isLastInTurn) {
      const isStreaming =
        item.data.status === 'streaming' ||
        item.data.status === 'running' ||
        item.data.status === 'pending';

      if (item.data.thinking) {
        currentTurnSteps.push({
          id: `${item.data.id}_thinking`,
          role: 'ai',
          content: '',
          thinking: item.data.thinking,
          timestamp: item.data.timestamp,
          status: item.data.status,
        } as any);
      }

      if (currentTurnSteps.length > 0) {
        groupedItems.push({
          type: 'steps_group',
          id: `steps_group_${item.data.id}`,
          steps: [...currentTurnSteps],
          isTurnActive: isStreaming,
        });
        currentTurnSteps = [];
      }

      groupedItems.push({
        ...item,
        data: { ...item.data, thinking: undefined },
      });
    } else {
      // 中间步骤（AI tool_call、tool_output、未标 isLastInTurn 的 AI 消息）全进 steps
      // 排除 HITL 卡片（作为独立节点渲染，但不截断步骤组）
      const isHitlTool =
        item.data.category === 'human_request' ||
        (item.data.role === 'tool' &&
          (item.data.tool_name === 'ask_human' || item.data.tool_name === 'ask_confirm'));

      if (isHitlTool) {
        groupedItems.push(item);
      } else {
        currentTurnSteps.push(item.data);
      }
    }
  }

  if (currentTurnSteps.length > 0) {
    const isTailActive = currentTurnSteps.some(s =>
      s.status === 'streaming' || s.status === 'running' || s.status === 'pending'
    );

    groupedItems.push({
      type: 'steps_group',
      id: `steps_group_tail_${currentTurnSteps[0].id}`,
      steps: [...currentTurnSteps],
      isTurnActive: isTailActive,
    });
  }

  return groupedItems;
}

const TurnStepsGroupView = React.memo(function TurnStepsGroupView({
  steps,
  isTurnActive,
  colors,
  onRewind,
  onRetry,
  onQuote,
  onForward,
  onAddToMemory,
  onRemoveFromMemory,
  onResend,
}: {
  steps: ChatMessage[];
  isTurnActive: boolean;
  colors: any;
  onRewind?: (id: string) => void;
  onRetry?: (id: string) => void;
  onQuote?: (msg: ChatMessage) => void;
  onForward?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string, messageId?: string) => void;
  onRemoveFromMemory?: (text: string, messageId?: string) => void;
  onResend?: (msg: ChatMessage) => void;
}) {
  const [expanded, setExpanded] = useState(isTurnActive || false);
  const { t } = useTranslation();

  useEffect(() => {
    setExpanded(isTurnActive || false);
  }, [isTurnActive]);

  return (
    <View style={styles.stepsGroupContainer}>
      <TouchableOpacity
        onPress={() => setExpanded(v => !v)}
        style={[styles.stepsHeader, { backgroundColor: colors.surfaceVariant + '40' }]}
        activeOpacity={0.7}
      >
        <MaterialIcons name="layers" size={16} color={colors.primary} style={{ marginRight: 6 }} />
        <Text style={[styles.stepsHeaderText, { color: colors.onSurfaceVariant }]}>
          {t('chat.messageList.executionSteps')} ({steps.length})
        </Text>
        {isTurnActive && (
          <ActivityIndicator size={12} color={colors.primary} style={{ marginRight: 6 }} />
        )}
        <MaterialIcons
          name={expanded ? 'expand-less' : 'expand-more'}
          size={16}
          color={colors.onSurfaceVariant}
        />
      </TouchableOpacity>
      {expanded && (
        <View style={[styles.stepsContentList, { borderLeftColor: colors.outline + '30' }]}>
          {steps.map((stepMsg) => {
            return (
              <MessageItem
                key={stepMsg.id}
                message={stepMsg}
                isUser={false}
                inStepsGroup={true}
                colors={colors}
                onRewind={onRewind}
                onRetry={onRetry}
                onQuote={onQuote}
                onForward={onForward}
                onAddToMemory={onAddToMemory}
                onRemoveFromMemory={onRemoveFromMemory}
                onResend={onResend}
              />
            );
          })}
        </View>
      )}
    </View>
  );
});

export interface MessageListProps {
  onRewind?: (id: string) => void;
  onRetry?: (id: string) => void;
  onQuote?: (msg: ChatMessage) => void;
  onForward?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string, messageId?: string) => void;
  onRemoveFromMemory?: (text: string, messageId?: string) => void;
  onResend?: (msg: ChatMessage) => void;
  isTyping: boolean;
  hasMoreMessages: boolean;
  isLoadingMessages: boolean;
}

export const MessageList = React.memo(function MessageList({
  onRewind, onRetry, onQuote, onForward, onAddToMemory, onRemoveFromMemory, onResend, isTyping, hasMoreMessages, isLoadingMessages
}: MessageListProps) {
  const messages = useConversationStore((state) => state.messages);
  const { colors } = useTheme();
  const { t } = useTranslation();
  const flatListRef = useRef<FlatList>(null);
  const isUserAtBottomRef = useRef(true);
  const shouldScrollToBottomRef = useRef(false);
  const listHeightRef = useRef<number>(0);
  const contentHeightRef = useRef<number>(0);
  const scrollOffsetRef = useRef<number>(0);

  // Group messages
  const groupedMessages = useMemo(() => groupMessages(messages, t), [messages, t]);

  // 监听新增加的用户消息，触发强制滚动
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'human') {
        shouldScrollToBottomRef.current = true;
        flatListRef.current?.scrollToEnd({ animated: true });

        const timer = setTimeout(() => {
          shouldScrollToBottomRef.current = false;
        }, 500);
        return () => clearTimeout(timer);
      }
    }
  }, [messages]);

  // 当 AI 开始思考或输入时，触发强制滚动
  useEffect(() => {
    if (isTyping) {
      shouldScrollToBottomRef.current = true;
      flatListRef.current?.scrollToEnd({ animated: true });

      const timer = setTimeout(() => {
        shouldScrollToBottomRef.current = false;
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isTyping]);

  // 自动加载探测及随动滚动的辅助函数
  const checkAndLoadMore = useCallback(() => {
    if (isLoadingMessages || !hasMoreMessages) return;
    const listH = listHeightRef.current;
    const contentH = contentHeightRef.current;
    const offsetY = scrollOffsetRef.current;
    if (listH > 0 && contentH > 0) {
      const scrollableHeight = contentH - listH;
      if (scrollableHeight <= 0 || (offsetY / scrollableHeight) <= 0.2) {
        const { currentConversationId, loadMoreMessages } = useConversationStore.getState();
        if (currentConversationId) {
          loadMoreMessages(currentConversationId);
        }
      }
    }
  }, [isLoadingMessages, hasMoreMessages]);

  // 自动加载探测：当停止加载且还有历史时，如果列表内容不够长（比如不足满屏）或者仍然停留在顶部 20% 范围内，则继续触发加载
  useEffect(() => {
    if (!isLoadingMessages && hasMoreMessages) {
      const timer = setTimeout(checkAndLoadMore, 100);
      return () => clearTimeout(timer);
    }
  }, [isLoadingMessages, hasMoreMessages, checkAndLoadMore]);

  // 监听 AI 流式输出时的内容增长，若用户当前处于底部，则在内容大小改变时跟随滚动
  const handleContentSizeChange = useCallback((w: number, h: number) => {
    contentHeightRef.current = h;
    if (shouldScrollToBottomRef.current || (isTyping && isUserAtBottomRef.current)) {
      flatListRef.current?.scrollToEnd({ animated: true });
    }
    setTimeout(checkAndLoadMore, 100);
  }, [checkAndLoadMore, isTyping]);

  const handleLayout = useCallback((event: any) => {
    listHeightRef.current = event.nativeEvent.layout.height;
    checkAndLoadMore();
  }, [checkAndLoadMore]);

  const handleScroll = useCallback((event: any) => {
    const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
    scrollOffsetRef.current = contentOffset.y;

    // 如果滚动到顶部附近（前 20%），触发加载历史
    const scrollableHeight = contentSize.height - layoutMeasurement.height;
    if (scrollableHeight > 0 && contentOffset.y / scrollableHeight <= 0.2) {
      const { currentConversationId, loadMoreMessages, hasMoreMessages, isLoadingMessages } = useConversationStore.getState();
      if (currentConversationId && hasMoreMessages && !isLoadingMessages) {
        loadMoreMessages(currentConversationId);
      }
    }

    // 增加 paddingToBottom 阈值至 120，提高流式输出和动画更新期间的容错，避免在 auto-scroll 期间因微小偏移误判 isUserAtBottomRef.current 为 false
    const paddingToBottom = 120;
    const isAtBottom = layoutMeasurement.height + contentOffset.y >=
      contentSize.height - paddingToBottom;
    isUserAtBottomRef.current = isAtBottom;
  }, []);

  const renderMessage = useCallback((item: RenderItem) => {
    if (item.type === 'message') {
      const message = item.data;
      const isUser = message.role === 'human';

      return (
        <MessageItem
          message={message}
          isUser={isUser}
          colors={colors}
          onRewind={onRewind}
          onRetry={onRetry}
          onQuote={onQuote}
          onForward={onForward}
          onAddToMemory={onAddToMemory}
          onRemoveFromMemory={onRemoveFromMemory}
          onResend={onResend}
        />
      );
    } else {
      return (
        <TurnStepsGroupView
          steps={item.steps}
          isTurnActive={item.isTurnActive}
          colors={colors}
          onRewind={onRewind}
          onRetry={onRetry}
          onQuote={onQuote}
          onForward={onForward}
          onAddToMemory={onAddToMemory}
          onRemoveFromMemory={onRemoveFromMemory}
          onResend={onResend}
        />
      );
    }
  }, [colors, onRewind, onRetry, onQuote, onForward, onAddToMemory, onRemoveFromMemory, onResend]);

  return (
    <FlatList
      ref={flatListRef}
      style={[styles.container, { backgroundColor: colors.background }]}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
      data={groupedMessages}
      keyExtractor={(item) => (item.type === 'message' ? item.data.id : item.id)}
      renderItem={({ item }) => renderMessage(item)}
      onScroll={handleScroll}
      onLayout={handleLayout}
      onContentSizeChange={handleContentSizeChange}
      scrollEventThrottle={16}
      ListEmptyComponent={null}
      ItemSeparatorComponent={() => <Divider style={styles.divider} />}
      ListHeaderComponent={
        hasMoreMessages && isLoadingMessages ? (
          <View style={{ paddingVertical: 16, alignItems: 'center' }}>
            <ActivityIndicator size="small" color={colors.primary} />
          </View>
        ) : null
      }
      ListFooterComponent={
        isTyping ? (
          <View style={styles.typingContainer}>
            <View style={[styles.typingBubble, { backgroundColor: colors.surfaceVariant }]}>
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
            </View>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, marginTop: 4 }}>
              {t('chat.messageList.aiThinking')}
            </Text>
          </View>
        ) : null
      }
      maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
      initialNumToRender={15}
      maxToRenderPerBatch={10}
      windowSize={10}
    />
  );
}, (prev, next) => {
  return prev.onRewind === next.onRewind &&
    prev.onRetry === next.onRetry &&
    prev.onQuote === next.onQuote &&
    prev.onForward === next.onForward &&
    prev.onAddToMemory === next.onAddToMemory &&
    prev.onRemoveFromMemory === next.onRemoveFromMemory &&
    prev.onResend === next.onResend &&
    prev.isTyping === next.isTyping &&
    prev.hasMoreMessages === next.hasMoreMessages &&
    prev.isLoadingMessages === next.isLoadingMessages;
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  contentContainer: {
    flexGrow: 1,
  },
  messageList: {
    paddingVertical: 4,
  },
  // 单条消息
  messageItem: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    position: 'relative',
    overflow: 'hidden',
  },
  watermark: {
    position: 'absolute',
    right: 8,
    bottom: 4,
    zIndex: 0,
  },
  aiFooter: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 4,
    paddingRight: 4,
  },
  aiFooterText: {
    fontSize: 10,
    opacity: 0.6,
  },
  messageBody: {
    zIndex: 1,
  },
  referencesContainer: {
    marginBottom: 8,
  },
  divider: {
    marginHorizontal: 12,
    opacity: 0.3,
  },
  systemMessageContainer: {
    alignItems: 'center',
    marginVertical: 8,
  },
  systemText: {
    fontStyle: 'italic',
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    paddingLeft: 4,
  },
  resendBtn: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  // 工具消息：紧凑单行
  toolRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 5,
    paddingHorizontal: 12,
    position: 'relative',
    minHeight: 28,
  },
  toolSpine: {
    position: 'absolute',
    left: 19,
    top: 0,
    bottom: 0,
    width: 1,
    opacity: 0.3,
  },
  toolDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 10,
    opacity: 0.5,
    zIndex: 1,
    marginLeft: 4, // 调整位置使其位于 spine 中线上
  },

  toolContent: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  toolLabel: {
    fontSize: 12,
    opacity: 0.65,
    lineHeight: 16,
  },

  // Thinking 折叠
  thinkingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 4,
    marginBottom: 4,
  },
  thinkingHeaderText: {
    flex: 1,
    fontSize: 11,
    fontWeight: '600',
    opacity: 0.65,
  },
  thinkingBody: {
    borderLeftWidth: 2,
    paddingLeft: 8,
    marginBottom: 8,
    opacity: 0.7,
  },

  // Steps Group
  stepsGroupContainer: {
    marginVertical: 6,
    paddingHorizontal: 4,
  },
  stepsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 0,
    borderRadius: 8,
  },
  stepsHeaderText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '600',
  },
  stepsContentList: {
    borderLeftWidth: 1.5,
    marginLeft: 8,
    marginTop: 6,
    marginBottom: 4,
    paddingLeft: 7,
  },
  inStepsGroupMessageItem: {
    paddingHorizontal: 0,
    paddingVertical: 4,
  },
  inStepsGroupThinkingBody: {
    borderLeftWidth: 0,
    paddingLeft: 0,
  },
  inStepsGroupToolRow: {
    paddingLeft: 0,
    paddingRight: 0,
    paddingVertical: 4,
    position: 'relative',
  },
  inStepsGroupTimelineDot: {
    position: 'absolute',
    left: -11, // Centers exactly on border left line (-8px paddingLeft - 3px radius)
    top: '50%',
    marginTop: -3,
    width: 6,
    height: 6,
    borderRadius: 3,
    zIndex: 2,
  },

  typingContainer: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
  },
  typingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
    gap: 4,
  },
  typingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    opacity: 0.6,
  },
});
