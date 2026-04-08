// 设备列表页面

import React, { useCallback } from 'react';
import { View, StyleSheet, FlatList, RefreshControl } from 'react-native';
import { Text, Portal, Dialog, Button, Snackbar } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useRouter } from 'expo-router';
import { useDevices } from '@/hooks/useDevices';
import { useAuthStore } from '@/stores/authStore';
import { DeviceCard } from '@/components/device/DeviceCard';
import { DeviceStatus } from '@/components/device/DeviceStatus';
import { Skeleton, ListSkeleton } from '@/components/ui/Skeleton';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { DeviceManager } from '@/services/devices/DeviceManager';
import { MaterialIcons } from '@expo/vector-icons';

// 游客模式下的登录提示组件
function GuestLoginPrompt() {
  const router = useRouter();
  const { t } = useTranslation();

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
          onPress={() => router.push('/(auth)/login')}
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

function DevicesContent() {
  const { t } = useTranslation();
  const router = useRouter();
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
  } = useDevices({ autoFetch: isLoggedIn }); // 只有登录后才自动获取

  const [refreshing, setRefreshing] = React.useState(false);
  const [selectedDevice, setSelectedDevice] = React.useState<string | null>(null);
  const [dialogVisible, setDialogVisible] = React.useState(false);
  const [snackbarVisible, setSnackbarVisible] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState('');

  // 游客模式显示登录提示
  if (!isLoggedIn) {
    return <GuestLoginPrompt />;
  }

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }, [refresh]);

  const handleDevicePress = useCallback((deviceId: string) => {
    const device = devices.find(d => d.id === deviceId);
    if (device) {
      setSelectedDevice(deviceId);
      setDialogVisible(true);
    }
  }, [devices]);

  const handleSetCurrent = useCallback(() => {
    const device = devices.find(d => d.id === selectedDevice);
    if (device) {
      setCurrentDevice(device);
      setSnackbarMessage(`已将 ${device.name} 设为当前设备`);
      setSnackbarVisible(true);
    }
    setDialogVisible(false);
  }, [selectedDevice, devices, setCurrentDevice]);

  const handleEnterChat = useCallback(() => {
    const device = devices.find(d => d.id === selectedDevice);
    if (device) {
      if (device.status !== 'online') {
        setSnackbarMessage('设备离线，无法进入对话');
        setSnackbarVisible(true);
        setDialogVisible(false);
        return;
      }
      setCurrentDevice(device);
      setDialogVisible(false);
      // 跳转到云端对话页面
      router.push({
        pathname: '/cloud-chat/new',
        params: { deviceId: device.id, deviceName: device.name }
      });
    }
  }, [selectedDevice, devices, setCurrentDevice, router]);

  const handleSendTestCommand = useCallback(async () => {
    const device = devices.find(d => d.id === selectedDevice);
    if (!device) return;

    if (device.status !== 'online') {
      setSnackbarMessage('设备离线，无法发送指令');
      setSnackbarVisible(true);
      setDialogVisible(false);
      return;
    }

    setDialogVisible(false);
    setSnackbarMessage('正在发送测试指令...');
    setSnackbarVisible(true);

    try {
      const result = await DeviceManager.sendCommand(
        device.id,
        'test',
        { message: 'Hello from Mobile!', timestamp: Date.now() }
      );
      setSnackbarMessage(`指令发送成功！ID: ${result?.command_id || 'N/A'}`);
      setSnackbarVisible(true);
    } catch (error: any) {
      setSnackbarMessage(`发送失败: ${error.message || '未知错误'}`);
      setSnackbarVisible(true);
    }
  }, [selectedDevice, devices]);

  const renderItem = useCallback(({ item }: { item: typeof devices[0] }) => (
    <DeviceCard
      device={item}
      isSelected={currentDevice?.id === item.id}
      onPress={() => handleDevicePress(item.id)}
    />
  ), [currentDevice, handleDevicePress]);

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
      <View style={styles.header}>
        <Text variant="headlineMedium" style={styles.title}>
          {t('devices.title')}
        </Text>
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
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      )}

      {/* 设备操作对话框 */}
      <Portal>
        <Dialog visible={dialogVisible} onDismiss={() => setDialogVisible(false)}>
          <Dialog.Title>
            {devices.find(d => d.id === selectedDevice)?.name || '设备操作'}
          </Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              状态: {devices.find(d => d.id === selectedDevice)?.status === 'online' ? '🟢 在线' : '🔴 离线'}
            </Text>
          </Dialog.Content>
          <Dialog.Actions style={styles.dialogActions}>
            <Button onPress={() => setDialogVisible(false)}>取消</Button>
            <Button 
              onPress={handleSetCurrent} 
              mode="outlined"
              disabled={selectedDevice === currentDevice?.id}
            >
              {selectedDevice === currentDevice?.id ? '当前设备' : '设为当前'}
            </Button>
            <Button 
              onPress={handleSendTestCommand}
              mode="outlined"
              disabled={devices.find(d => d.id === selectedDevice)?.status !== 'online'}
            >
              测试指令
            </Button>
            <Button 
              onPress={handleEnterChat}
              mode="contained"
              disabled={devices.find(d => d.id === selectedDevice)?.status !== 'online'}
            >
              进入对话
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

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
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
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
  },
  retryButton: {
    minWidth: 120,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#666',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#999',
  },
  dialogActions: {
    flexDirection: 'column',
    gap: 8,
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  // 游客模式样式
  guestContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
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
