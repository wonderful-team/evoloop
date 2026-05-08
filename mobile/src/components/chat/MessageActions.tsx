// 消息操作菜单组件 - 支持复制、删除、转发、收藏等

import React, { useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Share,
} from 'react-native';
import {
  Menu,
  Portal,
  Dialog,
  Button,
  Text,
} from 'react-native-paper';
import { useTheme } from '@/theme';
import Clipboard from '@react-native-clipboard/clipboard';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTranslation } from 'react-i18next';

interface MessageActionsProps {
  messageId: string;
  content: string;
  isUser: boolean;
  onDelete?: (id: string) => void;
  onForward?: (content: string) => void;
  onFavorite?: (content: string) => void;
  children: React.ReactNode;
}

// 操作按钮项
interface ActionItem {
  icon: keyof typeof MaterialIcons.glyphMap;
  label: string;
  onPress: () => void;
  destructive?: boolean;
}

export function MessageActions({
  messageId,
  content,
  isUser,
  onDelete,
  onForward,
  onFavorite,
  children,
}: MessageActionsProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const [menuVisible, setMenuVisible] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [copied, setCopied] = useState(false);

  // 复制消息内容
  const handleCopy = useCallback(() => {
    Clipboard.setString(content);
    setCopied(true);
    setMenuVisible(false);
    setTimeout(() => setCopied(false), 2000);
  }, [content]);

  // 分享消息
  const handleShare = useCallback(async () => {
    try {
      await Share.share({
        message: content,
      });
    } catch (error) {
      console.error('分享失败:', error);
    }
    setMenuVisible(false);
  }, [content]);

  // 转发消息
  const handleForward = useCallback(() => {
    onForward?.(content);
    setMenuVisible(false);
  }, [content, onForward]);

  // 收藏消息
  const handleFavorite = useCallback(() => {
    onFavorite?.(content);
    setMenuVisible(false);
  }, [content, onFavorite]);

  // 删除消息
  const handleDelete = useCallback(() => {
    setShowDeleteConfirm(true);
    setMenuVisible(false);
  }, []);

  const confirmDelete = useCallback(() => {
    onDelete?.(messageId);
    setShowDeleteConfirm(false);
  }, [messageId, onDelete]);

  // 生成操作项
  const actionItems: ActionItem[] = [
    { icon: 'content-copy', label: copied ? t('chat.messageActions.copied') : t('chat.messageActions.copy'), onPress: handleCopy },
    { icon: 'share', label: t('chat.messageActions.share'), onPress: handleShare },
    ...(onForward ? [{ icon: 'reply' as const, label: t('chat.messageActions.forward'), onPress: handleForward }] : []),
    ...(onFavorite ? [{ icon: 'star-border' as const, label: t('chat.messageActions.favorite'), onPress: handleFavorite }] : []),
    ...(onDelete ? [{ icon: 'delete' as const, label: t('chat.messageActions.delete'), onPress: handleDelete, destructive: true }] : []),
  ];

  return (
    <>
      <Menu
        visible={menuVisible}
        onDismiss={() => setMenuVisible(false)}
        anchor={
          <TouchableOpacity
            onLongPress={() => setMenuVisible(true)}
            activeOpacity={0.9}
          >
            {children}
          </TouchableOpacity>
        }
        contentStyle={[
          styles.menuContent,
          { backgroundColor: colors.surface },
        ]}
      >
        {actionItems.map((item, index) => (
          <Menu.Item
            key={index}
            onPress={item.onPress}
            title={item.label}
            leadingIcon={item.icon}
            titleStyle={item.destructive ? { color: colors.error } : undefined}
            style={item.destructive ? { backgroundColor: colors.errorContainer + '20' } : undefined}
          />
        ))}
      </Menu>

      {/* 删除确认对话框 */}
      <Portal>
        <Dialog
          visible={showDeleteConfirm}
          onDismiss={() => setShowDeleteConfirm(false)}
        >
          <Dialog.Title>{t('chat.messageActions.deleteConfirmTitle')}</Dialog.Title>
          <Dialog.Content>
            <Text>{t('chat.messageActions.deleteConfirmDesc')}</Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowDeleteConfirm(false)}>{t('common.cancel')}</Button>
            <Button onPress={confirmDelete} textColor={colors.error}>
              {t('chat.messageActions.delete')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </>
  );
}

// 简化版操作栏（用于消息气泡底部）
interface MessageActionBarProps {
  content: string;
  onCopy?: () => void;
  onRetry?: () => void;
  onDelete?: () => void;
  showRetry?: boolean;
}

export function MessageActionBar({
  content,
  onCopy,
  onRetry,
  onDelete,
  showRetry,
}: MessageActionBarProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    Clipboard.setString(content);
    setCopied(true);
    onCopy?.();
    setTimeout(() => setCopied(false), 2000);
  }, [content, onCopy]);

  return (
    <View style={styles.actionBar}>
      <TouchableOpacity
        style={styles.actionButton}
        onPress={handleCopy}
      >
        <MaterialIcons
          name={copied ? 'check' : 'content-copy'}
          size={16}
          color={copied ? colors.primary : colors.onSurfaceVariant}
        />
        <Text style={[styles.actionText, { color: copied ? colors.primary : colors.onSurfaceVariant }]}>
          {copied ? t('chat.messageActions.copied') : t('chat.messageActions.copy')}
        </Text>
      </TouchableOpacity>

      {showRetry && onRetry && (
        <TouchableOpacity
          style={styles.actionButton}
          onPress={onRetry}
        >
          <MaterialIcons name="refresh" size={16} color={colors.onSurfaceVariant} />
          <Text style={[styles.actionText, { color: colors.onSurfaceVariant }]}>{t('chat.messageActions.retry')}</Text>
        </TouchableOpacity>
      )}

      {onDelete && (
        <TouchableOpacity
          style={styles.actionButton}
          onPress={onDelete}
        >
          <MaterialIcons name="delete-outline" size={16} color={colors.error} />
          <Text style={[styles.actionText, { color: colors.error }]}>{t('chat.messageActions.delete')}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  menuContent: {
    borderRadius: 12,
    marginTop: 8,
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: 4,
    paddingHorizontal: 4,
    gap: 12,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    padding: 4,
  },
  actionText: {
    fontSize: 12,
  },
});
