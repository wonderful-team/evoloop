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
import { MessageContent, ChangesetSnapshot, ResourceChip, MessageReferences } from '@/components/chat';
import { useConversationStore } from '@/stores/conversationStore';

import { shareChatMessage } from '@/utils/share';
import Clipboard from '@react-native-clipboard/clipboard';

interface MessageListProps {
  onRewind?: (messageId: string, hasFileOperations: boolean) => void;
  onRetry?: (messageId: string, hasFileOperations: boolean) => void;
  onQuote?: (message: ChatMessage) => void;
  onForward?: (message: ChatMessage) => void;
  onAddToMemory?: (text: string) => void;
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
// 自定义比较：忽略 hasFileOperations 变化（它不影响渲染内容，只影响菜单行为）
const MessageItem = React.memo(function MessageItem({
  message,
  isUser,
  colors,
  onRewind,
  onRetry,
  onQuote,
  onForward,
  onAddToMemory,
  onResend,
  hasFileOperations,
}: {
  message: ChatMessage;
  isUser: boolean;
  colors: any;
  onRewind?: (id: string, hasFiles: boolean) => void;
  onRetry?: (id: string, hasFiles: boolean) => void;
  onQuote?: (msg: ChatMessage) => void;
  onForward?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string) => void;
  onResend?: (msg: ChatMessage) => void;
  hasFileOperations: boolean;
}) {
  const [menuVisible, setMenuVisible] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const { t } = useTranslation();


  const handleCopy = useCallback(() => {
    Clipboard.setString(message.content);
    setMenuVisible(false);
  }, [message.content]);

  const handleRewind = useCallback(() => {
    onRewind?.(message.id, hasFileOperations);
    setMenuVisible(false);
  }, [message.id, hasFileOperations, onRewind]);

  const handleRetry = useCallback(() => {
    onRetry?.(message.id, hasFileOperations);
    setMenuVisible(false);
  }, [message.id, hasFileOperations, onRetry]);

  const handleQuote = useCallback(() => {
    onQuote?.(message);
    setMenuVisible(false);
  }, [message, onQuote]);

  const handleAddToMemory = useCallback(() => {
    onAddToMemory?.(message.content);
    setMenuVisible(false);
  }, [message.content, onAddToMemory]);

  const handleForward = useCallback(() => {
    onForward?.(message);
    setMenuVisible(false);
  }, [message, onForward]);

  const handleShare = useCallback(async () => {
    const sender = isUser ? t('chat.messageList.me') : 'AI';
    await shareChatMessage(message.content, sender);
    setMenuVisible(false);
  }, [message.content, isUser]);

  const roleIcon = getRoleIcon(message.role);
  const roleColor = getRoleColor(message.role, colors);

  // ── 工具消息：紧凑单行（对齐桌面端设计）
  if (message.role === 'tool') {
    const toolLabel = message.tool_meta?.display_name || message.tool_name || 'TOOL';
    const isRunning = message.status === 'running';
    return (
      <View style={styles.toolRow}>
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
                <View style={[styles.thinkingBody, { borderLeftColor: colors.outline }]}>
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

              <MessageContent content={message.content} isUser={isUser} />

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
      {!isUser && onAddToMemory && (
        <Menu.Item 
          onPress={handleAddToMemory} 
          title={t('chat.messageActions.addToMemory')} 
          leadingIcon={props => <MaterialIcons {...props} name="psychology" />} 
        />
      )}
    </Menu>


  );
}, (prev, next) => {
  // 只比较影响渲染的 props，忽略 hasFileOperations（它只影响菜单行为）
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

function groupMessages(messages: ChatMessage[]): RenderItem[] {
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
          const hasMoreAiAfter = turnMsgs
            .slice(j + 1)
            .some((msg) => msg.role === 'ai');
          flushPendingAi(!hasMoreAiAfter);
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

  // Group steps
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
      currentTurnSteps.push(item.data);
    }
  }

  if (currentTurnSteps.length > 0) {
    groupedItems.push({
      type: 'steps_group',
      id: `steps_group_end`,
      steps: [...currentTurnSteps],
      isTurnActive: false,
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
  onResend,
}: {
  steps: ChatMessage[];
  isTurnActive: boolean;
  colors: any;
  onRewind?: (id: string, hasFiles: boolean) => void;
  onRetry?: (id: string, hasFiles: boolean) => void;
  onQuote?: (msg: ChatMessage) => void;
  onForward?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string) => void;
  onResend?: (msg: ChatMessage) => void;
}) {
  const [expanded, setExpanded] = useState(isTurnActive);
  const { t } = useTranslation();

  useEffect(() => {
    if (isTurnActive) {
      setExpanded(true);
    }
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
          {t('chat.messageList.executionSteps', '思考与执行过程')} ({steps.length})
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
                colors={colors}
                onRewind={onRewind}
                onRetry={onRetry}
                onQuote={onQuote}
                onForward={onForward}
                onAddToMemory={onAddToMemory}
                onResend={onResend}
                hasFileOperations={stepMsg.has_file_operations ?? false}
              />
            );
          })}
        </View>
      )}
    </View>
  );
});

