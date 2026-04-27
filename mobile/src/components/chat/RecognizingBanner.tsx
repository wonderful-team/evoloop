// 实时语音识别状态横幅 - 独立组件，自行订阅 NLS Store
// 目的：将 nlsCurrentText / nlsVolume 的高频变化从 ChatScreen 中隔离，
// 避免语音识别过程中整页重渲染。

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useNLSStore } from '@/stores/nlsStore';
import { useTheme } from '@/theme';

export function RecognizingBanner() {
  const { colors } = useTheme();
  const isRecording = useNLSStore((s) => s.isRecording);
  const currentText = useNLSStore((s) => s.currentText);
  const volume = useNLSStore((s) => s.volume);

  if (!isRecording || !currentText) {
    return null;
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
      <MaterialIcons name="mic" size={16} color={colors.primary} />
      <Text variant="bodySmall" style={{ color: colors.onSurface, marginLeft: 8, flex: 1 }}>
        {currentText}
      </Text>
      <View style={[styles.volumeIndicator, { width: volume * 50, backgroundColor: colors.primary }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginHorizontal: 12,
    marginVertical: 4,
    borderRadius: 8,
  },
  volumeIndicator: {
    height: 4,
    borderRadius: 2,
    marginLeft: 8,
    maxWidth: 50,
  },
});
