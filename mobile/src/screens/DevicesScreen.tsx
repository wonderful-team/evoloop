// 设备列表页面

import React, { useCallback } from 'react';
import { View, StyleSheet, FlatList, RefreshControl } from 'react-native';
import { Text, Button, Snackbar } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from '@/utils/navigation';
import { useDevices } from '@/hooks/useDevices';
import { useAuthStore } from '@/stores/authStore';
import { DeviceCard } from '@/components/device/DeviceCard';
import { DeviceStatus } from '@/components/device/DeviceStatus';
import { Skeleton, ListSkeleton } from '@/components/ui/Skeleton';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Header } from '@/components/common/Header';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

// 游客模式下的登录提示组件
function GuestLoginPrompt() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.guestContainer}>
        <MaterialIcons name="desktop-mac" size={64} color="#9CA3AF" />
        <Text variant="headlineMedium" style={styles.guestTitle}>
          设备管理
        </Text>
        <Text variant="bodyMedium" style={styles.guestText}>
          登录后可以查看和管理您的设备，进行云端对话等功能
        </Text>
        <Button
          mode="contained"
          style={styles.loginButton}
          onPress={() => router.push('Auth')}
        >
          立即登录
        </Button>
        <Button
          mode="text"
          style={styles.backButton}
          onPress={() => router.back()}
        >
          返回首页
        </Button>
      </View>
    </SafeAreaView>
  );
}

const DevicesContent = () => {
  const { t } = useTranslation();
  const { isLoggedIn } = useAuthStore();
  const {
    devices,
    currentDevice,
    isLoading,
    error,
    onlineCount,
    totalCount,
    refresh,
    setCurrentDevice,
  } = useDevices({ autoFetch: isLoggedIn });

  const [refreshing, setRefreshing] = React.useState(false);
  const [snackbarVisible, setSnackbarVisible] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState('');

  const onRefresh = useCallback(async () => {
    if (!isLoggedIn) return;
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }, [refresh, isLoggedIn]);

  // 点击设备直接进入聊天
  const handleDevicePress = useCallback((device: typeof devices[0]) => {
    if (!isLoggedIn) return;
    if (device.status !== 'online') {
      setSnackbarMessage('设备离线，无法进入对话');
      setSnackbarVisible(true);
      return;
    }
    // 设置为当前设备
    setCurrentDevice(device);
    // 返回聊天页面
    router.back();
  }, [setCurrentDevice, isLoggedIn]);

  const renderItem = useCallback(({ item }: { item: typeof devices[0] }) => (
    <DeviceCard
      device={item}
      isSelected={currentDevice?.deviceKey === item.deviceKey}
      onPress={() => handleDevicePress(item)}
    />
  ), [currentDevice, handleDevicePress]);

  // 游客模式显示登录提示（放在所有 hooks 之后）
  if (!isLoggedIn) {
    return <GuestLoginPrompt />;
  }

  if (isLoading && devices.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <Skeleton width={150} height={28} />
        </View>
        <ListSkeleton count={5} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <Header title="我的设备" showBack />

      <View style={styles.header}>
        <View style={styles.headerTop}>
          <Text variant="bodyMedium" style={styles.subtitle}>
            {totalCount > 0 ? `共 ${totalCount} 台设备` : '管理您的 EvoLoop 设备'}
          </Text>
        </View>
        {totalCount > 0 && (
          <DeviceStatus online={onlineCount} total={totalCount} />
        )}
      </View>

      {error ? (
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>
            加载失败: {error.message}
          </Text>
          <Button onPress={refresh} mode="contained" style={styles.retryButton}>
            重试
          </Button>
        </View>
      ) : devices.length === 0 ? (
        <View style={styles.centerContent}>
          <Text style={styles.emptyText}>
            {t('devices.noDevices')}
          </Text>
        </View>
      ) : (
        <FlatList
          data={devices}
          renderItem={renderItem}
          keyExtractor={(item) => item.deviceKey}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      )}

      {/* 提示消息 */}
      <Snackbar
        visible={snackbarVisible}
        onDismiss={() => setSnackbarVisible(false)}
        duration={3000}
        action={{
          label: '关闭',
          onPress: () => setSnackbarVisible(false),
        }}
      >
        {snackbarMessage}
      </Snackbar>
    </SafeAreaView>
  );
}

export default function DevicesScreen() {
  return (
    <ErrorBoundary>
      <DevicesContent />
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  headerTop: {
    marginBottom: 12,
  },
  title: {
    fontWeight: '700',
    fontSize: 24,
    color: '#242424',
    marginBottom: 4,
  },
  subtitle: {
    color: '#757575',
    fontSize: 14,
  },
  list: {
    paddingVertical: 8,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  errorText: {
    color: '#FF3D00',
    marginBottom: 16,
    fontSize: 16,
  },
  retryButton: {
    minWidth: 120,
    marginTop: 8,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#757575',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#A0A0A0',
  },
  // 游客模式样式
  guestContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
    backgroundColor: '#fff',
  },
  guestTitle: {
    fontWeight: 'bold',
    marginTop: 24,
    marginBottom: 12,
  },
  guestText: {
    textAlign: 'center',
    color: '#6B7280',
    marginBottom: 32,
    lineHeight: 22,
  },
  loginButton: {
    minWidth: 200,
    marginBottom: 12,
  },
  backButton: {
    minWidth: 200,
  },
});
