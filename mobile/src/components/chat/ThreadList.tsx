// 会话列表组件

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  View,
  StyleSheet,
  SectionList,
  TouchableOpacity,
  RefreshControl,
  Text,
  Platform,
} from 'react-native';
import { IconButton, Divider, ActivityIndicator, Portal, Dialog, Button, TextInput } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useConversationStore } from '@/stores/conversationStore';
import { useAuthStore } from '@/stores/authStore';
import { Conversation } from '@/types/conversation';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { Swipeable } from 'react-native-gesture-handler';
import { formatDate } from '@/utils/format';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

interface ThreadListProps {
  projectId?: number;
  deviceKey?: string;
  onSelectThread?: (threadId: string) => void;
  onNewThread?: () => void;
}

interface ConversationSection {
  title: string;
  data: Conversation[];
}

export function ThreadList({ projectId, deviceKey, onSelectThread, onNewThread }: ThreadListProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
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
    getUnreadCount,
    togglePinConversation,
    renameConversation,
  } = useConversationStore();

  const [renameVisible, setRenameVisible] = useState(false);
  const [renameThreadId, setRenameThreadId] = useState('');
  const [renameTitle, setRenameTitle] = useState('');

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

  // 打开重命名对话框
  const handleOpenRename = useCallback((threadId: string, currentTitle: string) => {
    setRenameThreadId(threadId);
    setRenameTitle(currentTitle);
    setRenameVisible(true);
  }, []);

  // 提交重命名
  const handleRename = useCallback(async () => {
    if (!renameTitle.trim()) return;
    try {
      await renameConversation(renameThreadId, renameTitle.trim());
      setRenameVisible(false);
    } catch (error) {
      console.error('重命名会话失败:', error);
    }
  }, [renameThreadId, renameTitle, renameConversation]);

  // 时间维度分组
  const sections = useMemo(() => {
    const pinnedList: Conversation[] = [];
    const todayList: Conversation[] = [];
    const yesterdayList: Conversation[] = [];
    const recentList: Conversation[] = [];
    const earlierList: Conversation[] = [];

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
    const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    conversations.forEach((conv) => {
      if (conv.is_pinned) {
        pinnedList.push(conv);
        return;
      }

      const dateStr = conv.updated_at || conv.created_at;
      if (!dateStr) {
        earlierList.push(conv);
        return;
      }

      const date = new Date(dateStr);
      if (isNaN(date.getTime())) {
        earlierList.push(conv);
        return;
      }

      if (date >= today) {
        todayList.push(conv);
      } else if (date >= yesterday) {
        yesterdayList.push(conv);
      } else if (date >= sevenDaysAgo) {
        recentList.push(conv);
      } else {
        earlierList.push(conv);
      }
    });

    const result: ConversationSection[] = [];
    if (pinnedList.length > 0) {
      result.push({ title: t('threadList.sectionPinned') || '置顶会话', data: pinnedList });
    }
    if (todayList.length > 0) {
      result.push({ title: t('threadList.sectionToday') || '今天', data: todayList });
    }
    if (yesterdayList.length > 0) {
      result.push({ title: t('threadList.sectionYesterday') || '昨天', data: yesterdayList });
    }
    if (recentList.length > 0) {
      result.push({ title: t('threadList.sectionRecent') || '最近 7 天', data: recentList });
    }
    if (earlierList.length > 0) {
      result.push({ title: t('threadList.sectionEarlier') || '更早', data: earlierList });
    }
    return result;
  }, [conversations, t]);

  // 渲染会话项
  const renderThreadItem = useCallback(({ item }: { item: Conversation }) => {
    const isActive = item.id === currentConversationId;
    const unreadCount = getUnreadCount(item.id);

    return (
      <Swipeable
        renderRightActions={() => (
          <View style={styles.actionsContainer}>
            <TouchableOpacity
              style={[styles.pinAction, { backgroundColor: colors.secondary }]}
              onPress={() => togglePinConversation(item.id)}
            >
              <MaterialIcons
                name="push-pin"
                size={20}
                color={colors.onPrimary}
              />
              <Text style={{ color: colors.onPrimary, fontSize: 11, marginTop: 2 }}>
                {item.is_pinned ? t('threadList.unpin') || '取消置顶' : t('threadList.pin') || '置顶'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.deleteActionTouch, { backgroundColor: colors.error }]}
              onPress={() => handleDelete(item.id)}
            >
              <MaterialIcons
                name="delete"
                size={20}
                color={colors.onError}
              />
              <Text style={{ color: colors.onError, fontSize: 11, marginTop: 2 }}>
                {t('chat.messageActions.delete') || '删除'}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      >
        <TouchableOpacity
          style={[
            styles.threadItem,
            { backgroundColor: isActive ? colors.primaryContainer : (item.is_pinned ? colors.surfaceVariant + '40' : 'transparent') },
          ]}
          onPress={() => handleSelectThread(item)}
          onLongPress={() => handleOpenRename(item.id, item.title)}
        >
          <View style={styles.threadContent}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}>
              {!!item.is_pinned && (
                <MaterialIcons
                  name="push-pin"
                  size={14}
                  color={isActive ? colors.primary : colors.onSurfaceVariant}
                  style={{ marginRight: 4 }}
                />
              )}
              <Text
                style={[
                  styles.threadTitle,
                  { color: isActive ? colors.primary : colors.onSurface, flex: 1, marginBottom: 0 },
                ]}
                numberOfLines={1}
              >
                {item.title || t('chat.threadList.newConversation')}
              </Text>
            </View>

            <Text style={[styles.threadMeta, { color: colors.onSurfaceVariant }]}>
              {formatDate.date(item.updated_at)}
            </Text>
          </View>

          {unreadCount > 0 && (
            <View style={styles.unreadBadge}>
              <Text style={styles.unreadBadgeText}>
                {unreadCount > 99 ? '99+' : unreadCount}
              </Text>
            </View>
          )}

          {isActive && (
            <MaterialIcons name="chevron-right" size={20} color={colors.primary} />
          )}
        </TouchableOpacity>
      </Swipeable>
    );
  }, [currentConversationId, colors, handleSelectThread, handleDelete, getUnreadCount, togglePinConversation, handleOpenRename, t]);

  // 渲染 Section 头部
  const renderSectionHeader = useCallback(({ section: { title } }: { section: { title: string } }) => (
    <View style={[styles.sectionHeader, { backgroundColor: colors.background }]}>
      <Text style={[styles.sectionHeaderText, { color: colors.primary }]}>{title}</Text>
    </View>
  ), [colors]);

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
      <View
        style={[
          styles.header,
          { borderBottomColor: colors.outline + '30' },
          Platform.OS === 'harmony' && {
            paddingTop: insets.top + 8,
            paddingBottom: 12,
          },
        ]}
      >
        <Text style={{ color: colors.onSurface, fontSize: 16, fontWeight: '600' }}>
          {t('threadList.title') || '对话列表'}
        </Text>

        <TouchableOpacity
          style={[styles.newThreadBtn, { backgroundColor: colors.primary }]}
          onPress={onNewThread}
        >
          <MaterialIcons name="add" size={18} color={colors.onPrimary} />
          <Text style={{ color: colors.onPrimary, fontSize: 13, marginLeft: 4 }}>
            {t('chat.threadList.newConversation')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* 会话列表 */}
      <SectionList
        sections={sections}
        keyExtractor={(item) => item.id}
        renderItem={renderThreadItem}
        renderSectionHeader={renderSectionHeader}
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
              {t('threadList.empty') || '暂无对话'}
            </Text>
            <TouchableOpacity
              style={[styles.newThreadButton, { backgroundColor: colors.primaryContainer }]}
              onPress={onNewThread}
            >
              <Text style={{ color: colors.primary }}>{t('threadList.startNew') || '开启新对话'}</Text>
            </TouchableOpacity>
          </View>
        }
        contentContainerStyle={conversations.length === 0 && styles.emptyContent}
      />

      {/* 重命名会话对话框 */}
      <Portal>
        <Dialog visible={renameVisible} onDismiss={() => setRenameVisible(false)}>
          <Dialog.Title>{t('threadList.renameTitle') || '会话重命名'}</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label={t('threadList.renamePlaceholder') || '请输入新的会话标题'}
              value={renameTitle}
              onChangeText={setRenameTitle}
              style={styles.dialogInput}
            />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setRenameVisible(false)}>{t('threadList.cancel') || '取消'}</Button>
            <Button onPress={handleRename}>{t('threadList.confirm') || '确定'}</Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
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
  threadContent: {
    flex: 1,
  },
  threadTitle: {
    fontSize: 15,
    fontWeight: '500',
  },
  threadMeta: {
    fontSize: 12,
  },
  actionsContainer: {
    flexDirection: 'row',
    width: 150,
    height: '100%',
  },
  pinAction: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteActionTouch: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  unreadBadge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#EF4444',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
    marginRight: 8,
  },
  unreadBadgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
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
  sectionHeader: {
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  sectionHeaderText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  dialogInput: {
    backgroundColor: 'transparent',
  },
});
