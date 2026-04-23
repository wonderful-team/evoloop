// 调试测试页面

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Appbar } from 'react-native-paper';
import { useTheme } from '@/theme';
import { router } from '@/utils/navigation';
import NLSTestPanel from '@/components/debug/NLSTestPanel';

export default function DebugScreen() {
  const { colors } = useTheme();

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <Appbar.Header>
        <Appbar.BackAction onPress={() => router.back()} />
        <Appbar.Content title="NLS 语音识别测试" />
      </Appbar.Header>

      <NLSTestPanel />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
