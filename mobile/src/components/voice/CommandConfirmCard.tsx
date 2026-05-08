// 指令确认卡片 - 显示待执行的设备指令

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, Divider } from 'react-native-paper';
import { TaskCommand } from '@/types/voice';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface CommandConfirmCardProps {
  command: TaskCommand;
  onConfirm: () => void;
  onCancel: () => void;
}

export function CommandConfirmCard({
  command,
  onConfirm,
  onCancel,
}: CommandConfirmCardProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();

  // 获取动作显示文本
  const getActionText = (action: string) => {
    return t(`voice.command.actionMap.${action}`, { defaultValue: action });
  };

  // 翻译参数名
  const translateParameterKey = (key: string): string => {
    return t(`voice.command.paramMap.${key}`, { defaultValue: key });
  };

  // 获取参数显示文本
  const renderParameters = () => {
    if (!command.parameters || Object.keys(command.parameters).length === 0) {
      return null;
    }

    return (
      <View style={styles.parametersContainer}>
        {Object.entries(command.parameters).map(([key, value]) => (
          <View key={key} style={styles.parameterRow}>
            <Text
              variant="bodySmall"
              style={[styles.parameterKey, { color: colors.text.tertiary }]}
            >
              {translateParameterKey(key)}:
            </Text>
            <Text
              variant="bodyMedium"
              style={[styles.parameterValue, { color: colors.text.primary }]}
            >
              {formatParameterValue(key, value, t('voice.command.second'))}
            </Text>
          </View>
        ))}
      </View>
    );
  };

  // 获取设备图标
  const getDeviceIcon = () => {
    const iconMap: Record<string, string> = {
      light: 'lightbulb',
      switch: 'toggle-switch',
      lock: 'lock',
      thermostat: 'thermometer',
      camera: 'camera',
      sensor: 'access-point',
      speaker: 'speaker',
    };
    return iconMap[command.deviceType || ''] || 'devices';
  };

  return (
    <Card style={[styles.container, { backgroundColor: colors.warningContainer }]}>
      <Card.Content>
        {/* 标题 */}
        <View style={styles.header}>
          <Text variant="titleMedium" style={{ color: colors.onWarningContainer }}>
            {t('voice.command.title')}
          </Text>
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: colors.warning },
            ]}
          >
            <Text variant="labelSmall" style={{ color: colors.onWarning }}>
              {t('voice.command.pending')}
            </Text>
          </View>
        </View>

        <Divider style={[styles.divider, { backgroundColor: colors.outlineVariant }]} />

        {/* 设备信息 */}
        <View style={styles.deviceInfo}>
          <Text
            variant="bodySmall"
            style={[styles.label, { color: colors.text.tertiary }]}
          >
            {t('voice.command.device')}
          </Text>
          <Text variant="bodyLarge" style={{ color: colors.onWarningContainer }}>
            {command.deviceName || t('voice.command.unknownDevice')}
          </Text>
        </View>

        {/* 动作信息 */}
        <View style={styles.actionInfo}>
          <Text
            variant="bodySmall"
            style={[styles.label, { color: colors.text.tertiary }]}
          >
            {t('voice.command.action')}
          </Text>
          <Text variant="bodyLarge" style={{ color: colors.onWarningContainer }}>
            {getActionText(command.action)}
          </Text>
        </View>

        {/* 参数 */}
        {renderParameters()}
      </Card.Content>

      {/* 操作按钮 */}
      <Card.Actions style={styles.actions}>
        <Button
          mode="outlined"
          onPress={onCancel}
          style={styles.button}
          textColor={colors.onWarningContainer}
        >
          {t('voice.command.cancel')}
        </Button>
        <Button
          mode="contained"
          onPress={onConfirm}
          style={[styles.button, { backgroundColor: colors.warning }]}
          textColor={colors.onWarning}
        >
          {t('voice.command.confirm')}
        </Button>
      </Card.Actions>
    </Card>
  );
}

// 格式化参数值
function formatParameterValue(key: string, value: any, secondLabel: string): string {
  if (key === 'brightness') {
    return `${value}%`;
  }
  if (key === 'temperature') {
    return `${value}°C`;
  }
  if (key === 'duration' || key === 'delay') {
    return `${value}${secondLabel}`;
  }
  return String(value);
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 8,
    borderRadius: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
  },
  divider: {
    marginVertical: 12,
  },
  deviceInfo: {
    marginBottom: 12,
  },
  actionInfo: {
    marginBottom: 12,
  },
  label: {
    marginBottom: 4,
  },
  parametersContainer: {
    backgroundColor: 'rgba(0, 0, 0, 0.05)',
    borderRadius: 8,
    padding: 12,
    marginTop: 8,
  },
  parameterRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  parameterKey: {
    flex: 1,
  },
  parameterValue: {
    fontWeight: '500',
  },
  actions: {
    justifyContent: 'flex-end',
    paddingHorizontal: 16,
    paddingBottom: 16,
    gap: 8,
  },
  button: {
    minWidth: 100,
  },
});
