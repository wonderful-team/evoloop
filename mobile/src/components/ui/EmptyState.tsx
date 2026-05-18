// 空状态组件

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Button, IconButton } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
}

export function EmptyState({
  icon = 'inbox',
  title,
  description,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
}: EmptyStateProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  return (
    <View style={styles.container}>
      <View
        style={[
          styles.iconContainer,
          { backgroundColor: colors.surfaceVariant },
        ]}
      >
        <IconButton
          icon={icon}
          size={48}
          iconColor={colors.text.tertiary}
        />
      </View>

      <Text
        variant="titleMedium"
        style={[styles.title, { color: colors.text.primary }]}
      >
        {title}
      </Text>

      {description && (
        <Text
          variant="bodyMedium"
          style={[styles.description, { color: colors.text.secondary }]}
        >
          {description}
        </Text>
      )}

      <View style={styles.actions}>
        {actionLabel && onAction && (
          <Button
            mode="contained"
            onPress={onAction}
            style={styles.primaryAction}
          >
            {actionLabel}
          </Button>
        )}

        {secondaryActionLabel && onSecondaryAction && (
          <Button
            mode="text"
            onPress={onSecondaryAction}
            style={styles.secondaryAction}
          >
            {secondaryActionLabel}
          </Button>
        )}
      </View>
    </View>
  );
}

// 错误状态
export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon="alert-circle"
      title={title || t('emptyState.errorTitle')}
      description={description || t('emptyState.errorDesc')}
      actionLabel={onRetry ? t('common.retry') : undefined}
      onAction={onRetry}
    />
  );
}

// 网络错误状态
export function NetworkErrorState({ onRetry }: { onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon="wifi-off"
      title={t('emptyState.networkErrorTitle')}
      description={t('emptyState.networkErrorDesc')}
      actionLabel={onRetry ? t('common.retry') : undefined}
      onAction={onRetry}
    />
  );
}

// 搜索无结果状态
export function NoResultsState({
  keyword,
  onClear,
}: {
  keyword?: string;
  onClear?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon="magnify"
      title={keyword ? t('emptyState.noResultsFor', { keyword }) : t('emptyState.noResults')}
      description={t('emptyState.tryOtherKeywords')}
      actionLabel={onClear ? t('emptyState.clearFilters') : undefined}
      onAction={onClear}
    />
  );
}

// 需要登录状态
export function NeedLoginState({ onLogin }: { onLogin?: () => void }) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon="account-lock"
      title={t('emptyState.loginRequiredTitle')}
      description={t('emptyState.loginRequiredDesc')}
      actionLabel={onLogin ? t('emptyState.loginNow') : undefined}
      onAction={onLogin}
    />
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  iconContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  title: {
    marginBottom: 8,
    textAlign: 'center',
  },
  description: {
    textAlign: 'center',
    marginBottom: 24,
  },
  actions: {
    width: '100%',
    gap: 8,
  },
  primaryAction: {
    width: '100%',
  },
  secondaryAction: {
    width: '100%',
  },
});
