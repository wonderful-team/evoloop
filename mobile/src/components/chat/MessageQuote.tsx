// 消息引用组件 - 显示引用的消息或文件

import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { MessageReference } from '@/types/conversation';
import { useTranslation } from 'react-i18next';

interface MessageQuoteProps {
  reference: MessageReference;
  onRemove?: () => void;
  compact?: boolean;
  isUser?: boolean;
}

export function MessageQuote({ reference, onRemove, compact = false, isUser = false }: MessageQuoteProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  const getIcon = () => {
    switch (reference.type) {
      case 'message':
        return 'chat';
      case 'file':
        return 'insert-drive-file';
      case 'skill':
        return 'psychology';
      case 'memory':
        return 'memory';
      default:
        return 'link';
    }
  };

  const getTypeLabel = () => {
    switch (reference.type) {
      case 'message':
        return t('chat.quote.message');
      case 'file':
        return t('chat.quote.file');
      case 'skill':
        return t('chat.quote.skill');
      case 'memory':
        return t('chat.quote.memory');
      default:
        return t('chat.quote.reference');
    }
  };

  if (compact) {
    return (
      <View style={[styles.compactContainer, { backgroundColor: isUser ? 'rgba(255,255,255,0.15)' : colors.primaryContainer }]}>
        <MaterialIcons name={getIcon()} size={14} color={isUser ? '#fff' : colors.primary} />
        <Text variant="bodySmall" style={[styles.compactText, { color: isUser ? '#fff' : colors.primary }]} numberOfLines={1}>
          {reference.name}
        </Text>
        {onRemove && (
          <TouchableOpacity onPress={onRemove} style={styles.removeBtn}>
            <MaterialIcons name="close" size={14} color={isUser ? '#fff' : colors.primary} />
          </TouchableOpacity>
        )}
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: isUser ? 'rgba(0,0,0,0.06)' : colors.surfaceVariant }]}>
      <View style={styles.header}>
        <View style={styles.typeBadge}>
          <MaterialIcons name={getIcon()} size={12} color={isUser ? colors.onPrimaryContainer : colors.primary} />
          <Text variant="labelSmall" style={{ color: isUser ? colors.onPrimaryContainer : colors.primary, marginLeft: 4 }}>
            {getTypeLabel()}
          </Text>
        </View>
        {onRemove && (
          <IconButton icon="close" size={16} iconColor={isUser ? colors.onPrimaryContainer : undefined} onPress={onRemove} style={styles.closeBtn} />
        )}
      </View>
      <Text variant="bodyMedium" style={{ color: isUser ? colors.onPrimaryContainer : colors.onSurface }} numberOfLines={2}>
        {reference.name}
      </Text>
      {reference.detail && (
        <Text variant="bodySmall" style={{ color: isUser ? 'rgba(0,0,0,0.5)' : colors.onSurfaceVariant, marginTop: 4 }} numberOfLines={1}>
          {reference.detail}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 8,
    padding: 12,
    marginVertical: 4,
  },
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 4,
    marginRight: 8,
    marginBottom: 4,
  },
  compactText: {
    marginLeft: 4,
    maxWidth: 120,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  typeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  closeBtn: {
    margin: 0,
    padding: 0,
  },
  removeBtn: {
    marginLeft: 4,
    padding: 2,
  },
});
