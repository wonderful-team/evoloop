// 设备卡片组件

import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { Device } from '@/types';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface DeviceCardProps {
  device: Device;
  isSelected?: boolean;
  onPress?: () => void;
  onCommandPress?: () => void;
}

export function DeviceCard({
  device,
  isSelected = false,
  onPress,
  onCommandPress,
}: DeviceCardProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  const getStatusColor = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return '#22C55E';
      case 'busy':
        return '#F59E0B';
      case 'offline':
      default:
        return '#9CA3AF';
    }
  };

  const getStatusBgColor = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return '#DCFCE7';
      case 'busy':
        return '#FEF3C7';
      case 'offline':
      default:
        return '#F3F4F6';
    }
  };

  const getStatusText = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return t('devices.online');
      case 'busy':
        return t('devices.busy');
      case 'offline':
      default:
        return t('devices.offline');
    }
  };

  const getDeviceIcon = (type: Device['type']) => {
    if (type === 'mobile' || type === 'phone') return 'smartphone';
    return 'computer';
  };

  // 格式化最后活跃时间
  const formatLastSeen = (lastSeen: string) => {
    const timestamp = parseInt(lastSeen, 10);
    if (isNaN(timestamp)) return lastSeen;

    const now = Date.now() / 1000;
    const diff = now - timestamp;

    if (diff < 60) return t('devices.timeAgo.justNow');
    if (diff < 3600) return t('devices.timeAgo.minutes', { count: Math.floor(diff / 60) });
    if (diff < 86400) return t('devices.timeAgo.hours', { count: Math.floor(diff / 3600) });
    return t('devices.timeAgo.days', { count: Math.floor(diff / 86400) });
  };

  return (
    <TouchableOpacity
      style={[styles.card, isSelected && { backgroundColor: colors.primaryContainer }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={styles.content}>
        <View style={styles.mainRow}>
          {/* 设备图标 */}
          <View style={styles.iconContainer}>
            <MaterialIcons
              name={getDeviceIcon(device.type)}
              size={28}
              color="#666"
            />
          </View>

          {/* 设备信息 */}
          <View style={styles.info}>
            <Text variant="titleMedium" style={styles.name} numberOfLines={1}>
              {device.name || `${t('devices.devicePrefix')} ${(device.deviceKey || t('common.unknown')).slice(0, 8)}`}
            </Text>
            {device.lastSeen && (
              <Text variant="bodySmall" style={styles.lastSeen}>
                {t('devices.lastActive')}{formatLastSeen(device.lastSeen)}
              </Text>
            )}
          </View>

          {/* 状态指示器 */}
          <View style={styles.rightSection}>
            {(device.unreadCount ?? 0) > 0 && (
              <View style={styles.unreadBadge}>
                <Text style={styles.unreadBadgeText}>
                  {device.unreadCount! > 99 ? t('common.overflowCount') : device.unreadCount}
                </Text>
              </View>
            )}
            <View style={[styles.statusBadge, { backgroundColor: getStatusBgColor(device.status) }]}>
              <View style={[
                styles.statusDot,
                { backgroundColor: getStatusColor(device.status) },
                device.status === 'online' && styles.statusDotOnline,
              ]} />
              <Text style={[styles.statusText, { color: getStatusColor(device.status) }]}>
                {getStatusText(device.status)}
              </Text>
            </View>
          </View>
        </View>

      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginVertical: 4,
    borderRadius: 0,
    backgroundColor: '#fff',
  },
  content: {
    padding: 16,
  },
  mainRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconContainer: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: '#f5f5f5',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  info: {
    flex: 1,
    justifyContent: 'center',
  },
  name: {
    fontWeight: '600',
    fontSize: 16,
    color: '#1a1a1a',
    marginBottom: 2,
  },
  lastSeen: {
    fontSize: 12,
    color: '#999',
  },
  rightSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  unreadBadge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#EF4444',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
  },
  unreadBadgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 5,
  },
  statusDotOnline: {
    shadowColor: '#22C55E',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 4,
    elevation: 3,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
});
