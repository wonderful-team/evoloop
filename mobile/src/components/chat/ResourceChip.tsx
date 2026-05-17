// 资源片段组件 - 显示引用的消息或文件 (对齐桌面端 ResourceChip)

import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { MessageReference } from '@/types/conversation';
import { useTranslation } from 'react-i18next';

interface ResourceChipProps {
  reference: MessageReference;
  onRemove?: () => void;
  compact?: boolean;
  isUser?: boolean;
}

export function ResourceChip({ reference, onRemove, compact = false, isUser = false }: ResourceChipProps) {
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
      case 'image':
        return 'image';
      case 'audio':
        return 'audiotrack';
      case 'artifact':
        return 'widgets';
      case 'changeset':
        return 'code';
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
      case 'image':
        return t('chat.quote.image');
      case 'audio':
        return t('chat.quote.audio');
      case 'artifact':
        return t('chat.quote.artifact');
      case 'changeset':
        return t('chat.quote.changeset');
      default:
        return t('chat.quote.reference');
    }
  };

  const getCompactColors = () => {
    if (isUser) {
      return {
        bg: 'rgba(0, 0, 0, 0.05)',
        text: colors.onPrimaryContainer,
        border: 'rgba(0, 0, 0, 0.1)',
      };
    }
    switch (reference.type) {
      case 'skill':
        return { bg: 'rgba(245, 158, 11, 0.1)', text: '#d97706', border: 'rgba(245, 158, 11, 0.2)' }; // Amber
      case 'message':
        return { bg: 'rgba(59, 130, 246, 0.1)', text: '#2563eb', border: 'rgba(59, 130, 246, 0.2)' }; // Blue
      case 'changeset':
        return { bg: 'rgba(147, 51, 234, 0.1)', text: '#7c3aed', border: 'rgba(147, 51, 234, 0.2)' }; // Purple
      default:
        return { bg: colors.surfaceVariant, text: colors.onSurfaceVariant, border: 'transparent' };
    }
  };

  if (compact) {
    const compactColors = getCompactColors();
    return (
      <View style={[styles.compactContainer, { backgroundColor: compactColors.bg, borderColor: compactColors.border, borderWidth: 1 }]}>
        <MaterialIcons name={getIcon()} size={14} color={compactColors.text} />
        <Text variant="bodySmall" style={[styles.compactText, { color: compactColors.text }]} numberOfLines={1}>
          {reference.target_name}
        </Text>
        {onRemove && (
          <TouchableOpacity onPress={onRemove} style={styles.removeBtn}>
            <MaterialIcons name="close" size={14} color={compactColors.text} />
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
        {reference.target_name}
      </Text>
      {reference.meta_data?.detail && (
        <Text variant="bodySmall" style={{ color: isUser ? 'rgba(0,0,0,0.5)' : colors.onSurfaceVariant, marginTop: 4 }} numberOfLines={1}>
          {reference.meta_data.detail}
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
