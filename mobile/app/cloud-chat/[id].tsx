// 云端对话页面
// 参考: @evoloop/frontend/packages/mobile/src/screens/CloudChatScreen.tsx

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import {
  Text,
  TextInput,
  IconButton,
  ActivityIndicator,
  Avatar,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/theme';
// 附件功能暂不使用
// import * as ImagePicker from 'expo-image-picker';
import { api } from '@/services/api/client';
import { useAuthStore } from '@/stores/authStore';

interface Message {
  id: string;
  type: 'user' | 'output' | 'error';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  attachments?: any[];
}

// 附件功能暂不使用
// interface Attachment {
//   type: 'image' | 'file';
//   uri: string;
//   name?: string;
// }

export default function CloudChatScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { userInfo } = useAuthStore();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  // const [attachments, setAttachments] = useState<Attachment[]>([]);
  
  const flatListRef = useRef<FlatList>(null);
  const isNew = id === 'new';
  const conversationId = isNew ? undefined : id;

  // 加载历史消息
  useEffect(() => {
    if (!isNew && id) {
      loadHistory();
    }
  }, [id]);

  // 处理初始消息
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initialMessage = params.get('initialMessage');
    if (initialMessage && messages.length === 0) {
      handleSend(initialMessage);
    }
  }, []);

  // 加载历史消息
  const loadHistory = async () => {
    setIsLoading(true);
    try {
      const response: any = await api.get(`/gateway/api/v1/conversations/${id}/messages`);
      if (response?.data?.list) {
        const formatted = response.data.list.reverse().map((msg: any) => ({
          id: msg.id,
          type: msg.role === 'user' ? 'user' : 'output',
          content: msg.content,
          timestamp: msg.create_time * 1000,
        }));
        setMessages(formatted);
      }
    } catch (error) {
      console.error('加载历史消息失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 发送消息
  const handleSend = useCallback(async (content: string = input) => {
    if (!content.trim() && attachments.length === 0) return;

    const tempUserMsg: Message = {
      id: `temp_${Date.now()}`,
      type: 'user',
      content: content.trim(),
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, tempUserMsg]);
    setInput('');
    // setAttachments([]);

    const botMsgId = `bot_${Date.now()}`;
    setMessages(prev => [
      ...prev,
      {
        id: botMsgId,
        type: 'output',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      },
    ]);

    setIsStreaming(true);
    let fullResponse = '';

    try {
      // 使用 fetch 进行流式请求
      const response = await fetch(`${process.env.EXPO_PUBLIC_API_BASE_URL}/gateway/api/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${userInfo?.token || ''}`,
        },
        body: JSON.stringify({
          message: content.trim(),
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        throw new Error('请求失败');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('无法读取响应');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                fullResponse += parsed.content;
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (last?.id === botMsgId) {
                    return [
                      ...prev.slice(0, -1),
                      { ...last, content: fullResponse },
                    ];
                  }
                  return prev;
                });
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }

      setIsStreaming(false);
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.id === botMsgId) {
          return [...prev.slice(0, -1), { ...last, isStreaming: false }];
        }
        return prev;
      });
    } catch (error: any) {
      console.error('发送消息失败:', error);
      setIsStreaming(false);
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.id === botMsgId) {
          return [
            ...prev.slice(0, -1),
            {
              id: botMsgId,
              type: 'error',
              content: error.message || '发送失败',
              timestamp: Date.now(),
            },
          ];
        }
        return prev;
      });
    }
  }, [input, attachments, conversationId, userInfo]);

  // 图片选择功能暂不使用
  // const handleImagePick = useCallback(async () => { ... }, []);
  // const removeAttachment = useCallback((index: number) => { ... }, []);

  // 渲染消息
  const renderMessage = useCallback(({ item }: { item: Message }) => {
    const isUser = item.type === 'user';
    const isError = item.type === 'error';

    return (
      <View style={[styles.messageContainer, isUser && styles.userMessageContainer]}>
        {!isUser && (
          <Avatar.Icon
            size={32}
            icon="robot"
            style={[styles.avatar, { backgroundColor: colors.primaryContainer }]}
            color={colors.primary}
          />
        )}
        <View style={[styles.messageBubble, {
          backgroundColor: isUser ? colors.primary : isError ? colors.errorContainer : colors.surface,
          borderBottomLeftRadius: isUser ? 16 : 4,
          borderBottomRightRadius: isUser ? 4 : 16,
        }]}>
          <Text style={[styles.messageText, {
            color: isUser ? colors.onPrimary : isError ? colors.error : colors.onSurface,
          }]}>
            {item.content}
            {item.isStreaming && '▊'}
          </Text>

        </View>
        {isUser && (
          <Avatar.Text
            size={32}
            label={userInfo?.nickname?.charAt(0) || 'U'}
            style={[styles.avatar, { backgroundColor: colors.primary }]}
            color={colors.onPrimary}
          />
        )}
      </View>
    );
  }, [colors, userInfo]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      {/* 头部 */}
      <View style={[styles.header, { 
        backgroundColor: colors.surface,
        borderBottomColor: colors.outlineVariant,
      }]}>
        <IconButton
          icon="arrow-back"
          size={24}
          onPress={() => router.back()}
        />
        <Text variant="titleMedium" style={styles.headerTitle}>
          {isNew ? '新对话' : '云端对话'}
        </Text>
        <IconButton
          icon="more-vert"
          size={24}
          onPress={() => {}}
        />
      </View>

      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* 消息列表 */}
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={item => item.id}
          contentContainerStyle={styles.messagesContent}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <MaterialIcons name="chat-bubble-outline" size={48} color={colors.outline} />
              <Text style={[styles.emptyText, { color: colors.outline }]}>
                开始一个新的对话
              </Text>
            </View>
          }
        />

        {isLoading && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="small" color={colors.primary} />
          </View>
        )}

        {/* 输入框 */}
        <View style={[styles.inputContainer, { 
          backgroundColor: colors.surface,
          borderTopColor: colors.outlineVariant,
        }]}>
          {/* 附件预览 */}
          {attachments.length > 0 && (
            <View style={styles.attachmentsRow}>
              {attachments.map((att, index) => (
                <View key={index} style={styles.attachmentPreview}>
                  <Image source={{ uri: att.uri }} style={styles.attachmentThumb} />
                  <IconButton
                    icon="close"
                    size={14}
                    style={styles.removeAttachment}
                    onPress={() => removeAttachment(index)}
                  />
                </View>
              ))}
            </View>
          )}

          <View style={styles.inputRow}>
            <IconButton
              icon="image"
              size={20}
              iconColor={colors.onSurfaceVariant}
              onPress={handleImagePick}
              disabled={isStreaming}
            />
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder="输入消息..."
              placeholderTextColor={colors.outline}
              multiline
              maxLength={2000}
              disabled={isStreaming}
              style={[styles.input, { color: colors.onSurface }]}
              contentStyle={styles.inputContent}
              underlineColor="transparent"
              activeUnderlineColor="transparent"
            />
            {isStreaming ? (
              <ActivityIndicator size="small" color={colors.primary} style={styles.sendButton} />
            ) : (
              <IconButton
                icon="send"
                size={24}
                iconColor={input.trim() || attachments.length > 0 ? colors.onPrimary : colors.outline}
                onPress={() => handleSend()}
                disabled={!input.trim()}
                style={[styles.sendButton, {
                  backgroundColor: input.trim() ? colors.primary : colors.surfaceVariant,
                }]}
              />
            )}
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 56,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontWeight: '600',
  },
  keyboardView: {
    flex: 1,
  },
  messagesContent: {
    padding: 16,
    paddingBottom: 24,
  },
  messageContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginBottom: 16,
  },
  userMessageContainer: {
    flexDirection: 'row-reverse',
  },
  avatar: {
    marginHorizontal: 8,
  },
  messageBubble: {
    maxWidth: '75%',
    padding: 12,
    borderRadius: 16,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  messageImage: {
    width: 200,
    height: 200,
    borderRadius: 8,
    marginTop: 8,
    resizeMode: 'cover',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 100,
  },
  emptyText: {
    marginTop: 16,
    fontSize: 14,
  },
  loadingOverlay: {
    position: 'absolute',
    top: 16,
    left: '50%',
    marginLeft: -20,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: 'rgba(0,0,0,0.05)',
    borderRadius: 16,
  },
  inputContainer: {
    borderTopWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  attachmentsRow: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    marginBottom: 8,
  },
  attachmentPreview: {
    width: 60,
    height: 60,
    borderRadius: 8,
    overflow: 'hidden',
    marginRight: 8,
    position: 'relative',
  },
  attachmentThumb: {
    width: '100%',
    height: '100%',
  },
  removeAttachment: {
    position: 'absolute',
    top: -8,
    right: -8,
    backgroundColor: 'white',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  input: {
    flex: 1,
    backgroundColor: 'transparent',
    fontSize: 15,
    maxHeight: 100,
    paddingHorizontal: 0,
  },
  inputContent: {
    paddingTop: 8,
    paddingBottom: 8,
  },
  sendButton: {
    margin: 0,
    borderRadius: 20,
  },
});
