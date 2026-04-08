// 云端对话页面
// Mobile → Gateway → Desktop 指令下发架构

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
  Chip,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/theme';
import { DeviceManager } from '@/services/devices/DeviceManager';
import { useDeviceStore } from '@/stores/deviceStore';

interface Message {
  id: string;
  type: 'user' | 'output' | 'error' | 'system';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  commandId?: number;
}

export default function CloudChatScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { currentDevice } = useDeviceStore();
  
  // 从 URL 参数获取设备信息
  const { deviceId, deviceName } = useLocalSearchParams<{
    deviceId?: string;
    deviceName?: string;
  }>();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  
  const flatListRef = useRef<FlatList>(null);
  const isNew = id === 'new';
  const conversationId = isNew ? undefined : id;

  // 确定目标设备
  const targetDeviceId = deviceId || currentDevice?.id;
  const targetDeviceName = deviceName || currentDevice?.name || 'Desktop';
  const isDeviceOnline = currentDevice?.status === 'online';

  // 添加系统消息
  const addSystemMessage = useCallback((content: string) => {
    const systemMsg: Message = {
      id: `system_${Date.now()}`,
      type: 'system',
      content,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, systemMsg]);
  }, []);

  // 发送消息到 Desktop
  const handleSend = useCallback(async () => {
    if (!input.trim()) return;
    if (!targetDeviceId) {
      addSystemMessage('错误：未选择目标设备');
      return;
    }
    if (!isDeviceOnline) {
      addSystemMessage('错误：设备离线，无法发送指令');
      return;
    }

    const content = input.trim();
    const tempUserMsg: Message = {
      id: `user_${Date.now()}`,
      type: 'user',
      content,
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, tempUserMsg]);
    setInput('');
    setIsSending(true);

    const botMsgId = `bot_${Date.now()}`;
    setMessages(prev => [
      ...prev,
      {
        id: botMsgId,
        type: 'output',
        content: '正在发送至 Desktop...',
        timestamp: Date.now(),
        isStreaming: true,
      },
    ]);

    try {
      // 使用 DeviceManager 发送指令
      const result = await DeviceManager.sendCommand(
        targetDeviceId,
        'chat',
        {
          message: content,
          conversation_id: conversationId,
          timestamp: Date.now(),
        }
      );

      // 更新消息状态
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.id === botMsgId) {
          return [
            ...prev.slice(0, -1),
            {
              ...last,
              content: `指令已发送！Desktop 正在处理...\n指令 ID: ${result?.command_id || 'N/A'}`,
              isStreaming: false,
              commandId: result?.command_id,
            },
          ];
        }
        return prev;
      });
    } catch (error: any) {
      console.error('发送指令失败:', error);
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.id === botMsgId) {
          return [
            ...prev.slice(0, -1),
            {
              id: botMsgId,
              type: 'error',
              content: `发送失败: ${error.message || '请检查设备连接'}`,
              timestamp: Date.now(),
            },
          ];
        }
        return prev;
      });
    } finally {
      setIsSending(false);
    }
  }, [input, targetDeviceId, isDeviceOnline, conversationId, addSystemMessage]);

  // 渲染消息
  const renderMessage = useCallback(({ item }: { item: Message }) => {
    const isUser = item.type === 'user';
    const isError = item.type === 'error';
    const isSystem = item.type === 'system';

    if (isSystem) {
      return (
        <View style={styles.systemMessageContainer}>
          <Chip icon="information" style={styles.systemChip}>
            {item.content}
          </Chip>
        </View>
      );
    }

    return (
      <View style={[styles.messageContainer, isUser && styles.userMessageContainer]}>
        {!isUser && (
          <Avatar.Icon
            size={32}
            icon="desktop-classic"
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
            label="我"
            style={[styles.avatar, { backgroundColor: colors.primary }]}
            color={colors.onPrimary}
          />
        )}
      </View>
    );
  }, [colors]);

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
        <View style={styles.headerCenter}>
          <Text variant="titleMedium" style={styles.headerTitle}>
            {targetDeviceName}
          </Text>
          <View style={styles.statusRow}>
            <View style={[styles.statusDot, { 
              backgroundColor: isDeviceOnline ? '#4CAF50' : '#FF3D00' 
            }]} />
            <Text variant="bodySmall" style={{ color: colors.outline }}>
              {isDeviceOnline ? '在线' : '离线'}
              {targetDeviceId ? ` • ${targetDeviceId.slice(0, 8)}...` : ''}
            </Text>
          </View>
        </View>
        <IconButton
          icon="refresh"
          size={24}
          onPress={() => {
            if (targetDeviceId) {
              DeviceManager.refreshDeviceStatus(targetDeviceId);
            }
          }}
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
                开始与 Desktop 对话
              </Text>
              <Text style={[styles.emptySubtext, { color: colors.outline }]}>
                发送的消息将通过 Gateway 路由到 Desktop
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
          <View style={styles.inputRow}>
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder={isDeviceOnline ? "输入消息..." : "设备离线，无法发送"}
              placeholderTextColor={colors.outline}
              multiline
              maxLength={2000}
              disabled={isSending || !isDeviceOnline}
              style={[styles.input, { color: colors.onSurface }]}
              underlineColorAndroid="transparent"
              theme={{ colors: { primary: colors.primary } }}
            />
            <IconButton
              icon={isSending ? 'loading' : 'send'}
              size={24}
              onPress={handleSend}
              disabled={!input.trim() || isSending || !isDeviceOnline}
              containerColor={colors.primary}
              iconColor={colors.onPrimary}
            />
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
    paddingHorizontal: 4,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
  },
  headerTitle: {
    fontWeight: '600',
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  keyboardView: {
    flex: 1,
  },
  messagesContent: {
    padding: 16,
    flexGrow: 1,
  },
  messageContainer: {
    flexDirection: 'row',
    marginBottom: 16,
    alignItems: 'flex-end',
  },
  userMessageContainer: {
    justifyContent: 'flex-end',
  },
  avatar: {
    marginHorizontal: 4,
  },
  messageBubble: {
    maxWidth: '75%',
    padding: 12,
    borderRadius: 16,
    elevation: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  messageText: {
    fontSize: 14,
    lineHeight: 20,
  },
  systemMessageContainer: {
    alignItems: 'center',
    marginVertical: 8,
  },
  systemChip: {
    height: 32,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 100,
  },
  emptyText: {
    marginTop: 16,
    fontSize: 16,
  },
  emptySubtext: {
    marginTop: 8,
    fontSize: 14,
  },
  loadingOverlay: {
    position: 'absolute',
    top: 16,
    right: 16,
  },
  inputContainer: {
    borderTopWidth: 1,
    padding: 12,
    paddingBottom: Platform.OS === 'ios' ? 24 : 12,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    marginRight: 8,
    backgroundColor: 'transparent',
    paddingVertical: 8,
    maxHeight: 100,
  },
});