export const MessageList = React.memo(function MessageList({
  onRewind, onRetry, onQuote, onForward, onAddToMemory, onResend, isTyping
}: MessageListProps) {
  const messages = useConversationStore((state) => state.messages);
  const { colors } = useTheme();
  const { t } = useTranslation();
  const flatListRef = useRef<FlatList>(null);
  const isUserAtBottomRef = useRef(true);

  // Group messages
  const groupedMessages = useMemo(() => groupMessages(messages), [messages]);
  const lastMessageCountRef = useRef(groupedMessages.length);

  // 自动滚动到底部
  useEffect(() => {
    const prevCount = lastMessageCountRef.current;
    const currentCount = groupedMessages.length;
    lastMessageCountRef.current = currentCount;

    if (currentCount > prevCount) {
      requestAnimationFrame(() => {
        setTimeout(() => {
          flatListRef.current?.scrollToEnd({ animated: true });
        }, 50);
      });
    }
  }, [groupedMessages]);

  const handleScroll = useCallback((event: any) => {
    const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
    const paddingToBottom = 20;
    const isAtBottom = layoutMeasurement.height + contentOffset.y >=
      contentSize.height - paddingToBottom;
    isUserAtBottomRef.current = isAtBottom;
  }, []);

  const hasFileOperationsAfter = useCallback((messageId: string): boolean => {
    const rawIndex = messages.findIndex(m => m.id === messageId);
    if (rawIndex === -1) return false;
    for (let i = rawIndex + 1; i < messages.length; i++) {
      if (messages[i].has_file_operations) {
        return true;
      }
      const content = messages[i].content || '';
      if (content.includes('```diff') || content.includes('文件') || content.includes('修改')) {
        return true;
      }
    }
    return false;
  }, [messages]);

  const renderMessage = useCallback((item: RenderItem) => {
    if (item.type === 'message') {
      const message = item.data;
      const isUser = message.role === 'human';
      const hasFileOps = hasFileOperationsAfter(message.id);

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
          onResend={onResend}
          hasFileOperations={hasFileOps}
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
          onResend={onResend}
        />
      );
    }
  }, [colors, onRewind, onRetry, onQuote, onForward, onAddToMemory, onResend, hasFileOperationsAfter]);

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
      scrollEventThrottle={200}
      ListEmptyComponent={null}
      ItemSeparatorComponent={() => <Divider style={styles.divider} />}
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
    prev.onResend === next.onResend &&
    prev.isTyping === next.isTyping;
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
    paddingHorizontal: 12,
  },
  stepsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
  },
  stepsHeaderText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '600',
  },
  stepsContentList: {
    borderLeftWidth: 1,
    marginLeft: 20,
    marginTop: 4,
    paddingLeft: 4,
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
