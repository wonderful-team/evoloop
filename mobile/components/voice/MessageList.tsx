// 语音对话消息列表 - 支持 Markdown、图片、文件、音频、Rewind/Retry

import React, { useRef, useEffect, useCallback, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  Animated,
  TouchableOpacity,
} from 'react-native';
import { Text, Avatar, Menu } from 'react-native-paper';
import { ChatMessage } from '@/types/voice';
import { useTheme } from '@/theme';
import { MessageContent } from '@/components/chat/MessageContent';
import { MaterialIcons } from '@expo/vector-icons';

interface MessageListProps {
  messages: ChatMessage[];
  onRewind?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  onQuote?: (message: ChatMessage) => void;
}

// 格式化时间
function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

// 单条消息组件
function MessageItem({
  message,
  isUser,
  colors,
  onRewind,
  onRetry,
  onQuote,
}: {
  message: ChatMessage;
  isUser: boolean;
  colors: any;
  onRewind?: (id: string) => void;
  onRetry?: (id: string) => void;
  onQuote?: (msg: ChatMessage) => void;
}) {
  const [menuVisible, setMenuVisible] = useState(false);

  const handleCopy = useCallback(() => {
    setMenuVisible(false);
  }, []);

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

  return (
    <Menu
      visible={menuVisible}
      onDismiss={() => setMenuVisible(false)}
      anchor={
        <TouchableOpacity
          activeOpacity={0.8}
          onLongPress={() => setMenuVisible(true)}
        >
          <View
            style={[
              styles.messageBubble,
              {
                backgroundColor: isUser ? colors.primaryContainer : colors.surfaceVariant,
              },
            ]}
          >
            <View style={styles.messageContent}>
              <MessageContent content={message.content} isUser={isUser} />
              
              {!message.isComplete && (
                <Animated.Text style={[styles.cursor, { color: colors.primary }]}>
                  |
                </Animated.Text>
              )}
            </View>
            
            <Text
              variant="bodySmall"
              style={[styles.timestamp, { color: colors.outline }]}
            >
              {formatTime(message.timestamp)}
            </Text>
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
    </Menu>
  );
}

export function MessageList({ messages, onRewind, onRetry, onQuote }: MessageListProps) {
  const { colors } = useTheme();
  const scrollViewRef = useRef<ScrollView>(null);

  // 自动滚动到底部
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages]);

  // 渲染单条消息
  const renderMessage = (message: ChatMessage, index: number) => {
    const isUser = message.role === 'user';
    const isSystem = message.role === 'system';

    // 系统消息
    if (isSystem) {
      return (
        <View key={message.id} style={styles.systemMessageContainer}>
          <Text variant="bodySmall" style={[styles.systemText, { color: colors.outline }]}>
            {message.content}
          </Text>
        </View>
      );
    }

    // 用户或助手消息
    return (
      <View
        key={message.id}
        style={[
          styles.messageContainer,
          isUser ? styles.userMessage : styles.assistantMessage,
        ]}
      >
        {/* 头像 */}
        <Avatar.Icon
          size={32}
          icon={isUser ? 'account' : 'robot'}
          style={[
            styles.avatar,
            { backgroundColor: isUser ? colors.primary : colors.surfaceVariant },
          ]}
          color={isUser ? colors.onPrimary : colors.primary}
        />

        {/* 消息气泡 */}
        <MessageItem
          message={message}
          isUser={isUser}
          colors={colors}
          onRewind={onRewind}
          onRetry={onRetry}
          onQuote={onQuote}
        />
      </View>
    );
  };

  return (
    <ScrollView
      ref={scrollViewRef}
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {messages.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text variant="bodyMedium" style={{ color: colors.outline }}>
            开始语音对话，或输入文字消息
          </Text>
        </View>
      ) : (
        messages.map((message, index) => renderMessage(message, index))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  contentContainer: {
    padding: 16,
    paddingBottom: 32,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 48,
  },
  messageContainer: {
    flexDirection: 'row',
    marginBottom: 16,
    maxWidth: '90%',
  },
  userMessage: {
    alignSelf: 'flex-end',
    flexDirection: 'row-reverse',
  },
  assistantMessage: {
    alignSelf: 'flex-start',
  },
  avatar: {
    marginHorizontal: 8,
  },
  messageBubble: {
    flex: 1,
    borderRadius: 16,
    padding: 12,
  },
  messageContent: {
    flex: 1,
  },
  cursor: {
    opacity: 1,
    fontWeight: 'bold',
  },
  timestamp: {
    marginTop: 8,
    fontSize: 10,
    alignSelf: 'flex-end',
  },
  systemMessageContainer: {
    alignItems: 'center',
    marginVertical: 8,
  },
  systemText: {
    fontStyle: 'italic',
  },
});
