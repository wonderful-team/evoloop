// 设备状态指示器

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';

interface DeviceStatusProps {
  online: number;
  total: number;
}

export function DeviceStatus({ online, total }: DeviceStatusProps) {
  return (
    <View style={styles.container}>
      <View style={styles.item}>
        <View style={[styles.dot, { backgroundColor: '#00C853' }]} />
        <Text style={styles.text}>
          {online} 在线
        </Text>
      </View>
      <View style={styles.divider} />
      <View style={styles.item}>
        <View style={[styles.dot, { backgroundColor: '#9E9E9E' }]} />
        <Text style={styles.text}>
          {total - online} 离线
        </Text>
      </View>
      <View style={styles.divider} />
      <View style={styles.item}>
        <MaterialIcons name="devices" size={16} color="#666" />
        <Text style={styles.text}>
          {total} 总计
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#f8f8f8',
    borderRadius: 8,
    marginHorizontal: 16,
    marginVertical: 8,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  text: {
    fontSize: 14,
    color: '#666',
  },
  divider: {
    width: 1,
    height: 16,
    backgroundColor: '#ddd',
  },
});
