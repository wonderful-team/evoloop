// 语音对话消息列表 - 文档列表样式

import React, { useRef, useEffect, useCallback, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Text, Menu, Divider } from 'react-native-paper';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import { ChatMessage } from '@/types/conversation';
import { useTheme } from '@/theme';
import { MessageContent } from '@/components/chat/MessageContent';
import { WoodenRobot } from '@/components/WoodenRobot';

interface MessageListProps {
  messages: ChatMessage[];
  onRewind?: (messageId: string, hasFileOperations: boolean) => void;
  onRetry?: (messageId: string, hasFileOperations: boolean) => void;
  onQuote?: (message: ChatMessage) => void;
  onAddToMemory?: (text: string) => void;
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

// 单条消息组件
function MessageItem({
  message,
  isUser,
  colors,
  onRewind,
  onRetry,
  onQuote,
  onAddToMemory,
  hasFileOperations,
}: {
  message: ChatMessage;
  isUser: boolean;
  colors: any;
  onRewind?: (id: string, hasFiles: boolean) => void;
  onRetry?: (id: string, hasFiles: boolean) => void;
  onQuote?: (msg: ChatMessage) => void;
  onAddToMemory?: (text: string) => void;
  hasFileOperations: boolean;
}) {
  const [menuVisible, setMenuVisible] = useState(false);

  const handleCopy = useCallback(() => {
    setMenuVisible(false);
  }, []);

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

  const roleIcon = getRoleIcon(message.role);
  const roleColor = getRoleColor(message.role, colors);

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
              <MessageContent content={message.content} isUser={isUser} />
            </View>
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
      {!isUser && onAddToMemory && (
        <Menu.Item onPress={handleAddToMemory} title="添加到记忆" leadingIcon="brain" />
      )}
    </Menu>
  );
}

export function MessageList({ messages, onRewind, onRetry, onQuote, onAddToMemory }: MessageListProps) {
  const { colors } = useTheme();
  const scrollViewRef = useRef<ScrollView>(null);
  const isUserAtBottomRef = useRef(true);
  const lastMessageCountRef = useRef(messages.length);

  // 自动滚动到底部
  useEffect(() => {
    const prevCount = lastMessageCountRef.current;
    const currentCount = messages.length;
    lastMessageCountRef.current = currentCount;

    if (currentCount > prevCount && isUserAtBottomRef.current) {
      const lastMessage = messages[messages.length - 1];
      if (lastMessage?.role === 'user') {
        setTimeout(() => {
          scrollViewRef.current?.scrollToEnd({ animated: true });
        }, 100);
      }
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

  const renderMessage = (message: ChatMessage, index: number) => {
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
          onAddToMemory={onAddToMemory}
          hasFileOperations={hasFileOps}
        />
        {index < messages.length - 1 && (
          <Divider style={styles.divider} />
        )}
      </View>
    );
  };

  function WelcomeView() {
    const [mood, setMood] = useState<'neutral' | 'happy' | 'thinking'>('happy');

    useEffect(() => {
      const interval = setInterval(() => {
        const moods: Array<'neutral' | 'happy' | 'thinking'> = ['neutral', 'happy', 'thinking'];
        setMood(moods[Math.floor(Math.random() * moods.length)]);
      }, 5000);
      return () => clearInterval(interval);
    }, []);

    return (
      <View style={styles.welcomeContainer}>
        <WoodenRobot primaryColor={colors.primary} mood={mood} />
        <Text variant="headlineSmall" style={[styles.welcomeTitle, { color: colors.primary }]}>
          EvoLoop AI
        </Text>
        <Text variant="bodyMedium" style={[styles.welcomeSubtitle, { color: colors.onSurfaceVariant }]}>
          你好！我是你的木头机器人助手
        </Text>
        <Text variant="bodySmall" style={[styles.welcomeHint, { color: colors.onSurfaceVariant }]}>
          点击麦克风开始语音对话
        </Text>
      </View>
    );
  }

  return (
    <ScrollView
      ref={scrollViewRef}
      style={[styles.container, { backgroundColor: colors.background }]}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
      onScroll={handleScroll}
      scrollEventThrottle={200}
    >
      {messages.length === 0 ? (
        <WelcomeView />
      ) : (
        <View style={styles.messageList}>
          {messages.map((message, index) => renderMessage(message, index))}
        </View>
      )}
    </ScrollView>
  );
}

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
  welcomeContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 32,
    gap: 16,
  },
  welcomeTitle: {
    fontWeight: 'bold',
    marginTop: 16,
  },
  welcomeSubtitle: {
    fontSize: 16,
    fontWeight: '500',
  },
  welcomeHint: {
    marginTop: 4,
    opacity: 0.6,
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
});
