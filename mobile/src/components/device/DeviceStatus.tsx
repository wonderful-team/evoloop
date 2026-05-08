// 设备状态指示器

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTranslation } from 'react-i18next';

interface DeviceStatusProps {
  online: number;
  total: number;
}

export function DeviceStatus({ online, total }: DeviceStatusProps) {
  const { t } = useTranslation();
  const offline = total - online;

  return (
    <View style={styles.container}>
      <View style={[styles.statCard, { backgroundColor: '#DCFCE7' }]}>
        <View style={[styles.dot, { backgroundColor: '#22C55E', shadowColor: '#22C55E', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 3, elevation: 2 }]} />
        <Text style={[styles.statNumber, { color: '#166534' }]}>{online}</Text>
        <Text style={[styles.statLabel, { color: '#166534' }]}>{t('devices.online')}</Text>
      </View>

      <View style={[styles.statCard, { backgroundColor: '#F3F4F6' }]}>
        <View style={[styles.dot, { backgroundColor: '#9CA3AF' }]} />
        <Text style={[styles.statNumber, { color: '#4B5563' }]}>{offline}</Text>
        <Text style={[styles.statLabel, { color: '#4B5563' }]}>{t('devices.offline')}</Text>
      </View>

      <View style={[styles.statCard, { backgroundColor: '#EFF6FF' }]}>
        <MaterialIcons name="devices" size={16} color="#2563EB" />
        <Text style={[styles.statNumber, { color: '#1E40AF' }]}>{total}</Text>
        <Text style={[styles.statLabel, { color: '#1E40AF' }]}>{t('devices.total')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 12,
  },
  statCard: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: '#f8f8f8',
    borderRadius: 10,
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statNumber: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1a1a1a',
  },
  statLabel: {
    fontSize: 13,
    color: '#666',
  },
});
