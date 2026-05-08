// 全屏加载组件

import React from 'react';
import { View, StyleSheet, Modal, ActivityIndicator } from 'react-native';
import { Text } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';

interface FullScreenLoaderProps {
  visible: boolean;
  message?: string;
  transparent?: boolean;
}

export function FullScreenLoader({
  visible,
  message,
  transparent = true,
}: FullScreenLoaderProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();

  return (
    <Modal
      transparent={transparent}
      visible={visible}
      animationType="fade"
      statusBarTranslucent
    >
      <View
        style={[
          styles.container,
          {
            backgroundColor: transparent
              ? 'rgba(0, 0, 0, 0.5)'
              : colors.background,
          },
        ]}
      >
        <View
          style={[
            styles.loaderContainer,
            { backgroundColor: colors.surface },
          ]}
        >
          <ActivityIndicator size="large" color={colors.primary} />
          {message && (
            <Text
              variant="bodyMedium"
              style={[styles.message, { color: colors.text.primary }]}
            >
              {message}
            </Text>
          )}
        </View>
      </View>
    </Modal>
  );
}

// 页面内加载
export function PageLoader({ message }: { message?: string }) {
  const { colors } = useTheme();

  return (
    <View style={[styles.pageLoader, { backgroundColor: colors.background }]}>
      <ActivityIndicator size="large" color={colors.primary} />
      {message && (
        <Text
          variant="bodyMedium"
          style={[styles.message, { color: colors.text.secondary }]}
        >
          {message}
        </Text>
      )}
    </View>
  );
}

// 内联加载
export function InlineLoader({ size = 'small' }: { size?: 'small' | 'large' }) {
  const { colors } = useTheme();

  return (
    <View style={styles.inlineLoader}>
      <ActivityIndicator size={size} color={colors.primary} />
    </View>
  );
}

// 底部加载更多
export function LoadMoreFooter({
  isLoading,
  hasMore,
}: {
  isLoading: boolean;
  hasMore: boolean;
}) {
  const { colors } = useTheme();

  if (!isLoading && !hasMore) {
    return (
      <View style={styles.loadMoreFooter}>
        <Text variant="bodySmall" style={{ color: colors.text.tertiary }}>
          {t('common.endReached')}
        </Text>
      </View>
    );
  }

  if (isLoading) {
    return (
      <View style={styles.loadMoreFooter}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  return null;
}

// 下拉刷新指示器
export function RefreshIndicator({ refreshing }: { refreshing: boolean }) {
  const { colors } = useTheme();

  if (!refreshing) return null;

  return (
    <View style={styles.refreshIndicator}>
      <ActivityIndicator size="small" color={colors.primary} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loaderContainer: {
    padding: 32,
    borderRadius: 16,
    alignItems: 'center',
    gap: 16,
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
  },
  message: {
    marginTop: 8,
  },
  pageLoader: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  inlineLoader: {
    padding: 16,
    alignItems: 'center',
  },
  loadMoreFooter: {
    padding: 16,
    alignItems: 'center',
  },
  refreshIndicator: {
    padding: 16,
    alignItems: 'center',
  },
});
