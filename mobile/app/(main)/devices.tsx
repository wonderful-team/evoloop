// 设备列表页面

import React, { useCallback } from 'react';
import { View, StyleSheet, FlatList, RefreshControl } from 'react-native';
import { Text, FAB, Portal, Dialog, Button } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useDevices } from '@/hooks/useDevices';
import { DeviceCard } from '@/components/device/DeviceCard';
import { DeviceStatus } from '@/components/device/DeviceStatus';
import { QRScanner } from '@/components/device/QRScanner';
import { Skeleton, ListSkeleton } from '@/components/ui/Skeleton';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';

function DevicesContent() {
  const { t } = useTranslation();
  const {
    devices,
    currentDevice,
    isLoading,
    error,
    onlineCount,
    totalCount,
    refresh,
    setCurrentDevice,
  } = useDevices({ autoFetch: true });

  const [refreshing, setRefreshing] = React.useState(false);
  const [selectedDevice, setSelectedDevice] = React.useState<string | null>(null);
  const [dialogVisible, setDialogVisible] = React.useState(false);
  const [scannerVisible, setScannerVisible] = React.useState(false);
  const [binding, setBinding] = React.useState(false);

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
    }
    setDialogVisible(false);
  }, [selectedDevice, devices, setCurrentDevice]);

  const handleScan = useCallback(async (data: string) => {
    setScannerVisible(false);
    setBinding(true);
    try {
      // TODO: 解析二维码数据并绑定设备
      console.log('扫描到的数据:', data);
      // await bindDevice(data);
    } finally {
      setBinding(false);
    }
  }, []);

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
          <Text style={styles.emptySubtext}>
            点击右下角按钮扫码绑定设备
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

      <Portal>
        <Dialog visible={dialogVisible} onDismiss={() => setDialogVisible(false)}>
          <Dialog.Title>设备操作</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              选择要执行的操作
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setDialogVisible(false)}>取消</Button>
            <Button onPress={handleSetCurrent} mode="contained">
              设为当前设备
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <FAB
        icon="qrcode-scan"
        style={styles.fab}
        onPress={() => setScannerVisible(true)}
        loading={binding}
        disabled={binding}
        label="绑定设备"
      />

      <QRScanner
        visible={scannerVisible}
        onClose={() => setScannerVisible(false)}
        onScan={handleScan}
      />
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
  fab: {
    position: 'absolute',
    margin: 16,
    right: 0,
    bottom: 0,
    backgroundColor: '#0066FF',
  },
});
