// 配额耗尽交互卡片 - 对应 Desktop 的 QuotaExhaustedCard
// 显示在消息列表底部，提供查看配额和继续操作

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { router } from '@/utils/navigation';

export interface QuotaExhaustedInfo {
  title?: string;
  message?: string;
  hint?: string;
  actionText?: string;
}

interface QuotaExhaustedCardProps {
  info?: QuotaExhaustedInfo | null;
  onContinue?: () => void;
}

export function QuotaExhaustedCard({ info, onContinue }: QuotaExhaustedCardProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  const handleCheckQuota = () => {
    router.push('Plans');
  };

  return (
    <Card
      style={[
        styles.container,
        {
          backgroundColor: colors.errorContainer + '20',
          borderColor: colors.error + '30',
        },
      ]}
    >
      {/* 头部 */}
      <Card.Content style={styles.header}>
        <MaterialIcons name="warning" size={20} color={colors.error} />
        <Text style={[styles.title, { color: colors.error }]}>
          {info?.title || t('chat.quota.card.title')}
        </Text>
      </Card.Content>

      {/* 主消息 */}
      <Card.Content style={styles.messageSection}>
        <Text style={[styles.message, { color: colors.onSurface }]}>
          {info?.message || t('chat.quota.card.message')}
        </Text>
      </Card.Content>

      {/* 提示 */}
      {info?.hint && (
        <Card.Content style={styles.hintSection}>
          <View style={[styles.hintBox, { backgroundColor: colors.errorContainer + '40' }]}>
            <Text style={[styles.hintText, { color: colors.onSurfaceVariant }]}>
              {info.hint}
            </Text>
          </View>
        </Card.Content>
      )}

      {/* 操作说明 */}
      <Card.Content style={styles.infoSection}>
        <Text style={[styles.infoText, { color: colors.onSurfaceVariant }]}>
          {t('chat.quota.card.info')}
        </Text>
        <View style={styles.options}>
          <View style={styles.optionItem}>
            <MaterialIcons name="check-circle" size={14} color={colors.onSurfaceVariant} />
            <Text style={[styles.optionText, { color: colors.onSurfaceVariant }]}>
              {t('chat.quota.card.option1')}
            </Text>
          </View>
          <View style={styles.optionItem}>
            <MaterialIcons name="check-circle" size={14} color={colors.onSurfaceVariant} />
            <Text style={[styles.optionText, { color: colors.onSurfaceVariant }]}>
              {t('chat.quota.card.option2')}
            </Text>
          </View>
        </View>
      </Card.Content>

      {/* 按钮区域 */}
      <Card.Actions style={styles.actions}>
        <Button
          mode="outlined"
          onPress={handleCheckQuota}
          style={[styles.button, { borderColor: colors.error + '50' }]}
          textColor={colors.error}
          icon="open-in-new"
        >
          {info?.actionText || t('chat.quota.card.checkQuota')}
        </Button>
        <Button
          mode="contained"
          onPress={onContinue}
          style={[styles.button, { backgroundColor: colors.error }]}
          textColor={colors.onError}
          icon="refresh"
        >
          {t('chat.quota.card.continue')}
        </Button>
      </Card.Actions>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginVertical: 8,
    borderRadius: 12,
    borderWidth: 1,
    elevation: 2,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingBottom: 8,
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
  },
  messageSection: {
    paddingBottom: 8,
  },
  message: {
    fontSize: 14,
    fontWeight: '500',
    lineHeight: 20,
  },
  hintSection: {
    paddingBottom: 8,
  },
  hintBox: {
    padding: 10,
    borderRadius: 8,
  },
  hintText: {
    fontSize: 13,
    lineHeight: 18,
  },
  infoSection: {
    paddingBottom: 8,
  },
  infoText: {
    fontSize: 13,
    marginBottom: 4,
  },
  options: {
    gap: 4,
  },
  optionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  optionText: {
    fontSize: 13,
  },
  actions: {
    justifyContent: 'flex-end',
    paddingHorizontal: 16,
    paddingBottom: 12,
    gap: 8,
  },
  button: {
    borderRadius: 8,
    flex: 1,
  },
});
