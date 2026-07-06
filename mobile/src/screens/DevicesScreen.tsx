// 设备列表页面

import React, { useCallback } from 'react';
import { View, StyleSheet, FlatList, RefreshControl } from 'react-native';
import { Text, Button, Snackbar, Card, Chip } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
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
  const { t } = useTranslation();
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.guestContainer}>
        <MaterialIcons name="desktop-mac" size={64} color="#9CA3AF" />
        <Text variant="headlineMedium" style={styles.guestTitle}>
          {t('devices.managementTitle')}
        </Text>
        <Text variant="bodyMedium" style={styles.guestText}>
          {t('devices.guestDesc')}
        </Text>
        <Button
          mode="contained"
          style={styles.loginButton}
          onPress={() => router.push('Auth')}
        >
          {t('auth.login.submit')}
        </Button>
        <Button
          mode="text"
          style={styles.backButton}
          onPress={() => router.back()}
        >
          {t('devices.backToHome')}
        </Button>
      </View>
    </SafeAreaView>
  );
}

const DevicesContent = () => {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { isLoggedIn } = useAuthStore();
  const {
    devices,
    currentDevice,
    isLoading,
    error,
    onlineCount,
    totalCount,
    refresh,
    switchDevice,
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
      setSnackbarMessage(t('devices.deviceOffline'));
      setSnackbarVisible(true);
      return;
    }
    // 设置为当前设备（原子化更新 device + conversation store）
    switchDevice(device);
    // 返回聊天页面
    router.back();
  }, [switchDevice, isLoggedIn]);

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
      <Header title={t('devices.myDevices')} showBack />

      <View style={styles.header}>
        <View style={styles.headerTop}>
          <Text variant="bodyMedium" style={styles.subtitle}>
            {totalCount > 0 ? t('devices.totalCount', { count: totalCount }) : t('devices.manageSubtitle')}
          </Text>
        </View>
        {totalCount > 0 && (
          <DeviceStatus online={onlineCount} total={totalCount} />
        )}
      </View>

      {error ? (
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>
            {t('devices.loadFailed')}{error.message}
          </Text>
          <Button onPress={refresh} mode="contained" style={styles.retryButton}>
            {t('common.retry')}
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
          ListHeaderComponent={
              <Card
                style={[
                  styles.card,
                  styles.cloudCard,
                  !currentDevice && [styles.activeCard, { borderColor: colors.primary }]
                ]}
                onPress={() => {
                  switchDevice(null);
                  router.back();
                }}
            >
              <Card.Content>
                <View style={styles.itemHeader}>
                  <View style={[styles.iconContainer, { backgroundColor: '#E3F2FD' }]}>
                    <MaterialIcons name="cloud" size={28} color="#1976D2" />
                  </View>
                  <View style={styles.info}>
                    <Text variant="titleMedium" style={styles.name}>
                      {t('devices.cloudModeTitle')}
                    </Text>
                    <Text variant="bodySmall" style={styles.path}>
                      {t('devices.cloudModeDesc')}
                    </Text>
                  </View>
                  {!currentDevice && (
                    <Chip
                      icon="check-circle"
                      compact
                      style={[styles.activeChip, { backgroundColor: colors.primaryContainer }]}
                      textStyle={{ color: colors.primary }}
                    >
                      {t('projects.current')}
                    </Chip>
                  )}
                </View>
              </Card.Content>
            </Card>
          }
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
          label: t('common.close'),
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
    padding: 8,
  },
  card: {
    marginHorizontal: 8,
    marginVertical: 6,
  },
  activeCard: {
    borderWidth: 2,
  },
  cloudCard: {
    marginBottom: 12,
    backgroundColor: '#FAFBFC',
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  info: {
    flex: 1,
  },
  name: {
    fontWeight: '600',
  },
  path: {
    opacity: 0.6,
    marginTop: 2,
  },
  activeChip: {
    backgroundColor: 'transparent',
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
