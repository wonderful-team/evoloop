// 会话列表组件

import React, { useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { Text, IconButton, Menu, Divider, ActivityIndicator } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useConversationStore } from '@/stores/conversationStore';
import { useAuthStore } from '@/stores/authStore';
import { Conversation } from '@/types/conversation';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { Swipeable } from 'react-native-gesture-handler';
import { formatDate } from '@/utils/format';

interface ThreadListProps {
  projectId?: number;
  deviceKey?: string;
  onSelectThread?: (threadId: string) => void;
  onNewThread?: () => void;
}

export function ThreadList({ projectId, deviceKey, onSelectThread, onNewThread }: ThreadListProps) {
  const { colors } = useTheme();
  const { isLoggedIn } = useAuthStore();
  const {
    conversations,
    currentConversationId,
    isLoadingConversations,
    hasMoreConversations,
    loadConversations,
    loadMoreConversations,
    deleteConversation,
    setCurrentConversation,
  } = useConversationStore();

  // 加载会话列表（仅在登录时，projectId 或 deviceKey 变化时刷新）
  useEffect(() => {
    if (isLoggedIn) {
      loadConversations(projectId, true, deviceKey).catch(() => {
        // 静默处理错误，不显示代码级错误，由调用方决定是否提示用户
      });
    }
  }, [projectId, deviceKey, isLoggedIn]);

  // 选择会话
  const handleSelectThread = useCallback((conversation: Conversation) => {
    setCurrentConversation(conversation.id);
    onSelectThread?.(conversation.id);
  }, [setCurrentConversation, onSelectThread]);

  // 删除会话
  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteConversation(id);
    } catch (error) {
      console.error('删除会话失败:', error);
    }
  }, [deleteConversation]);

  // 渲染会话项
  const renderThreadItem = useCallback(({ item }: { item: Conversation }) => {
    const isActive = item.id === currentConversationId;

    return (
      <Swipeable
        renderRightActions={() => (
          <View style={[styles.deleteAction, { backgroundColor: colors.error }]}>
            <IconButton
              icon="delete"
              iconColor={colors.onError}
              onPress={() => handleDelete(item.id)}
            />
          </View>
        )}
      >
        <TouchableOpacity
          style={[
            styles.threadItem,
            { backgroundColor: isActive ? colors.primaryContainer : 'transparent' },
          ]}
          onPress={() => handleSelectThread(item)}
        >
          <View style={styles.threadIcon}>
            <MaterialIcons
              name="chat-bubble"
              size={20}
              color={isActive ? colors.primary : colors.onSurfaceVariant}
            />
          </View>

          <View style={styles.threadContent}>
            <Text
              style={[
                styles.threadTitle,
                { color: isActive ? colors.primary : colors.onSurface },
              ]}
              numberOfLines={1}
            >
              {item.title || '新对话'}
            </Text>

            <Text style={[styles.threadMeta, { color: colors.onSurfaceVariant }]}>
              {formatDate.date(item.updated_at)} · {item.message_count} 条消息
            </Text>
          </View>

          {isActive && (
            <MaterialIcons name="chevron-right" size={20} color={colors.primary} />
          )}
        </TouchableOpacity>
      </Swipeable>
    );
  }, [currentConversationId, colors, handleSelectThread, handleDelete]);

  // 渲染底部加载更多
  const renderFooter = () => {
    if (!hasMoreConversations) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  };

  // 下拉刷新
  const handleRefresh = () => {
    if (isLoggedIn) {
      loadConversations(projectId, true, deviceKey);
    }
  };

  // 加载更多
  const handleLoadMore = () => {
    if (hasMoreConversations && !isLoadingConversations) {
      loadMoreConversations();
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      {/* 头部 */}
      <View style={[styles.header, { borderBottomColor: colors.outline + '30' }]}>
        <Text variant="titleMedium" style={{ color: colors.onSurface }}>
          会话历史
        </Text>

        <TouchableOpacity
          style={[styles.newThreadBtn, { backgroundColor: colors.primary }]}
          onPress={onNewThread}
        >
          <MaterialIcons name="add" size={18} color={colors.onPrimary} />
          <Text style={{ color: colors.onPrimary, fontSize: 13, marginLeft: 4 }}>
            新建对话
          </Text>
        </TouchableOpacity>
      </View>

      {/* 会话列表 */}
      <FlatList
        data={conversations}
        keyExtractor={(item) => item.id}
        renderItem={renderThreadItem}
        ItemSeparatorComponent={() => (
          <Divider style={{ backgroundColor: colors.outline + '20' }} />
        )}
        refreshControl={
          <RefreshControl
            refreshing={isLoadingConversations}
            onRefresh={handleRefresh}
            colors={[colors.primary]}
          />
        }
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.5}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <MaterialIcons name="chat-bubble-outline" size={48} color={colors.onSurfaceVariant} />
            <Text style={[styles.emptyText, { color: colors.onSurfaceVariant }]}>
              暂无会话记录
            </Text>
            <TouchableOpacity
              style={[styles.newThreadButton, { backgroundColor: colors.primaryContainer }]}
              onPress={onNewThread}
            >
              <Text style={{ color: colors.primary }}>开始新对话</Text>
            </TouchableOpacity>
          </View>
        }
        contentContainerStyle={conversations.length === 0 && styles.emptyContent}
      />
    </View>
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
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  threadItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  threadIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  threadContent: {
    flex: 1,
  },
  threadTitle: {
    fontSize: 15,
    fontWeight: '500',
    marginBottom: 4,
  },
  threadMeta: {
    fontSize: 12,
  },
  deleteAction: {
    justifyContent: 'center',
    alignItems: 'center',
    width: 80,
  },
  footer: {
    paddingVertical: 16,
    alignItems: 'center',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 48,
  },
  emptyText: {
    fontSize: 14,
    marginTop: 16,
    marginBottom: 24,
  },
  newThreadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  newThreadButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  emptyContent: {
    flex: 1,
    justifyContent: 'center',
  },
});
