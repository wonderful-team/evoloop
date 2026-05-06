// 语音对话消息列表 - 文档列表样式

import React, { useRef, useEffect, useCallback, useState } from 'react';
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
import { MessageContent } from '@/components/chat/MessageContent';
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
    case 'user': return 'account';
    case 'assistant': return 'robot';
    case 'system': return 'information';
    case 'tool': return 'wrench';
    default: return 'help-circle';
  }
}

// 获取角色颜色
function getRoleColor(role: string, colors: any): string {
  switch (role) {
    case 'user': return colors.primary;
    case 'assistant': return colors.secondary || '#7C4DFF';
    case 'system': return colors.onSurfaceVariant;
    case 'tool': return colors.tertiary || '#00BCD4';
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
    const sender = isUser ? '我' : 'AI';
    await shareChatMessage(message.content, sender);
    setMenuVisible(false);
  }, [message.content, isUser]);

  const roleIcon = getRoleIcon(message.role);
  const roleColor = getRoleColor(message.role, colors);

  // ── 工具消息：紧凑单行（对齐桌面端设计）
  if (message.role === 'tool') {
    const toolLabel = (message as any).tool_meta?.display_name || (message as any).tool_name || 'TOOL';
    const isRunning = (message as any).status === 'running';
    return (
      <View style={styles.toolRow}>
        <View style={[styles.toolSpine, { backgroundColor: colors.outline }]} />
        <View style={[styles.toolDot, { backgroundColor: colors.outline }]} />
        <View style={styles.toolContent}>
          <MaterialCommunityIcons name="wrench-outline" size={12} color={colors.onSurfaceVariant} style={{ opacity: 0.6 }} />
          <Text
            numberOfLines={1}
            style={[styles.toolLabel, { color: colors.onSurfaceVariant }]}
          >
            {toolLabel}
          </Text>
          {isRunning && (
            <ActivityIndicator size={10} color={colors.primary} style={{ marginLeft: 4, opacity: 0.6 }} />
          )}
          {(message as any).changeset_count > 0 && (
            <View style={[styles.changesetBadge, { backgroundColor: colors.primaryContainer }]}>
              <Text style={[styles.changesetBadgeText, { color: colors.primary }]}>
                {(message as any).changeset_count} FILES
              </Text>
            </View>
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
                    思考过程
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

              <MessageContent content={message.content} isUser={isUser} />

              {/* 文件变更徽章 */}
              {!isUser && (message as any).changeset_count > 0 && (
                <View style={styles.changesetRow}>
                  <View style={[styles.changesetBadge, { backgroundColor: colors.primaryContainer }]}>
                    <MaterialCommunityIcons name="file-multiple-outline" size={11} color={colors.primary} />
                    <Text style={[styles.changesetBadgeText, { color: colors.primary }]}>
                      {(message as any).changeset_count} 个文件变更
                    </Text>
                  </View>
                </View>
              )}
            </View>

            {/* 发送状态指示器 */}
            {isUser && message.status && message.status !== 'sent' && (
              <View style={styles.statusRow}>
                {message.status === 'sending' && (
                  <>
                    <ActivityIndicator size={12} color={colors.onSurfaceVariant} />
                    <Text variant="bodySmall" style={{ marginLeft: 4, color: colors.onSurfaceVariant }}>
                      发送中
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
                      发送失败，点击重试
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </View>
        </TouchableOpacity>
      }
    >
      <Menu.Item onPress={handleCopy} title="复制" leadingIcon="content-copy" />
      {isUser && onRewind && (
        <Menu.Item onPress={handleRewind} title="撤回" leadingIcon="undo" />
      )}
      {isUser && onRetry && (
        <Menu.Item onPress={handleRetry} title="重试" leadingIcon="refresh" />
      )}
      {onQuote && (
        <Menu.Item onPress={handleQuote} title="引用" leadingIcon="format-quote-close" />
      )}
      {onForward && (
        <Menu.Item onPress={handleForward} title="转发" leadingIcon="share-variant" />
      )}
      <Menu.Item onPress={handleShare} title="分享" leadingIcon="export-variant" />
      {!isUser && onAddToMemory && (
        <Menu.Item onPress={handleAddToMemory} title="添加到记忆" leadingIcon="brain" />
      )}
    </Menu>
  );
}, (prev, next) => {
  // 只比较影响渲染的 props，忽略 hasFileOperations（它只影响菜单行为）
  return prev.message === next.message &&
    prev.isUser === next.isUser &&
    prev.colors === next.colors;
});

export const MessageList = React.memo(function MessageList({
  onRewind, onRetry, onQuote, onForward, onAddToMemory, onResend, isTyping
}: MessageListProps) {
  const messages = useConversationStore((state) => state.messages);
  const { colors } = useTheme();
  const flatListRef = useRef<FlatList>(null);
  const isUserAtBottomRef = useRef(true);
  const lastMessageCountRef = useRef(messages.length);

  // 自动滚动到底部：只要消息数量增加（用户发送或 AI 回复），都滚动到底部
  useEffect(() => {
    const prevCount = lastMessageCountRef.current;
    const currentCount = messages.length;
    lastMessageCountRef.current = currentCount;

    if (currentCount > prevCount) {
      // 使用 requestAnimationFrame + 短暂延迟，确保内容渲染和布局计算完成后再滚动
      requestAnimationFrame(() => {
        setTimeout(() => {
          flatListRef.current?.scrollToEnd({ animated: true });
        }, 50);
      });
    }
  }, [messages]);

  const handleScroll = useCallback((event: any) => {
    const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
    const paddingToBottom = 20;
    const isAtBottom = layoutMeasurement.height + contentOffset.y >=
      contentSize.height - paddingToBottom;
    isUserAtBottomRef.current = isAtBottom;
  }, []);

  const hasFileOperationsAfter = useCallback((messageIndex: number): boolean => {
    for (let i = messageIndex + 1; i < messages.length; i++) {
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

  // 使用 useCallback 稳定 renderItem 引用，避免 FlatList 在 MessageList 重渲染时
  // 因 renderItem 引用变化而重新渲染所有可见项
  const renderMessage = useCallback((message: ChatMessage, index: number) => {
    const isUser = message.role === 'user';
    const isSystem = message.role === 'system';

    // 系统消息简洁显示
    if (isSystem) {
      return (
        <View key={message.id} style={styles.systemMessageContainer}>
          <Text variant="bodySmall" style={[styles.systemText, { color: colors.onSurfaceVariant }]}>
            {message.content}
          </Text>
        </View>
      );
    }

    const hasFileOps = hasFileOperationsAfter(index);

    return (
      <View key={message.id}>
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
        {index < messages.length - 1 && (
          <Divider style={styles.divider} />
        )}
      </View>
    );
  }, [colors, onRewind, onRetry, onQuote, onForward, onAddToMemory, onResend, hasFileOperationsAfter]);

  return (
    <FlatList
      ref={flatListRef}
      style={[styles.container, { backgroundColor: colors.background }]}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
      data={messages}
      keyExtractor={(item) => item.id}
      renderItem={({ item, index }) => renderMessage(item, index)}
      onScroll={handleScroll}
      scrollEventThrottle={200}
      ListEmptyComponent={null}
      ListFooterComponent={
        isTyping ? (
          <View style={styles.typingContainer}>
            <View style={[styles.typingBubble, { backgroundColor: colors.surfaceVariant }]}>
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
              <View style={[styles.typingDot, { backgroundColor: colors.primary }]} />
            </View>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, marginTop: 4 }}>
              AI 思考中...
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
  // 自定义比较：只有 props 引用或 isTyping 变化时才重渲染
  // 避免 ChatScreen 因高频状态（nlsVolume/nlsCurrentText）变化导致 MessageList 无辜重渲染
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
    width: 7,
    height: 7,
    borderRadius: 4,
    marginRight: 8,
    opacity: 0.5,
    zIndex: 1,
  },
  toolContent: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  toolLabel: {
    flex: 1,
    fontSize: 12,
    opacity: 0.65,
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
  // 文件变更徽章
  changesetRow: {
    marginTop: 8,
    flexDirection: 'row',
  },
  changesetBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  changesetBadgeText: {
    fontSize: 10,
    fontWeight: '600',
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
