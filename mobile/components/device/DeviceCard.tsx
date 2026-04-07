// 设备卡片组件

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, IconButton, Chip } from 'react-native-paper';
import { MaterialIcons } from '@expo/vector-icons';
import { Device } from '@/types';

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
  const getStatusColor = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return '#00C853';
      case 'busy':
        return '#FFAB00';
      case 'offline':
      default:
        return '#9E9E9E';
    }
  };

  const getStatusText = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return '在线';
      case 'busy':
        return '忙碌';
      case 'offline':
      default:
        return '离线';
    }
  };

  const getDeviceIcon = (type: Device['type']) => {
    return type === 'desktop' ? 'computer' : 'smartphone';
  };

  return (
    <Card
      style={[styles.card, isSelected && styles.selectedCard]}
      onPress={onPress}
    >
      <Card.Content>
        <View style={styles.header}>
          <View style={styles.iconContainer}>
            <MaterialIcons
              name={getDeviceIcon(device.type)}
              size={32}
              color="#666"
            />
          </View>
          <View style={styles.info}>
            <Text variant="titleMedium" style={styles.name}>
              {device.name || `设备 ${device.id.slice(0, 8)}`}
            </Text>
            <Text variant="bodySmall" style={styles.osInfo}>
              {device.osInfo}
            </Text>
          </View>
          <View style={styles.status}>
            <View
              style={[
                styles.statusDot,
                { backgroundColor: getStatusColor(device.status) },
              ]}
            />
            <Chip
              compact
              style={{ backgroundColor: `${getStatusColor(device.status)}20` }}
              textStyle={{ color: getStatusColor(device.status), fontSize: 12 }}
            >
              {getStatusText(device.status)}
            </Chip>
          </View>
        </View>

        {device.currentProject && (
          <View style={styles.projectContainer}>
            <MaterialIcons name="folder" size={16} color="#666" />
            <Text variant="bodySmall" style={styles.projectName}>
              {device.currentProject.name}
            </Text>
          </View>
        )}
      </Card.Content>

      {device.status === 'online' && (
        <Card.Actions>
          <IconButton
            icon="send"
            size={20}
            onPress={onCommandPress}
            iconColor="#0066FF"
          />
        </Card.Actions>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginVertical: 8,
    elevation: 2,
  },
  selectedCard: {
    borderWidth: 2,
    borderColor: '#0066FF',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#f0f0f0',
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
  osInfo: {
    opacity: 0.6,
    marginTop: 2,
  },
  status: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  projectContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  projectName: {
    marginLeft: 6,
    opacity: 0.8,
  },
});
